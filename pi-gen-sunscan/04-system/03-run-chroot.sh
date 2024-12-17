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
/usr/local/bin/rename_hotspot.sh & exit 0
EOF

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
