#!/usr/bin/env python3
"""Generate systemd units for the Kistentracker Caddy + backend stack.

This renders, from the templates in ``templates/``:

* ``caddy.socket``   -- socket unit binding HTTP/HTTPS ports.
* ``caddy.service``  -- system unit running Caddy via Podman.
* ``Caddyfile.socket`` -- Caddy config binding socket-activated file descriptors.
* ``backend.service`` -- user unit running ``podman-compose up -d``.
* ``backup-db.service`` / ``backup-db.timer`` -- SQLite backup oneshot + timer.

Two modes (mutually exclusive):

* ``--user``      -- rootless user manager (all units as user units).
                     Requires unprivileged ports (>= 1024).
* ``--run-as USER`` -- system units for Caddy + backup; Caddy drops to USER.
                     Backend runs as a user unit of USER.

The script only writes files; it never invokes Podman or systemd. Run it as
your normal user, then follow the printed instructions to install.

Examples:

    ./generate.py --user --http-port 8080 --https-port 8443 \\
        --backup-dir /home/myuser/backups/kistentracker

    ./generate.py --run-as appuser --site-address example.com \\
        --acme-email you@example.com --backup-dir /var/backups/kistentracker
"""

from __future__ import annotations

import argparse
import pwd
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"

TEMPLATES = {
    "caddy.socket.tmpl": "caddy.socket",
    "caddy.service.tmpl": "caddy.service",
    "Caddyfile.socket.tmpl": "Caddyfile.socket",
    "backend.service.tmpl": "backend.service",
    "backup-db.service.tmpl": "backup-db.service",
    "backup-db.timer.tmpl": "backup-db.timer",
}

_TOKEN_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR / "generated",
        help="Directory to write the generated files into.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--user",
        action="store_true",
        help="Generate units for a rootless `systemctl --user` manager. "
        "Requires unprivileged ports (>= 1024).",
    )
    mode.add_argument(
        "--run-as",
        metavar="USER",
        help="Generate system units that drop Caddy privileges to this "
        "unprivileged user. Backend runs as a user unit of this user.",
    )
    parser.add_argument(
        "--run-as-uid",
        type=int,
        default=None,
        help="UID for --run-as (needed for XDG_RUNTIME_DIR). Looked up from the "
        "local passwd database if omitted.",
    )

    parser.add_argument("--http-port", type=int, default=80)
    parser.add_argument("--https-port", type=int, default=443)

    parser.add_argument("--site-address", default="localhost")
    parser.add_argument(
        "--acme-email",
        default="",
        help="Use Let's Encrypt with this email; omit for 'tls internal' (self-signed).",
    )
    parser.add_argument("--backend-port", type=int, default=8000)

    parser.add_argument("--container-name", default="caddy")
    parser.add_argument("--image", default="docker.io/library/caddy:2-alpine")
    parser.add_argument("--network", default="deployment_dbtrials")
    parser.add_argument("--frontend-volume", default="deployment_frontend")
    parser.add_argument("--caddy-data-volume", default="deployment_caddy_data")
    parser.add_argument("--caddy-config-volume", default="deployment_caddy_config")
    parser.add_argument(
        "--podman",
        default="/usr/bin/podman",
        help="Absolute path to the podman binary.",
    )
    parser.add_argument(
        "--caddyfile-path",
        type=Path,
        default=None,
        help="Absolute path the service mounts as the Caddyfile. Defaults "
        "depends on --user (~/.config/caddy/) or --run-as (/etc/caddy/).",
    )

    parser.add_argument(
        "--data-volume",
        default="deployment_data",
        help="Name of the Podman volume holding the SQLite database.",
    )
    parser.add_argument(
        "--backup-dir",
        required=True,
        help="Host directory where backup files are written.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Remove backup files older than this many days.",
    )
    parser.add_argument(
        "--backup-randomized-delay-sec",
        type=int,
        default=3600,
        help="Max random delay (seconds) past the timer's OnCalendar moment.",
    )
    parser.add_argument(
        "--after-backend",
        default="backend",
        metavar="CONTAINER",
        help="Order backup After= this container to avoid racing a "
        "podman-compose up on boot. Set to empty to skip.",
    )

    parser.add_argument(
        "--compose-file",
        type=Path,
        default=None,
        help="Path to compose.yml (defaults to <SCRIPT_DIR>/../compose.yml).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to .env for podman-compose (defaults to <SCRIPT_DIR>/../.env).",
    )
    parser.add_argument(
        "--podman-compose",
        default="podman-compose",
        help="Path to the podman-compose binary.",
    )
    parser.add_argument(
        "--no-frontend-build",
        action="store_true",
        help="Do not start the frontend-build compose service in the backend unit.",
    )
    return parser.parse_args(argv)


