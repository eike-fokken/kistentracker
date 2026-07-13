#!/usr/bin/env python3
"""Generate the root systemd socket-activation files for the Caddy container.

This renders, from the templates in ``templates/``:

* ``caddy.socket``   -- one socket unit with two ``ListenStream`` entries (the
  HTTP and HTTPS ports) that systemd binds and hands to the container.
* ``caddy.service``  -- the Podman unit that runs Caddy; the activated sockets
  are forwarded into the container (fd/3 = HTTP, fd/4 = HTTPS).
* ``Caddyfile.socket`` -- a Caddy config that binds those file descriptors
  instead of opening its own ports.

The script only writes files; it never invokes Podman or systemd (installing the
units requires root). Run it as your normal user, then follow the printed
instructions to install the generated files.

Example:

    ./generate.py --site-address rentals.example.com --acme-email you@example.com
"""

from __future__ import annotations

import argparse
import os
import pwd
import re
import stat
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"

# template file -> output file name
TEMPLATES = {
    "caddy.socket.tmpl": "caddy.socket",
    "caddy.service.tmpl": "caddy.service",
    "Caddyfile.socket.tmpl": "Caddyfile.socket",
    "backup-db.service.tmpl": "backup-db.service",
    "backup-db.timer.tmpl": "backup-db.timer",
}

