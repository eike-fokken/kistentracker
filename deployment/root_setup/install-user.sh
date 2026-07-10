#!/usr/bin/env bash
#
# Install the socket-activated Caddy units into the rootless *user* systemd
# manager. Idempotent: every run first tears down anything a previous run (or a
# previous attempt) installed, so it always ends on a clean slate.
#
# It installs the files currently in ./generated/ (produce them with
#   ./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180
# ). Run this script as your normal user -- no root required.

set -euo pipefail

UNIT_NAME="${UNIT_NAME:-caddy}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN_DIR="$SCRIPT_DIR/generated"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

SOCKET_UNIT="$UNIT_NAME.socket"
SERVICE_UNIT="$UNIT_NAME.service"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- Preconditions --------------------------------------------------------
for f in "$SOCKET_UNIT" "$SERVICE_UNIT" "Caddyfile.socket"; do
	if [[ ! -f "$GEN_DIR/$f" ]]; then
		echo "error: $GEN_DIR/$f not found. Generate it first, e.g.:" >&2
		echo "  ./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180" >&2
		exit 1
	fi
done

# Where the service mounts the Caddyfile -- read it straight from the generated
# unit so this script and the unit can never disagree.
CADDYFILE_DEST="$(
	grep -oE -- "-v [^:]+:/etc/caddy/Caddyfile:ro" "$GEN_DIR/$SERVICE_UNIT" |
		head -n1 | sed -E 's/^-v //; s#:/etc/caddy/Caddyfile:ro$##'
)"
if [[ -z "$CADDYFILE_DEST" ]]; then
	echo "error: could not determine the Caddyfile path from $SERVICE_UNIT" >&2
	exit 1
fi

# --- Clean slate: remove anything a previous attempt left behind ----------
say "Tearing down any previous installation"
# Stop + disable (removes *.wants symlinks). Ignore errors if not present.
systemctl --user disable --now "$SOCKET_UNIT" "$SERVICE_UNIT" 2>/dev/null || true
systemctl --user stop "$SERVICE_UNIT" "$SOCKET_UNIT" 2>/dev/null || true
# Force-remove a leftover container so the fresh service can recreate it.
podman rm -f "$UNIT_NAME" 2>/dev/null || true
# Delete old unit files and Caddyfile.
rm -f "$USER_UNIT_DIR/$SOCKET_UNIT" "$USER_UNIT_DIR/$SERVICE_UNIT"
rm -f "$CADDYFILE_DEST"
systemctl --user daemon-reload

# --- Install fresh files --------------------------------------------------
say "Installing Caddyfile to $CADDYFILE_DEST"
install -D -m 0644 "$GEN_DIR/Caddyfile.socket" "$CADDYFILE_DEST"

say "Installing units to $USER_UNIT_DIR"
mkdir -p "$USER_UNIT_DIR"
install -m 0644 "$GEN_DIR/$SOCKET_UNIT" "$USER_UNIT_DIR/"
install -m 0644 "$GEN_DIR/$SERVICE_UNIT" "$USER_UNIT_DIR/"

systemctl --user daemon-reload

say "Enabling and starting $SOCKET_UNIT"
systemctl --user enable --now "$SOCKET_UNIT"

# --- Report ---------------------------------------------------------------
say "Done. Current status:"
systemctl --user --no-pager status "$SOCKET_UNIT" || true
echo
echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket"
echo "activation). Make sure the backend + frontend build are up:"
echo "  (cd \"$SCRIPT_DIR/..\" && podman-compose up -d backend frontend-build)"
echo "To start at boot without an active login: loginctl enable-linger \"\$USER\""
