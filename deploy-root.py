#!/usr/bin/env python3
"""
deploy-root.py — Caddy systemd setup (run as root or with sudo).

Must run *after* deploy-user.py so that volumes already exist.

Usage (as the developer user):
  sudo ./deploy-root.py [--tls MODE] [--domain DOMAIN]

Options:
  --tls MODE      "internal" (self-signed, default), "http", or "internet" (Let's Encrypt)
  --domain DOMAIN  Required for --tls internet
  --user UID       Numeric user ID of the developer (default: SUDO_UID or current uid)
  --cert-dir DIR   Certificates directory for internal TLS (default: developer's ~/dbtrials-certs)
"""

import argparse
import os
import pwd
import subprocess
import sys
from pathlib import Path
from string import Template

REPO_ROOT = Path(__file__).resolve().parent
SYSTEMD_DIR = Path("/etc/systemd/system")
SOCKET_TEMPLATE = REPO_ROOT / "systemd" / "caddy.socket.in"
SERVICE_TEMPLATE = REPO_ROOT / "systemd" / "caddy.service.in"

print(f"{REPO_ROOT=}")


def green(msg: str) -> str:
    return f"\033[32m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[33m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[31m{msg}\033[0m"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def _fail(msg: str) -> None:
    sys.exit(f"{red('ERROR:')} {msg}")


def _validate_template(path: Path) -> str:
    if not path.is_file():
        _fail(f"template not found: {path}")
    return path.read_text()


def _write_systemd(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o644)
    print(green(f"   Wrote {path}"))


def main() -> None:
    if os.geteuid() != 0:
        _fail("This script must be run as root. Use: sudo ./deploy-root.py ...")

    parser = argparse.ArgumentParser(description="Caddy systemd setup (requires root)")
    parser.add_argument(
        "--tls", choices=("http", "internal", "internet"), default="internal"
    )
    parser.add_argument("--domain", default="")
    parser.add_argument("--user", type=int, default=0)
    parser.add_argument("--cert-dir", default="")
    args = parser.parse_args()

    # Resolve developer user
    dev_uid = args.user or int(os.environ.get("SUDO_UID", "0"))
    if dev_uid == 0:
        _fail("--user is required when running as root without sudo (SUDO_UID not set)")

    try:
        pw = pwd.getpwuid(dev_uid)
    except KeyError:
        _fail(f"user with uid {dev_uid} not found")

    if args.tls == "internet" and not args.domain:
        _fail("--domain is required for internet TLS")

    # Cert dir for internal mode
    cert_dir = args.cert_dir or os.path.join(pw.pw_dir, "dbtrials-certs")
    if args.tls == "internal" and not Path(cert_dir).is_dir():
        _fail(f"cert dir not found: {cert_dir} (use --cert-dir)")

    # ── socket template ────────────────────────────────────────────────────
    socket_template = Template(_validate_template(SOCKET_TEMPLATE))
    listen_streams = {
        "http": "ListenStream=127.0.0.1:80",
        "internal": "ListenStream=127.0.0.1:80\nListenStream=127.0.0.1:443",
        "internet": "ListenStream=80\nListenStream=443",
    }[args.tls]
    socket_content = socket_template.substitute(LISTEN_STREAMS=listen_streams)
    _write_systemd(SYSTEMD_DIR / "caddy.socket", socket_content)

    # ── service template ───────────────────────────────────────────────────
    print(f"{args.tls=}")
    service_template = Template(_validate_template(SERVICE_TEMPLATE))
    cert_vol = f"  -v {cert_dir}:/etc/caddy/certs:ro" if args.tls == "internal" else ""
    print(cert_vol)
    service_content = service_template.substitute(
        CERT_VOLUME=cert_vol,
    )
    print("final file contents:")
    print(service_content)
    _write_systemd(SYSTEMD_DIR / "caddy.service", service_content)

    # ── reload & start ─────────────────────────────────────────────────────
    print("==> Enabling and starting caddy.socket ...")
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "caddy.socket"])

    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", "caddy.socket"],
    )
    if result.returncode == 0:
        print(green("   caddy.socket is active."))
    else:
        print(
            red("   caddy.socket failed to start. Check: systemctl status caddy.socket")
        )

    # ── done ───────────────────────────────────────────────────────────────
    print()
    print(green("=" * 46))
    print(green("  Root deployment complete."))
    print(green("=" * 46))
    print()
    print(f"   TLS mode : {args.tls}")
    if args.domain:
        print(f"   Domain   : {args.domain}")
    print()
    print("   Test with:")
    print("     curl http://localhost/")
    print("     curl http://localhost/api/docs")
    print("     curl http://localhost/admin/login/")
    if args.tls == "internal":
        print()
        print("   NOTE: Resolve 'dbtrials.local' to 127.0.0.1 in /etc/hosts")
        print("   and access via https://dbtrials.local")
    if args.tls == "internet":
        print()
        print("   NOTE: Ensure ports 80 and 443 are reachable from the internet.")
        print(
            f"   Caddy will auto-obtain a Let's Encrypt certificate for {args.domain}"
        )


if __name__ == "__main__":
    main()