_TOKEN_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Return the parsed command-line options (with defaults matching the stack)."""
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
    parser.add_argument(
        "--user",
        action="store_true",
        help="Generate units for a rootless `systemctl --user` manager instead of "
        "the system manager. Requires unprivileged ports (>= 1024).",
    )
    parser.add_argument(
        "--run-as",
        default="",
        metavar="USER",
        help="System-unit mode only: run the Caddy container as this unprivileged "
        "user via a root-owned socket unit (root binds 80/443, the service drops "
        "privileges). This is Option B -- privileged ports without a system-wide "
        "sysctl change. The user's ROOTLESS podman must own the network/volumes.",
    )
    parser.add_argument(
        "--run-as-uid",
        type=int,
        default=None,
        help="UID for --run-as (needed for XDG_RUNTIME_DIR). Looked up from the "
        "local passwd database if omitted.",
    )
    parser.add_argument(
        "--run-as-group",
        default="",
        help="Group for --run-as (defaults to the same name as --run-as).",
    )

    # Ports the socket unit binds (the public entry points).
    parser.add_argument("--http-port", type=int, default=80)
    parser.add_argument("--https-port", type=int, default=443)

    # Caddy / backend wiring.
    parser.add_argument("--site-address", default="localhost")
    parser.add_argument(
        "--acme-email",
        default="",
        help="If set, use Let's Encrypt with this email; otherwise 'tls internal' "
        "(self-signed).",
    )
    parser.add_argument("--backend-port", type=int, default=8000)

    # Podman resources. Defaults match the podman-compose stack (project name
    # 'deployment'). Verify with `podman network ls` / `podman volume ls`.
    parser.add_argument("--container-name", default="caddy")
    parser.add_argument("--image", default="docker.io/library/caddy:2-alpine")
    parser.add_argument("--network", default="deployment_dbtrials")
    parser.add_argument("--frontend-volume", default="deployment_frontend")
    parser.add_argument("--caddy-data-volume", default="deployment_caddy_data")
    parser.add_argument("--caddy-config-volume", default="deployment_caddy_config")
    parser.add_argument(
        "--podman",
        default="/usr/bin/podman",
        help="Absolute path to the podman binary used in the service unit.",
    )
    parser.add_argument(
        "--caddyfile-path",
        type=Path,
        default=None,
        help="Absolute path the service unit mounts as the Caddyfile. Defaults to "
        "/etc/caddy/<container-name>.Caddyfile.",
    )

    # Backup service options.
    parser.add_argument(
        "--data-volume",
        default="deployment_data",
        help="Name of the Podman volume holding the SQLite database.",
    )
    parser.add_argument(
        "--backup-dir",
        required=True,
        help="Host directory where backup files are written (required).",
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
        help="Max random delay (seconds) past the timer's OnCalendar moment "
        "before the backup actually fires.",
    )
    parser.add_argument(
        "--after-backend",
        default="backend",
        metavar="CONTAINER",
        help="The backup unit will order itself After= this container to avoid "
        "racing a podman-compose up on boot. Set to empty to skip.",
    )
    return parser.parse_args(argv)


def build_context(args: argparse.Namespace) -> dict[str, str]:
    """Turn parsed options into the flat string context used for rendering."""
    output_dir = args.output_dir.resolve()
    if args.caddyfile_path is not None:
        caddyfile_path = args.caddyfile_path.resolve()
    elif args.user:
        caddyfile_path = (
            Path("~/.config/caddy").expanduser() / f"{args.container_name}.Caddyfile"
        )
    else:
        caddyfile_path = Path(f"/etc/caddy/{args.container_name}.Caddyfile")

    # ACME vs. self-signed: an email line in the global block enables Let's
    # Encrypt; without it we force Caddy's internal (self-signed) CA.
    if args.acme_email:
        email_line = f"\temail {args.acme_email}\n"
        tls_line = ""  # Caddy manages the public certificate automatically.
    else:
        email_line = ""
        tls_line = "\ttls internal"

    # System vs. rootless user manager: the user manager has no
    # network-online.target and uses default.target instead of multi-user.target.
    if args.user:
        after_extra = ""
        wants_line = ""
        service_wantedby = "default.target"
    else:
        after_extra = " network-online.target"
        wants_line = "Wants=network-online.target"
        service_wantedby = "multi-user.target"

    # Option B: a system unit that drops privileges to an unprivileged user.
    # Root's socket unit binds 80/443 and passes the fds to this service, which
    # runs podman as `--run-as`. Rootless podman then needs that user's runtime
    # dir, and we order after their (lingering) user manager so it exists.
    if args.run_as:
        group = args.run_as_group or args.run_as
        user_group_lines = f"User={args.run_as}\nGroup={group}\n"
        runtime_env_line = f"Environment=XDG_RUNTIME_DIR=/run/user/{args.run_as_uid}\n"
        after_extra += f" user@{args.run_as_uid}.service"
    else:
        user_group_lines = ""
        runtime_env_line = ""

    # HTTP->HTTPS redirect target. Caddy's {host} drops the port, so when HTTPS
    # is served on a non-standard port we must add it explicitly, otherwise the
    # redirect points at :443 (which nothing serves in a high-port test setup).
    if args.https_port == 443:
        redir_hostport = "{host}"
    else:
        redir_hostport = "{host}:" + str(args.https_port)

    # Backup service: whether to wait for the backend container on boot.
    after_backend_line = (
        f"After=podman-{args.after_backend}.service"
        if args.after_backend
        else ""
    )

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
    }


def render(template_text: str, context: dict[str, str], source: str) -> str:
    """Replace every ``{{TOKEN}}`` with its context value; fail on unknown tokens."""
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
    """Render all templates into the output directory and print install steps."""
    args = parse_args(argv)

    if args.user and args.run_as:
        print(
            "error: --user and --run-as are mutually exclusive (--run-as is for a "
            "system unit that drops to an unprivileged user).",
            file=sys.stderr,
        )
        return 2

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
            "if the host allows it, e.g.:\n"
            "  sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80\n"
            "(persist it in /etc/sysctl.d/). This is system-wide -- prefer --run-as "
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

    _print_instructions(
        context,
        output_dir,
        written,
        user_mode=args.user,
        run_as=args.run_as,
        run_as_uid=args.run_as_uid,
    )
    return 0


def _print_instructions(
    context: dict[str, str],
    output_dir: Path,
    written: list[Path],
    user_mode: bool,
    run_as: str,
    run_as_uid: int | None,
) -> None:
    """Print where the files went and how to install them (user / root / Option B)."""
    unit = context["CONTAINER_NAME"]
    caddyfile = Path(context["CADDYFILE_HOST_PATH"])
    print("Generated:")
    for path in written:
        print(f"  {path}")
    print()

    if user_mode:
        unit_dir = "~/.config/systemd/user"
        print("Install for the rootless user manager (no root needed):")
        print(f"  install -D -m 0644 {output_dir / 'Caddyfile.socket'} {caddyfile}")
        print(f"  mkdir -p {unit_dir}")
        print(f"  install -m 0644 {output_dir / (unit + '.socket')} {unit_dir}/")
        print(f"  install -m 0644 {output_dir / (unit + '.service')} {unit_dir}/")
        print("  systemctl --user daemon-reload")
        print(f"  systemctl --user enable --now {unit}.socket")
        print("  # start at boot without an active login session:")
        print('  loginctl enable-linger "$USER"')
    elif run_as:
        print(
            f"Install as root; root binds the ports and Caddy runs as '{run_as}' "
            f"(uid {run_as_uid})."
        )
        print("Prerequisites (once):")
        print(
            f"  sudo loginctl enable-linger {run_as}   # ensures /run/user/{run_as_uid} exists at boot"
        )
        print(
            f"  # {run_as} needs subuid/subgid ranges for rootless podman (usually preset):"
        )
        print(f"  grep -q '^{run_as}:' /etc/subuid /etc/subgid || \\")
        print(
            f"    sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 {run_as}"
        )
        print()
        print("Install the files (root):")
        print(
            f"  sudo install -D -m 0644 {output_dir / 'Caddyfile.socket'} {caddyfile}"
        )
        print(
            f"  sudo install -m 0644 {output_dir / (unit + '.socket')} /etc/systemd/system/"
        )
        print(
            f"  sudo install -m 0644 {output_dir / (unit + '.service')} /etc/systemd/system/"
        )
        print("  sudo systemctl daemon-reload")
        print(f"  sudo systemctl enable --now {unit}.socket")
        print()
        print(f"The stack must run in {run_as}'s ROOTLESS podman so it owns the")
        print("network/volumes the service references. Run compose as that user, e.g.:")
        print(f"  sudo machinectl shell {run_as}@ /bin/sh -c \\")
        print(
            "    'cd <path>/deployment && podman-compose up -d backend frontend-build'"
        )
        print()
        print("Note: the units reference the network/volume names from that user's")
        print(
            "podman (verify with: sudo -u %s ... podman network ls / volume ls)."
            % run_as
        )
        return
    else:
        print("Install as root (review the files first):")
        print("  # 1. Put the Caddyfile where the service expects it:")
        print(f"  install -D -m 0644 {output_dir / 'Caddyfile.socket'} {caddyfile}")
        print(
            "  #    (on SELinux systems: restorecon -v <path> or add ',Z' to the mount)"
        )
        print("  # 2. Install the units:")
        print(
            f"  install -m 0644 {output_dir / (unit + '.socket')} /etc/systemd/system/"
        )
        print(
            f"  install -m 0644 {output_dir / (unit + '.service')} /etc/systemd/system/"
        )
        print("  # 3. Reload and enable (the socket triggers the service):")
        print("  systemctl daemon-reload")
        print(f"  systemctl enable --now {unit}.socket")

    print()
    print("Bring up the backend + frontend build with podman-compose first, e.g.:")
    print("  podman-compose up -d backend frontend-build")
    print("(Do not also run the compose 'caddy' service; this unit replaces it.)")

    # Backup units.
    print()
    print("--- Database backup (systemd timer) ---")
    backup_dir = context["BACKUP_DIR"]
    timer_unit = "backup-db.timer"
    service_unit = "backup-db.service"
    if user_mode:
        print("Install the backup timer under your user manager:")
        print(f"  mkdir -p ~/.config/systemd/user")
        print(f"  install -m 0644 {output_dir / service_unit} ~/.config/systemd/user/")
        print(f"  install -m 0644 {output_dir / timer_unit} ~/.config/systemd/user/")
        print(f"  install -d -m 0755 {backup_dir}")
        print("  systemctl --user daemon-reload")
        print(f"  systemctl --user enable --now {timer_unit}")
        print("  # Run once immediately to test:", f"systemctl --user start {service_unit}")
    else:
        print("Install the backup timer (system level, as root):")
        print(f"  sudo install -d -m 0755 {backup_dir}")
        print(f"  sudo install -m 0644 {output_dir / service_unit} /etc/systemd/system/")
        print(f"  sudo install -m 0644 {output_dir / timer_unit} /etc/systemd/system/")
        print("  sudo systemctl daemon-reload")
        print(f"  sudo systemctl enable --now {timer_unit}")
        print(f"  # Run once immediately to test:",
              f"sudo systemctl start {service_unit}")
    print(f"  # Inspect with: journalctl -u {service_unit}")


if __name__ == "__main__":
    raise SystemExit(main())
