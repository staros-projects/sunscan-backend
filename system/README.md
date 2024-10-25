# Sunscan OS Delivery Procedure for Raspberry Pi 4

This document outlines the steps required to prepare and deliver the Sunscan OS for Raspberry Pi 4. Follow the instructions carefully to reset the hotspot SSID, clean up storage, and create a compressed OS image.

## 1. Reset Hotspot SSID on Raspberry Pi 4

On the Raspberry Pi 4, execute the following commands to reset the SSID for the Sunscan hotspot:

```bash
admin@sunscan:/var/www/sunscan-backend $ sudo sh reset_hotspot.sh
```

This command resets the hotspot SSID to its default configuration.

## 2. Clear Application Storage

To remove all files from the Sunscan app's storage, run:

```bash
admin@sunscan:/var/www/sunscan-backend $ sudo rm -Rf app/storage/scans/*
admin@sunscan:/var/www/sunscan-backend $ sudo rm -Rf app/storage/snapshots/*
admin@sunscan:/var/www/sunscan-backend $ sudo rm -Rf app/storage/tmp/*
```

This command ensures that the storage is cleared before creating the OS image.

## 3. Empty Trash

Empty the trash to ensure that no unnecessary files are left behind:

```bash
rm -rf ~/.local/share/Trash/*
```

## 4. Prepare and Shrink Sunscan OS Image on Linux

With the Raspberry Pi SD card connected to a Linux machine, follow these steps:

### 4.1 Download and Install PiShrink

PiShrink is used to reduce the size of the OS image for easier distribution. Download and install PiShrink using the following commands:

```bash
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh
sudo mv pishrink.sh /usr/local/bin
```

### 4.2 Create and Shrink the OS Image

Create an OS image from the Raspberry Pi SD card and shrink it using PiShrink:

1. **Create the image**:

   Replace `/dev/sdb` with the correct device path of your SD card (you can verify the path using `lsblk` or `df -h` commands):

   ```bash
   sudo dd bs=4M if=/dev/sdb status=progress > /media/gbertrand/Samsung_T5/sunscan_os.img
   ```

   This command creates the raw image file `sunscan_os.img` from the SD card and stores it in `/media/gbertrand/Samsung_T5/`.

2. **Shrink the image**:

   Navigate to the location of the saved image:

   ```bash
   cd /media/gbertrand/Samsung_T5/
   ```

   Shrink the image with PiShrink:

   ```bash
   sudo pishrink.sh -Z sunscan_os_20240803.img
   ```

   This command compresses the OS image to optimize its size.

---

Once these steps are completed, the Sunscan OS image is ready for distribution.

