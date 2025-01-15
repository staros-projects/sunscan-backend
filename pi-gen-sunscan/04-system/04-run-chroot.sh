#!/bin/bash

#sudo raspi-config nonint do_i2c 0
#depmod
#modprobe i2c-dev


wget http://cdn.pisugar.com/release/pisugar-server_2.0.0-1_arm64.deb
wget http://cdn.pisugar.com/release/pisugar-poweroff_2.0.0-1_arm64.deb
wget http://cdn.pisugar.com/release/pisugar-programmer_2.0.0-1_arm64.deb
dpkg -i pisugar-server_2.0.0-1_arm64.deb
dpkg -i pisugar-poweroff_2.0.0-1_arm64.deb
dpkg -i pisugar-programmer_2.0.0-1_arm64.deb
rm pisugar-server_2.0.0-1_arm64.deb
rm pisugar-poweroff_2.0.0-1_arm64.deb
rm pisugar-programmer_2.0.0-1_arm64.deb