def build_context(args: argparse.Namespace) -> dict[str, str]:
    if args.caddyfile_path is not None:
        caddyfile_path = args.caddyfile_path.resolve()
    elif args.user:
        caddyfile_path = (
            Path("~/.config/caddy").expanduser() / f"{args.container_name}.Caddyfile"
        )
    else:
        caddyfile_path = Path(f"/etc/caddy/{args.container_name}.Caddyfile")

    if args.acme_email:
        email_line = f"\temail {args.acme_email}\n"
        tls_line = ""
    else:
        email_line = ""
        tls_line = "\ttls internal"

    if args.user:
        after_extra = ""
        wants_line = ""
        service_wantedby = "default.target"
        user_group_lines = ""
        runtime_env_line = ""
    else:
        after_extra = " network-online.target"
        wants_line = "Wants=network-online.target"
        service_wantedby = "multi-user.target"
        user_group_lines = f"User={args.run_as}\nGroup={args.run_as}\n"
        runtime_env_line = f"Environment=XDG_RUNTIME_DIR=/run/user/{args.run_as_uid}\n"
        after_extra += f" user@{args.run_as_uid}.service"

    if args.https_port == 443:
        redir_hostport = "{host}"
    else:
        redir_hostport = "{host}:" + str(args.https_port)

    after_backend_line = (
        f"After=podman-{args.after_backend}.service" if args.after_backend else ""
    )

    compose_file = args.compose_file or (SCRIPT_DIR / ".." / "compose.yml")
    compose_file = compose_file.resolve()
    env_file = args.env_file or (SCRIPT_DIR / ".." / ".env")
    env_file = env_file.resolve()
    frontend_build_service = "" if args.no_frontend_build else " frontend-build"

    return {
        "CONTAINER_NAME": args.container_name,
        "IMAGE": args.image,
        "NETWORK": args.network,
        "FRONTEND_VOLUME": args.frontend_volume,
        "CADDY_DATA_VOLUME": args.caddy_data_volume,
        "CADDY_CONFIG_VOLUME": args.caddy_config_volume,
        "PODMAN": args.podman,
        "HTTP_PORT": str(args.http_port),
        "HTTPS_PORT": str(args.https_port),
        "SITE_ADDRESS": args.site_address,
        "BACKEND_PORT": str(args.backend_port),
        "CADDYFILE_HOST_PATH": str(caddyfile_path),
        "CADDYFILE_BASENAME": caddyfile_path.name,
        "EMAIL_LINE": email_line,
        "TLS_LINE": tls_line,
        "AFTER_EXTRA": after_extra,
        "WANTS_LINE": wants_line,
        "SERVICE_WANTEDBY": service_wantedby,
        "REDIR_HOSTPORT": redir_hostport,
        "USER_GROUP_LINES": user_group_lines,
        "RUNTIME_ENV_LINE": runtime_env_line,
        "DATA_VOLUME": args.data_volume,
        "BACKUP_DIR": args.backup_dir,
        "RETENTION_DAYS": str(args.retention_days),
        "RANDOMIZED_DELAY_SEC": str(args.backup_randomized_delay_sec),
        "AFTER_BACKEND_LINE": after_backend_line,
        "COMPOSE_FILE": str(compose_file),
        "ENV_FILE": str(env_file),
        "PODMAN_COMPOSE": args.podman_compose,
        "FRONTEND_BUILD_SERVICE": frontend_build_service,
    }


def render(template_text: str, context: dict[str, str], source: str) -> str:
    missing: set[str] = set()

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            missing.add(key)
            return match.group(0)
        return context[key]

    result = _TOKEN_RE.sub(_sub, template_text)
    if missing:
        raise KeyError(
            f"{source}: unknown template token(s): {', '.join(sorted(missing))}"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.run_as and args.run_as_uid is None:
        try:
            args.run_as_uid = pwd.getpwnam(args.run_as).pw_uid
        except KeyError:
            print(
                f"error: user '{args.run_as}' not found in the local passwd "
                "database. Pass --run-as-uid explicitly (e.g. when generating on a "
                "different host than the deployment target).",
                file=sys.stderr,
            )
            return 2

    context = build_context(args)

    if args.user and (args.http_port < 1024 or args.https_port < 1024):
        print(
            f"warning: --user with privileged port(s) http={args.http_port}, "
            f"https={args.https_port}. A rootless user manager can only bind these "
            "if the host allows it, but that is dangerous!e.g.:\n"
            "Please use a non-privileged port or use --run-as "
            "(a system unit that drops to an unprivileged user) for privileged ports.",
            file=sys.stderr,
        )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for template_name, output_name in TEMPLATES.items():
        template_path = TEMPLATE_DIR / template_name
        try:
            template_text = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"error: cannot read template {template_path}: {exc}", file=sys.stderr
            )
            return 1
        rendered = render(template_text, context, template_name)
        out_path = output_dir / output_name
        out_path.write_text(rendered, encoding="utf-8")
        written.append(out_path)

    _print_instructions(context, output_dir, written, args)
    return 0


def _print_instructions(
    context: dict[str, str],
    output_dir: Path,
    written: list[Path],
    args: argparse.Namespace,
) -> None:
    unit = context["CONTAINER_NAME"]
    caddyfile = Path(context["CADDYFILE_HOST_PATH"])

    print("Generated:")
    for path in written:
        print(f"  {path}")
    print()

    if args.user:
        _print_user_instructions(context, output_dir, written, unit, caddyfile)
    else:
        _print_run_as_instructions(context, output_dir, written, unit, caddyfile, args)


