#!/usr/bin/env python3
"""
deploy-user.py — Developer-side dbtrials deployment (no root required).

Builds the frontend, builds container images, starts services, prepares
Caddy volumes, and enables lingering for rootless Podman.

Run this first, then run deploy-root.py with sudo.

Options:
  --tls MODE      "internal" (self-signed, default), "http", or "internet" (Let's Encrypt)
  --domain DOMAIN  Required for --tls internet
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_DIST = REPO_ROOT / "frontend-dist"


def _green(msg: str) -> str:
    return f"\033[32m{msg}\033[0m"


def _yellow(msg: str) -> str:
    return f"\033[33m{msg}\033[0m"


def _red(msg: str) -> str:
    return f"\033[31m{msg}\033[0m"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def _check(*names: str) -> None:
    for name in names:
        if shutil.which(name) is None:
            _fail(f"{name} is not installed")


def _fail(msg: str) -> None:
    sys.exit(f"{_red('ERROR:')} {msg}")


def _rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Developer-side dbtrials deployment")
    parser.add_argument(
        "--tls", choices=("http", "internal", "internet"), default="internal"
    )
    parser.add_argument("--domain", default="")
    args = parser.parse_args()

    if args.tls == "internet" and not args.domain:
        _fail("--domain is required for internet TLS")

    print("==> Checking prerequisites...")
    _check("podman", "podman-compose", "node", "npm", "openssl", "loginctl")
    print(_green("   All prerequisites found."))

    tls_mode = args.tls
    caddyfile = {
        "http": REPO_ROOT / "Caddyfile",
        "internal": REPO_ROOT / "Caddyfile.internal",
        "internet": REPO_ROOT / "Caddyfile.internet",
    }[tls_mode]

    # ── 1. Build the frontend ──────────────────────────────────────────────
    print("\n==> Step 1: Building frontend...")
    run(["npm", "ci", "--silent"], cwd=FRONTEND_DIR)
    run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    _rmtree(FRONTEND_DIST)
    FRONTEND_DIST.mkdir()
    for item in (FRONTEND_DIR / "dist").iterdir():
        dest = FRONTEND_DIST / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    shutil.copy2(FRONTEND_DIR / "nginx-default.conf", FRONTEND_DIST)
    print(_green("   Frontend built and copied to frontend-dist/"))

    # ── 2. Build container images ──────────────────────────────────────────
    print("\n==> Step 2: Building container images...")
    run(["podman-compose", "build"], cwd=REPO_ROOT)
    print(_green("   Images built."))

    # ── 3. Start backend & frontend containers ─────────────────────────────
    print("\n==> Step 3: Starting containers (podman-compose up -d)...")
    run(["podman-compose", "up", "-d"], cwd=REPO_ROOT)

    print("   Waiting for backend to become ready...")
    import time

    for _ in range(60):
        result = subprocess.run(
            ["podman", "logs", "dbtrials-backend"],
            capture_output=True,
            text=True,
        )
        if "Booting worker" in result.stderr or "Booting worker" in result.stdout:
            print(_green("   Backend is ready."))
            break
        time.sleep(2)
    else:
        print(_red("   Backend did not become ready within 120 seconds."))
        print("   Check logs: podman logs dbtrials-backend")

    # ── 4. Prepare Caddy volumes ───────────────────────────────────────────
    print("\n==> Step 4: Preparing Caddy volumes...")

    # Populate Caddyfile volume
    subprocess.run(
        ["podman", "volume", "rm", "dbtrials_caddyfile"],
        capture_output=True,
    )
    if tls_mode == "internet":
        content = caddyfile.read_text()
        content = content.replace("your-domain.example.com", args.domain)
        caddyfile.write_text(content)
        print(_yellow(f"   Caddyfile.internet updated with domain: {args.domain}"))

    caddyfile_cp_command_list = [
        "podman",
        "run",
        "--rm",
        "-v",
        "dbtrials_caddyfile:/etc/caddy",
        "-v",
        f"{caddyfile}:/src/Caddyfile:ro",
        "docker.io/alpine",
        "cp",
        "/src/Caddyfile",
        "/etc/caddy/Caddyfile",
    ]

    caddyfile_cp_command_string = " ".join(caddyfile_cp_command_list)
    print("caddy file copy command")
    print(caddyfile_cp_command_string)
    run(caddyfile_cp_command_list)

    # caddyfile_contents_in_volume = [
    #     "podman",
    #     "run",
    #     "--rm",
    #     "-v",
    #     "dbtrials_caddyfile:/data",
    #     "-v",
    #     f"{caddyfile}:/src/Caddyfile:ro",
    #     "docker.io/alpine",
    #     "cat",
    #     "/data/Caddyfile",
    # ]
    # run(caddyfile_contents_in_volume)

    print(_green("   Caddyfile volume populated."))

    # Self-signed certificate for internal mode
    if tls_mode == "internal":
        cert_dir = Path.home() / "dbtrials-certs"
        if not (cert_dir / "dbtrials.pem").exists():
            print("   Generating self-signed certificate for dbtrials.local...")
            run([sys.executable, str(REPO_ROOT / "gencert.py"), "--out", str(cert_dir)])
        else:
            print(_yellow("   Certificate already exists — skipping."))

    # ── 5. Enable lingering for rootless Podman ────────────────────────────
    print(f"\n==> Step 5: Enabling lingering for user {os.environ['USER']}...")
    run(["loginctl", "enable-linger", os.environ["USER"]])
    print(_green("   Lingering enabled — containers will survive logout."))

    # ── done ───────────────────────────────────────────────────────────────
    print()
    print(_green("=" * 46))
    print(_green("  User deployment complete."))
    print(_green("=" * 46))
    print()
    print(f"   TLS mode : {tls_mode}")
    if args.domain:
        print(f"   Domain   : {args.domain}")
    print()
    suffix = f" --domain {args.domain}" if args.domain else ""
    print(f"   Now run as root:  sudo ./deploy-root.py --tls {tls_mode}{suffix}")
    print()
    print("   Generate a proper SECRET_KEY with:  openssl rand -hex 32")
    print("   then set it in compose.yml under the backend environment section.")


if __name__ == "__main__":
    main()
