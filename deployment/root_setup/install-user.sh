#!/usr/bin/env bash
#
# Install socket-activated Caddy units, backend service, and database backup
# timer into systemd. Works in two modes, detected from the generated units:
#
#   system mode (caddy.service has User=)  -- must run as root.
#   user mode   (caddy.service has no User=) -- runs as the target user.
#
# Idempotent: every run first tears down anything a previous run installed.

set -euo pipefail

UNIT_NAME="${UNIT_NAME:-caddy}"
BACKUP_UNIT_NAME="${BACKUP_UNIT_NAME:-backup-db}"
BACKEND_UNIT_NAME="${BACKEND_UNIT_NAME:-backend}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN_DIR="$SCRIPT_DIR/generated"

SOCKET_UNIT="$UNIT_NAME.socket"
SERVICE_UNIT="$UNIT_NAME.service"
BACKUP_SERVICE_UNIT="$BACKUP_UNIT_NAME.service"
BACKUP_TIMER_UNIT="$BACKUP_UNIT_NAME.timer"
BACKEND_SERVICE_UNIT="$BACKEND_UNIT_NAME.service"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- Mode detection from generated caddy.service ----------------------------
if [[ ! -f "$GEN_DIR/$SERVICE_UNIT" ]]; then
	echo "error: $GEN_DIR/$SERVICE_UNIT not found. Generate units first." >&2
	exit 1
fi

RUN_AS_USER=""
if grep -q '^User=' "$GEN_DIR/$SERVICE_UNIT" 2>/dev/null; then
	MODE="system"
	RUN_AS_USER="$(grep -oP '^User=\K.*' "$GEN_DIR/$SERVICE_UNIT")"
else
	MODE="user"
fi

if [[ "$MODE" == "system" ]] && [[ "$(id -u)" -ne 0 ]]; then
	echo "error: generated units are in system mode (have User=). Must run as root." >&2
	exit 1
fi

# --- Preconditions -----------------------------------------------------------
MUST_EXIST=("$SOCKET_UNIT" "$SERVICE_UNIT" "Caddyfile.socket" "$BACKEND_SERVICE_UNIT" "$BACKUP_SERVICE_UNIT" "$BACKUP_TIMER_UNIT")
for f in "${MUST_EXIST[@]}"; do
	if [[ ! -f "$GEN_DIR/$f" ]]; then
		echo "error: $GEN_DIR/$f not found. Generate it first, e.g.:" >&2
		echo "  ./generate.py --user --http-port 8080 --https-port 8443 --backup-dir /some/path" >&2
		exit 1
	fi
done

# --- Paths and commands per mode --------------------------------------------
if [[ "$MODE" == "system" ]]; then
	UNIT_DIR="/etc/systemd/system"
	SYSTEMCTL="systemctl"
	CADDYFILE_BASE_DIR="/etc/caddy"
	RUN_AS_HOME="$(sudo -u "$RUN_AS_USER" sh -c 'echo "$HOME"')"
	SYSTEMCTL_USER_CMD=(systemctl --machine="$RUN_AS_USER"@.host --user)
	BACKEND_UNIT_DIR="$RUN_AS_HOME/.config/systemd/user"
else
	UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
	SYSTEMCTL="systemctl --user"
	CADDYFILE_BASE_DIR="$HOME/.config/caddy"
	SYSTEMCTL_USER_CMD=(systemctl --user)
	BACKEND_UNIT_DIR="$UNIT_DIR"
fi

systemctl_user() { "${SYSTEMCTL_USER_CMD[@]}" "$@"; }

CADDYFILE_DEST="$CADDYFILE_BASE_DIR/$UNIT_NAME.Caddyfile"

# --- Clean slate -------------------------------------------------------------
say "Tearing down any previous installation"

# Caddy.
$SYSTEMCTL disable --now "$SOCKET_UNIT" "$SERVICE_UNIT" 2>/dev/null || true
$SYSTEMCTL stop "$SERVICE_UNIT" "$SOCKET_UNIT" 2>/dev/null || true
# Force-remove a leftover container so the fresh service can recreate it.
podman rm -f "$UNIT_NAME" 2>/dev/null || true
rm -f "$UNIT_DIR/$SOCKET_UNIT" "$UNIT_DIR/$SERVICE_UNIT"
rm -f "$CADDYFILE_DEST"

# Backend.
systemctl_user disable --now "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
systemctl_user stop "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
rm -f "$BACKEND_UNIT_DIR/$BACKEND_SERVICE_UNIT"
systemctl_user daemon-reload

# Backup timer.
systemctl_user disable --now "$BACKUP_TIMER_UNIT" "$BACKUP_SERVICE_UNIT" 2>/dev/null || true
systemctl_user stop "$BACKUP_SERVICE_UNIT" "$BACKUP_TIMER_UNIT" 2>/dev/null || true
rm -f "$BACKEND_UNIT_DIR/$BACKUP_SERVICE_UNIT" "$BACKEND_UNIT_DIR/$BACKUP_TIMER_UNIT"

