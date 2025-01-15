#!/bin/bash

# Patch firmware config

CONFIG_TXT=/boot/firmware/config.txt

sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' $CONFIG_TXT
sed -i 's/^disable_fw_kms_setup=1/disable_fw_kms_setup=0/' $CONFIG_TXT
sed -i '/^camera_auto_detect=1/a\dtoverlay=imx477' $CONFIG_TXT
sed -i '/^\[cm5\]/,/^dtoverlay=dwc2,dr_mode=host$/d' $CONFIG_TXT
if ! grep -q '^\[cm5\]' $CONFIG_TXT; then
    echo -e '[cm5]\ndtoverlay=dwc2,dr_mode=host' >> $CONFIG_TXT
fi