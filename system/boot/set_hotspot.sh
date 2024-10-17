#!/bin/bash

# go random
SSID="SunScan-$(cat /sys/firmware/devicetree/base/serial-number | tail -c -10)"

echo $SSID

# update wpa_supplicant
sudo sed -i "s/^ssid=.*/ssid=\"$SSID\"/" /etc/wpa_supplicant/wpa_supplicant.conf