$SYSTEMCTL daemon-reload

# Ensure the backup directory exists.
BACKUP_DIR="$(
	grep -oE -- "-v [^:]+:/backup" "$GEN_DIR/$BACKUP_SERVICE_UNIT" |
		head -n1 | sed -E 's/^-v //; s#:/backup$##'
)"
if [[ -n "$BACKUP_DIR" ]]; then
	say "Creating backup directory $BACKUP_DIR"
	if [[ "$MODE" == "system" ]]; then
		sudo -u "$RUN_AS_USER" install -d -m 0755 "$BACKUP_DIR"
	else
		install -d -m 0755 "$BACKUP_DIR"
	fi
fi

# --- Install fresh files -----------------------------------------------------
say "Installing Caddyfile to $CADDYFILE_DEST"
install -D -m 0644 "$GEN_DIR/Caddyfile.socket" "$CADDYFILE_DEST"

say "Installing caddy units to $UNIT_DIR"
mkdir -p "$UNIT_DIR"
install -m 0644 "$GEN_DIR/$SOCKET_UNIT" "$UNIT_DIR/"
install -m 0644 "$GEN_DIR/$SERVICE_UNIT" "$UNIT_DIR/"
$SYSTEMCTL daemon-reload
$SYSTEMCTL enable --now "$SOCKET_UNIT"

say "Installing backend service"
	if [[ "$MODE" == "system" ]]; then
		sudo -u "$RUN_AS_USER" mkdir -p "$BACKEND_UNIT_DIR"
		sudo -u "$RUN_AS_USER" install -m 0644 "$GEN_DIR/$BACKEND_SERVICE_UNIT" "$BACKEND_UNIT_DIR/"
	else
		mkdir -p "$BACKEND_UNIT_DIR"
		install -m 0644 "$GEN_DIR/$BACKEND_SERVICE_UNIT" "$BACKEND_UNIT_DIR/"
	fi
	systemctl_user daemon-reload
	systemctl_user enable --now "$BACKEND_SERVICE_UNIT"

say "Installing backup timer"
if [[ "$MODE" == "system" ]]; then
	sudo -u "$RUN_AS_USER" mkdir -p "$BACKEND_UNIT_DIR"
	sudo -u "$RUN_AS_USER" install -m 0644 "$GEN_DIR/$BACKUP_SERVICE_UNIT" "$BACKEND_UNIT_DIR/"
	sudo -u "$RUN_AS_USER" install -m 0644 "$GEN_DIR/$BACKUP_TIMER_UNIT" "$BACKEND_UNIT_DIR/"
else
	mkdir -p "$BACKEND_UNIT_DIR"
	install -m 0644 "$GEN_DIR/$BACKUP_SERVICE_UNIT" "$BACKEND_UNIT_DIR/"
	install -m 0644 "$GEN_DIR/$BACKUP_TIMER_UNIT" "$BACKEND_UNIT_DIR/"
fi
systemctl_user daemon-reload
systemctl_user enable --now "$BACKUP_TIMER_UNIT"

# --- Report ------------------------------------------------------------------
say "Done. Current status:"
$SYSTEMCTL --no-pager status "$SOCKET_UNIT" || true
echo
systemctl_user --no-pager status "$BACKEND_SERVICE_UNIT" 2>/dev/null || true
echo
if [[ "$MODE" == "system" ]]; then
	echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket activation)."
	echo "The backend unit runs in $RUN_AS_USER's user manager."
else
	echo "Note: $SERVICE_UNIT stays inactive until the first connection (socket activation)."
	echo "The backend unit starts independently on boot."
	echo 'To start at boot without an active login: loginctl enable-linger "$USER"'
fi
echo
systemctl_user --no-pager status "$BACKUP_TIMER_UNIT" 2>/dev/null || true
echo
echo "Backup timer: fires hourly (with a random delay), writing to $BACKUP_DIR."
echo "  To run a backup now:  ${SYSTEMCTL_USER_CMD[*]} start $BACKUP_SERVICE_UNIT"
echo "  To view logs:         ${SYSTEMCTL_USER_CMD[*]} -u $BACKUP_SERVICE_UNIT"
echo "  To list next run:     ${SYSTEMCTL_USER_CMD[*]} list-timers $BACKUP_TIMER_UNIT"
if [[ "$MODE" == "system" ]]; then
	echo "  To view backend logs: sudo -u $RUN_AS_USER journalctl --user -u $BACKEND_SERVICE_UNIT"
else
	echo "  To view backend logs: journalctl --user -u $BACKEND_SERVICE_UNIT"
fi