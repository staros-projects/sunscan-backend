#!/bin/bash

#sudo raspi-config nonint do_i2c 0
#depmod
#modprobe i2c-dev


PISUGAR_VERSION=2.0.0-1

wget http://cdn.pisugar.com/release/pisugar-server_${PISUGAR_VERSION}_arm64.deb
wget http://cdn.pisugar.com/release/pisugar-poweroff_${PISUGAR_VERSION}_arm64.deb
wget http://cdn.pisugar.com/release/pisugar-programmer_${PISUGAR_VERSION}_arm64.deb
dpkg -i pisugar-server_${PISUGAR_VERSION}_arm64.deb
dpkg -i pisugar-poweroff_${PISUGAR_VERSION}_arm64.deb
dpkg -i pisugar-programmer_${PISUGAR_VERSION}_arm64.deb
rm pisugar-server_${PISUGAR_VERSION}_arm64.deb
rm pisugar-poweroff_${PISUGAR_VERSION}_arm64.deb
rm pisugar-programmer_${PISUGAR_VERSION}_arm64.deb
