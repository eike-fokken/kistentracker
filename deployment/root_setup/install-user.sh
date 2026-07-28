#!/usr/bin/env bash
#
# Install the socket-activated Caddy units AND the database backup timer into
# systemd. When run as a normal user it uses the rootless user manager
# (~/.config/systemd/user). When run as root it installs to system-wide paths
# (/etc/systemd/system). Idempotent: every run first tears down anything a
# previous run (or a previous attempt) installed, so it always ends on a clean
# slate.
#
# It installs the files currently in ./generated/ (produce them with
#   ./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180 \
#       --backup-dir /home/myuser/backups/kistentracker
#   # -- or without --user for system-wide installation:
#   ./generate.py --http-port 80 --https-port 443 --backend-port 8180 \
#       --backup-dir /some/path
# ).

set -euo pipefail

UNIT_NAME="${UNIT_NAME:-caddy}"
BACKUP_UNIT_NAME="${BACKUP_UNIT_NAME:-backup-db}"
BACKEND_UNIT_NAME="${BACKEND_UNIT_NAME:-backend}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN_DIR="$SCRIPT_DIR/generated"

if [[ "$(id -u)" -eq 0 ]]; then
	SYSTEM_UNIT=true
	UNIT_DIR="/etc/systemd/system"
	SYSTEMCTL="systemctl"
	CADDYFILE_BASE_DIR="/etc/caddy"
else
	SYSTEM_UNIT=false
	UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
	SYSTEMCTL="systemctl --user"
	CADDYFILE_BASE_DIR="$HOME/.config/caddy"
fi

SOCKET_UNIT="$UNIT_NAME.socket"
SERVICE_UNIT="$UNIT_NAME.service"
BACKUP_SERVICE_UNIT="$BACKUP_UNIT_NAME.service"
BACKUP_TIMER_UNIT="$BACKUP_UNIT_NAME.timer"
BACKEND_SERVICE_UNIT="$BACKEND_UNIT_NAME.service"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- Detect --run-as user (from User= in the generated caddy.service) ------
RUN_AS_USER=""
if $SYSTEM_UNIT && [[ -f "$GEN_DIR/$SERVICE_UNIT" ]]; then
	RUN_AS_USER="$(grep -oP '^User=\K.*' "$GEN_DIR/$SERVICE_UNIT" 2>/dev/null || echo "")"
fi

# --- Preconditions --------------------------------------------------------
MUST_EXIST=("$SOCKET_UNIT" "$SERVICE_UNIT" "Caddyfile.socket" "$BACKUP_SERVICE_UNIT" "$BACKUP_TIMER_UNIT")
# The backend unit is only required when it would actually be installed
# (user mode, or system mode with --run-as). In system root-only mode it's
# silently skipped.
if ! $SYSTEM_UNIT || [[ -n "$RUN_AS_USER" ]]; then
	MUST_EXIST+=("$BACKEND_SERVICE_UNIT")
fi
for f in "${MUST_EXIST[@]}"; do
	if [[ ! -f "$GEN_DIR/$f" ]]; then
		echo "error: $GEN_DIR/$f not found. Generate it first, e.g.:" >&2
		echo "  ./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180 --backup-dir /some/path" >&2
		exit 1
	fi
done

# Where the service mounts the Caddyfile -- for the generated Caddyfile copy
# destination we enforce the system/user split regardless of what the template
# baked in (the unit's mount path is separate and stays as-is).
CADDYFILE_DEST="$CADDYFILE_BASE_DIR/$UNIT_NAME.Caddyfile"

# --- Clean slate: remove anything a previous attempt left behind ----------
say "Tearing down any previous installation"
# Stop + disable (removes *.wants symlinks). Ignore errors if not present.
$SYSTEMCTL disable --now "$SOCKET_UNIT" "$SERVICE_UNIT" 2>/dev/null || true
$SYSTEMCTL disable --now "$BACKUP_TIMER_UNIT" "$BACKUP_SERVICE_UNIT" 2>/dev/null || true
# Teardown backend unit: user-manager in --run-as mode, system/user as-is otherwise.
if [[ -n "$RUN_AS_USER" ]]; then
	sudo -u "$RUN_AS_USER" systemctl --user disable --now "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
	sudo -u "$RUN_AS_USER" systemctl --user stop "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
	RUN_AS_HOME="$(sudo -u "$RUN_AS_USER" sh -c 'echo "$HOME"')"
	sudo rm -f "$RUN_AS_HOME/.config/systemd/user/$BACKEND_SERVICE_UNIT"
	sudo -u "$RUN_AS_USER" systemctl --user daemon-reload
else
	$SYSTEMCTL disable --now "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
	$SYSTEMCTL stop "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
	rm -f "$UNIT_DIR/$BACKEND_SERVICE_UNIT"
