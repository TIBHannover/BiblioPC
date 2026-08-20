#!/bin/bash
# URL aus der una-config.json ermitteln
CONFIG_FILE="/usr/local/etc/una-config.json"
SERVER_URL=$(jq -r '.server_url' "$CONFIG_FILE")
LOGOUT_SCRIPT=$(jq -r '.logout_script' "$CONFIG_FILE")
LOGOUT_URL="${SERVER_URL}/${LOGOUT_SCRIPT}"

CLIENT_HOST="unknown"
CLIENT_IP="127.0.0.1"

if [ -f "/dev/shm/hostname" ]; then
    CLIENT_HOST=$(cat /dev/shm/hostname)
fi

if [ -f "/dev/shm/ip" ]; then
    CLIENT_IP=$(cat /dev/shm/ip)
fi

# Benutzer abmelden
curl -k -s -X POST "$LOGOUT_URL" -d "host=${CLIENT_HOST}" -d "ip=${CLIENT_IP}"

# Benutzernummer löschen
rm -rf /dev/shm/benutzernummer
rm -rf /dev/shm/hostname
rm -rf /dev/shm/ip

# Home una-user löschen
#rm -rf /home/una-user && mkdir /home/una-user
