#!/bin/bash
# Zentraler Reset nach dem Logout einer GDM-Benutzer-Session. Ersetzt den in Ubuntu 26.04 entfernten GDM-PostSession-Hook. -- 16.10.2026

set -u

LOG_FILE="/var/log/una-reset.log"
LOCK_FILE="/run/lock/una-reset.lock"

log() {
    printf '%s [%s] %s\n' \
        "$(date --iso-8601=seconds)" \
        "${PAM_USER:-unknown}" \
        "$*" >> "$LOG_FILE"
}

# Nur beim Schließen einer PAM-Session ausführen
if [ "${PAM_TYPE:-}" != "close_session" ]; then
    log "SKIP: PAM_TYPE=${PAM_TYPE:-unset}"
    exit 0
fi

# Nur für echte GDM-Benutzeranmeldungen ausführen.
# gdm-launch-environment ist die Session des GDM-Greeters und muss ausgeschlossen werden.
case "${PAM_SERVICE:-}" in
    gdm-password|gdm-autologin)
        ;;
    *)
        log "SKIP: PAM_SERVICE=${PAM_SERVICE:-unset} PAM_TYPE=${PAM_TYPE:-unset}"
        exit 0
        ;;
esac

# Gleichzeitige oder doppelte Ausführungen verhindern
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "SKIP: another una-reset is already running"
    exit 0
fi

# Konfiguration lesen
CONFIG_FILE="/usr/local/etc/una-config.json"

if [ ! -r "$CONFIG_FILE" ]; then
    log "ERROR: config file not readable: $CONFIG_FILE"
    exit 1
fi

SERVER_URL="$(jq -r '.server_url // empty' "$CONFIG_FILE")"
LOGOUT_SCRIPT="$(jq -r '.logout_script // empty' "$CONFIG_FILE")"

if [ -z "$SERVER_URL" ] || [ -z "$LOGOUT_SCRIPT" ]; then
    log "ERROR: server_url or logout_script missing in $CONFIG_FILE"
    exit 1
fi

LOGOUT_URL="${SERVER_URL}/${LOGOUT_SCRIPT}"

# Client-Daten aus der Session lesen
CLIENT_HOST="unknown"
CLIENT_IP="127.0.0.1"

if [ -r /dev/shm/hostname ]; then
    CLIENT_HOST="$(cat /dev/shm/hostname)"
fi

if [ -r /dev/shm/ip ]; then
    CLIENT_IP="$(cat /dev/shm/ip)"
fi

log "START host=$CLIENT_HOST ip=$CLIENT_IP url=$LOGOUT_URL"

# Server über den Logout informieren
RESPONSE_FILE="$(mktemp /tmp/una-reset-response.XXXXXX)"

HTTP_CODE="$(curl -k -sS -o "$RESPONSE_FILE" \
    -w '%{http_code}' \
    --max-time 10 \
    -X POST "$LOGOUT_URL" \
    -d "host=${CLIENT_HOST}" \
    -d "ip=${CLIENT_IP}" 2>>"$LOG_FILE")"
CURL_RC=$?

RESPONSE_TEXT="$(tr '\n' ' ' < "$RESPONSE_FILE" 2>/dev/null || true)"
rm -f "$RESPONSE_FILE"

log "CURL rc=$CURL_RC http=$HTTP_CODE response=$RESPONSE_TEXT"

# Lokale Session-Daten entfernen
rm -f /dev/shm/benutzernummer
rm -f /dev/shm/hostname
rm -f /dev/shm/ip

log "DONE"
exit 0