def _print_user_instructions(
    context: dict[str, str],
    output_dir: Path,
    written: list[Path],
    unit: str,
    caddyfile: Path,
) -> None:
    unit_dir = "~/.config/systemd/user"
    print("Install for the rootless user manager (no root needed):")
    print(f"  install -D -m 0644 {output_dir / 'Caddyfile.socket'} {caddyfile}")
    print(f"  mkdir -p {unit_dir}")
    print(f"  install -m 0644 {output_dir / (unit + '.socket')} {unit_dir}/")
    print(f"  install -m 0644 {output_dir / (unit + '.service')} {unit_dir}/")
    print(f"  install -m 0644 {output_dir / 'backend.service'} {unit_dir}/")
    print("  systemctl --user daemon-reload")
    print(f"  systemctl --user enable --now {unit}.socket")
    print(f"  systemctl --user enable --now backend.service")
    print("  # start at boot without an active login session:")
    print('  loginctl enable-linger "$USER"')
    print()

    print("--- Database backup (systemd timer) ---")
    backup_dir = context["BACKUP_DIR"]
    timer_unit = "backup-db.timer"
    service_unit = "backup-db.service"
    print("Install the backup timer under your user manager:")
    print(f"  mkdir -p {unit_dir}")
    print(f"  install -m 0644 {output_dir / service_unit} {unit_dir}/")
    print(f"  install -m 0644 {output_dir / timer_unit} {unit_dir}/")
    print(f"  install -d -m 0755 {backup_dir}")
    print("  systemctl --user daemon-reload")
    print(f"  systemctl --user enable --now {timer_unit}")
    print("  # Run once immediately to test:", f"systemctl --user start {service_unit}")
    print(f"  # Inspect with: journalctl -u {service_unit}")


def _print_run_as_instructions(
    context: dict[str, str],
    output_dir: Path,
    written: list[Path],
    unit: str,
    caddyfile: Path,
    args: argparse.Namespace,
) -> None:
    run_as = args.run_as
    run_as_uid = args.run_as_uid

    print(
        f"Install as root; root binds the ports and Caddy runs as '{run_as}' "
        f"(uid {run_as_uid})."
    )
    print("Prerequisites (once):")
    print(
        f"  sudo loginctl enable-linger {run_as}   "
        f"# ensures /run/user/{run_as_uid} exists at boot"
    )
    print(
        f"  # {run_as} needs subuid/subgid ranges for rootless podman (usually preset):"
    )
    print(f"  grep -q '^{run_as}:' /etc/subuid /etc/subgid || \\")
    print(
        f"    sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 {run_as}"
    )
    print()
    print("Install the Caddy units (root):")
    print(f"  sudo install -D -m 0644 {output_dir / 'Caddyfile.socket'} {caddyfile}")
    print(
        f"  sudo install -m 0644 {output_dir / (unit + '.socket')} /etc/systemd/system/"
    )
    print(
        f"  sudo install -m 0644 {output_dir / (unit + '.service')} /etc/systemd/system/"
    )
    print("  sudo systemctl daemon-reload")
    print(f"  sudo systemctl enable --now {unit}.socket")
    print()
    print(f"Install the backend unit as a user unit for '{run_as}':")
    print(f"  sudo -u {run_as} mkdir -p ~{run_as}/.config/systemd/user")
    print(
        f"  sudo -u {run_as} install -m 0644 {output_dir / 'backend.service'} "
        f"~{run_as}/.config/systemd/user/"
    )
    print(f"  sudo -u {run_as} systemctl --user daemon-reload")
    print(f"  sudo -u {run_as} systemctl --user enable --now backend.service")
    print()
    print(f"The backend unit runs podman-compose as '{run_as}' so it owns the")
    print("network/volumes. The compose file and .env must be in place:")
    print(f"  compose: {context['COMPOSE_FILE']}")
    print(f"  env:     {context['ENV_FILE']}")
    print()
    print(f"  (verify with: sudo -u {run_as} podman network ls / volume ls).")
    print()

    backup_dir = context["BACKUP_DIR"]
    timer_unit = "backup-db.timer"
    service_unit = "backup-db.service"
    print("--- Database backup (systemd timer, install as user unit) ---")
    print(f"  sudo -u {run_as} mkdir -p ~{run_as}/.config/systemd/user")
    print(f"  sudo -u {run_as} install -m 0644 {output_dir / service_unit} ~{run_as}/.config/systemd/user/")
    print(f"  sudo -u {run_as} install -m 0644 {output_dir / timer_unit} ~{run_as}/.config/systemd/user/")
    print(f"  install -d -m 0755 {backup_dir}")
    print(f"  sudo -u {run_as} systemctl --user daemon-reload")
    print(f"  sudo -u {run_as} systemctl --user enable --now {timer_unit}")
    print(f"  # Run once immediately to test: sudo -u {run_as} systemctl --user start {service_unit}")
    print(f"  # Inspect with: sudo -u {run_as} journalctl --user -u {service_unit}")


if __name__ == "__main__":
    raise SystemExit(main())
