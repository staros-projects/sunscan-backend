#!/bin/bash
CONNECTION_DIR="/etc/NetworkManager/system-connections/"
HOTSPOT_FILE=$(grep -rl "ssid=sunscan-" $CONNECTION_DIR)

if [ -n "$HOTSPOT_FILE" ]; then
    MAC_SUFFIX=$(cat /sys/class/net/wlan0/address | sed 's/://g' | cut -c 7-12)
    NEW_SSID="sunscan-default"
    sed -i "s/ssid=sunscan-$MAC_SUFFIX/ssid=$NEW_SSID/" "$HOTSPOT_FILE"
    chmod 600 "$HOTSPOT_FILE"
    systemctl restart NetworkManager
fi