fi
$SYSTEMCTL stop "$SERVICE_UNIT" "$SOCKET_UNIT" 2>/dev/null || true
$SYSTEMCTL stop "$BACKUP_SERVICE_UNIT" "$BACKUP_TIMER_UNIT" 2>/dev/null || true
# Force-remove a leftover container so the fresh service can recreate it.
podman rm -f "$UNIT_NAME" 2>/dev/null || true
# Delete old unit files and Caddyfile.
rm -f "$UNIT_DIR/$SOCKET_UNIT" "$UNIT_DIR/$SERVICE_UNIT"
rm -f "$UNIT_DIR/$BACKUP_SERVICE_UNIT" "$UNIT_DIR/$BACKUP_TIMER_UNIT"
rm -f "$CADDYFILE_DEST"
$SYSTEMCTL daemon-reload

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

say "Installing units to $UNIT_DIR"
mkdir -p "$UNIT_DIR"
install -m 0644 "$GEN_DIR/$SOCKET_UNIT" "$UNIT_DIR/"
install -m 0644 "$GEN_DIR/$SERVICE_UNIT" "$UNIT_DIR/"

$SYSTEMCTL daemon-reload

say "Enabling and starting $SOCKET_UNIT"
$SYSTEMCTL enable --now "$SOCKET_UNIT"

# --- Install backend service ------------------------------------------------
say "Installing backend service"
if [[ -n "$RUN_AS_USER" ]]; then
	RUN_AS_HOME="$(sudo -u "$RUN_AS_USER" sh -c 'echo "$HOME"')"
	sudo -u "$RUN_AS_USER" mkdir -p "$RUN_AS_HOME/.config/systemd/user"
	sudo install -m 0644 "$GEN_DIR/$BACKEND_SERVICE_UNIT" "$RUN_AS_HOME/.config/systemd/user/"
	sudo -u "$RUN_AS_USER" systemctl --user daemon-reload
	sudo -u "$RUN_AS_USER" systemctl --user enable --now "$BACKEND_SERVICE_UNIT"
else
	install -m 0644 "$GEN_DIR/$BACKEND_SERVICE_UNIT" "$UNIT_DIR/"
	$SYSTEMCTL daemon-reload
	$SYSTEMCTL enable --now "$BACKEND_SERVICE_UNIT"
fi

# --- Install backup timer --------------------------------------------------
say "Installing backup timer"
install -m 0644 "$GEN_DIR/$BACKUP_SERVICE_UNIT" "$UNIT_DIR/"
install -m 0644 "$GEN_DIR/$BACKUP_TIMER_UNIT" "$UNIT_DIR/"
$SYSTEMCTL daemon-reload
$SYSTEMCTL enable --now "$BACKUP_TIMER_UNIT"

# --- Report ---------------------------------------------------------------
say "Done. Current status:"
$SYSTEMCTL --no-pager status "$SOCKET_UNIT" || true
echo
if [[ -n "$RUN_AS_USER" ]]; then
	sudo -u "$RUN_AS_USER" systemctl --user --no-pager status "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
elif $SYSTEM_UNIT; then
	$SYSTEMCTL --no-pager status "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
else
	$SYSTEMCTL --no-pager status "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
fi
echo
if $SYSTEM_UNIT && [[ -z "$RUN_AS_USER" ]]; then
	echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket"
	echo "activation). The backend unit starts independently on boot."
elif $SYSTEM_UNIT; then
	echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket"
	echo "activation). The backend unit runs in $RUN_AS_USER's user manager."
else
	echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket"
	echo "activation). The backend unit starts independently on boot."
	echo "To start at boot without an active login: loginctl enable-linger \"\$USER\""
fi
echo
$SYSTEMCTL --no-pager status "$BACKUP_TIMER_UNIT" 2>/dev/null || true
echo
echo "Backup timer: fires hourly (with a random delay), writing to $BACKUP_DIR."
echo "  To run a backup now:  $SYSTEMCTL start $BACKUP_SERVICE_UNIT"
echo "  To view logs:         journalctl ${SYSTEM_UNIT:+ -u $BACKUP_SERVICE_UNIT}"
echo "  To list next run:     $SYSTEMCTL list-timers $BACKUP_TIMER_UNIT"
if [[ -n "$RUN_AS_USER" ]]; then
	echo "  To view backend logs: sudo -u $RUN_AS_USER journalctl --user -u $BACKEND_SERVICE_UNIT"
elif $SYSTEM_UNIT; then
	echo "  To view backend logs: journalctl -u $BACKEND_SERVICE_UNIT"
else
	echo "  To view backend logs: journalctl --user -u $BACKEND_SERVICE_UNIT"
fi