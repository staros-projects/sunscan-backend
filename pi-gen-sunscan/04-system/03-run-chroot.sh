#!/bin/bash

# Configure Hotspot

cat << EOF > /usr/local/bin/rename_hotspot.sh
#!/bin/bash
CONNECTION_DIR="/etc/NetworkManager/system-connections/"
HOTSPOT_FILE=\$(grep -rl "ssid=sunscan-default" \$CONNECTION_DIR)

if [ -n "\$HOTSPOT_FILE" ]; then
    MAC_SUFFIX=\$(cat /sys/class/net/wlan0/address | sed 's/://g' | cut -c 7-12)
    NEW_SSID="sunscan-\$MAC_SUFFIX"
    sed -i "s/ssid=sunscan-default/ssid=\$NEW_SSID/" "\$HOTSPOT_FILE"
    chmod 600 "\$HOTSPOT_FILE"
    systemctl restart NetworkManager
fi
EOF

chmod +x /usr/local/bin/rename_hotspot.sh

cat << EOF > /etc/rc.local
#!/bin/sh -e
#
# rc.local
#
# This script is executed at the end of each multiuser runlevel.
# Make sure that the script will "exit 0" on success or any other
# value on error.
#
# In order to enable or disable this script just change the execution
# bits.
#
# By default this script does nothing.

# Print the IP address
_IP=\$(hostname -I) || true
if [ "\$_IP" ]; then
  printf "My IP address is %s\n" "\$_IP"
fi

EOF

chmod +x /etc/rc.local

cat << EOF > /var/www/sunscan-backend/reset_hotspot.sh
#!/bin/bash
CONNECTION_DIR="/etc/NetworkManager/system-connections/"
HOTSPOT_FILE=\$(grep -rl "ssid=sunscan-" \$CONNECTION_DIR)

if [ -n "\$HOTSPOT_FILE" ]; then
    MAC_SUFFIX=\$(cat /sys/class/net/wlan0/address | sed 's/://g' | cut -c 7-12)
    NEW_SSID="sunscan-default"
    sed -i "s/ssid=sunscan-\$MAC_SUFFIX/ssid=\$NEW_SSID/" "\$HOTSPOT_FILE"
    chmod 600 "\$HOTSPOT_FILE"
    systemctl restart NetworkManager
fi
EOF

chmod +x /var/www/sunscan-backend/reset_hotspot.sh

cat << EOF > /usr/local/bin/configure_hotspot.sh
#!/bin/bash

CONNECTION_DIR="/etc/NetworkManager/system-connections/"
HOTSPOT_FILE=\$(grep -rl "ssid=sunscan-" \$CONNECTION_DIR)

echo "Hotspot file: \$HOTSPOT_FILE"

if [ -f "\$HOTSPOT_FILE" ]; then
  echo "Hotspot already configured"
else
  nmcli radio wifi on

  INTERFACE="wlan0"

  # Configuration du hotspot
  SSID="sunscan-default"
  PASSWORD="SunScanByStaros"

  nmcli con add type wifi ifname "\$INTERFACE" con-name hotspot autoconnect yes ssid "\$SSID"
  nmcli con modify hotspot wifi-sec.key-mgmt wpa-psk wifi-sec.psk "\$PASSWORD"
  nmcli con modify hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
  nmcli con up hotspot
fi

/usr/local/bin/rename_hotspot.sh
EOF

chmod +x /usr/local/bin/configure_hotspot.sh

# Add systemd service to configure hotspot
cat << EOF > /etc/systemd/system/configure_hotspot.service
[Unit]
Description=Configure Hotspot
After=network.target

[Service]
ExecStart=/usr/local/bin/configure_hotspot.sh
Restart=on-failure
RestartSec=5s
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable configure_hotspot.service
