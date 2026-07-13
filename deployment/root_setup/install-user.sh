#!/usr/bin/env bash
#
# Install the socket-activated Caddy units AND the database backup timer into
# the rootless *user* systemd manager. Idempotent: every run first tears down
# anything a previous run (or a previous attempt) installed, so it always ends
# on a clean slate.
#
# It installs the files currently in ./generated/ (produce them with
#   ./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180 \
#       --backup-dir /home/myuser/backups/kistentracker
#   --backup-dir /some/path
# ). Run this script as your normal user -- no root required.

set -euo pipefail

UNIT_NAME="${UNIT_NAME:-caddy}"
BACKUP_UNIT_NAME="${BACKUP_UNIT_NAME:-backup-db}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN_DIR="$SCRIPT_DIR/generated"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

SOCKET_UNIT="$UNIT_NAME.socket"
SERVICE_UNIT="$UNIT_NAME.service"
BACKUP_SERVICE_UNIT="$BACKUP_UNIT_NAME.service"
BACKUP_TIMER_UNIT="$BACKUP_UNIT_NAME.timer"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- Preconditions --------------------------------------------------------
for f in "$SOCKET_UNIT" "$SERVICE_UNIT" "Caddyfile.socket" "$BACKUP_SERVICE_UNIT" "$BACKUP_TIMER_UNIT"; do
	if [[ ! -f "$GEN_DIR/$f" ]]; then
		echo "error: $GEN_DIR/$f not found. Generate it first, e.g.:" >&2
		echo "  ./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180 --backup-dir /some/path" >&2
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
systemctl --user disable --now "$BACKUP_TIMER_UNIT" "$BACKUP_SERVICE_UNIT" 2>/dev/null || true
systemctl --user stop "$SERVICE_UNIT" "$SOCKET_UNIT" 2>/dev/null || true
systemctl --user stop "$BACKUP_SERVICE_UNIT" "$BACKUP_TIMER_UNIT" 2>/dev/null || true
# Force-remove a leftover container so the fresh service can recreate it.
podman rm -f "$UNIT_NAME" 2>/dev/null || true
# Delete old unit files and Caddyfile.
rm -f "$USER_UNIT_DIR/$SOCKET_UNIT" "$USER_UNIT_DIR/$SERVICE_UNIT"
rm -f "$USER_UNIT_DIR/$BACKUP_SERVICE_UNIT" "$USER_UNIT_DIR/$BACKUP_TIMER_UNIT"
rm -f "$CADDYFILE_DEST"
systemctl --user daemon-reload

# Ensure the backup directory exists.
BACKUP_DIR="$(
	grep -oE -- "-v [^:]+:/backup" "$GEN_DIR/$BACKUP_SERVICE_UNIT" |
		head -n1 | sed -E 's/^-v //; s#:/backup$##'
)"
if [[ -n "$BACKUP_DIR" ]]; then
	say "Creating backup directory $BACKUP_DIR"
	install -d -m 0755 "$BACKUP_DIR"
fi

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

# --- Install backup timer --------------------------------------------------
say "Installing backup timer"
install -m 0644 "$GEN_DIR/$BACKUP_SERVICE_UNIT" "$USER_UNIT_DIR/"
install -m 0644 "$GEN_DIR/$BACKUP_TIMER_UNIT" "$USER_UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now "$BACKUP_TIMER_UNIT"

# --- Report ---------------------------------------------------------------
say "Done. Current status:"
systemctl --user --no-pager status "$SOCKET_UNIT" || true
echo
echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket"
echo "activation). Make sure the backend + frontend build are up:"
echo "  (cd \"$SCRIPT_DIR/..\" && podman-compose up -d backend frontend-build)"
echo "To start at boot without an active login: loginctl enable-linger \"\$USER\""
echo
systemctl --user --no-pager status "$BACKUP_TIMER_UNIT" 2>/dev/null || true
echo
echo "Backup timer: fires daily (with a random delay), writing to $BACKUP_DIR."
echo "  To run a backup now:  systemctl --user start $BACKUP_SERVICE_UNIT"
echo "  To view logs:         journalctl --user -u $BACKUP_SERVICE_UNIT"
echo "  To list next run:     systemctl --user list-timers $BACKUP_TIMER_UNIT"
