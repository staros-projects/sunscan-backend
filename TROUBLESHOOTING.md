# Troubleshooting Guide

## Hacker's Toolbox

### Manipulate the uvicorn service

Check if the service is running

```shell
systemctl status uvicorn.service
```

Restart the service

```shell
systemctl restart uvicorn.service
```

### View logs

To see only the uvicorn logs:

```shell
journalctl -u uvicorn.service --follow
```

To see all mixed logs:

```shell
journalctl --follow
```

## Hotspot Issue

If you see an error message like:

Warning: There is another connection with the name 'hotspot'. Reference the connection by its uuid '3fe517e1-ffff-4eb5-8631-1f8a8b2cacde'

there are too many configured hotspots. Clean them up with:

```shell
sudo nmtui
```

Edit a connection > Wi-Fi > hotspot (function <Delete>)

Once the hotspot is properly configured, you should see:

```shell
$ nmcli device
DEVICE         TYPE      STATE                   CONNECTION         
wlan0          wifi      connected               hotspot            
eth0           ethernet  connected               Wired connection 1 
lo             loopback  connected (externally)  lo    
```

## Camera Issue

If you have an issue with "self._picam2 = Picamera2(tuning=tuning)"
it might be a problem with a poorly connected ribbon cable, for example. You can use the following command to see if the system recognizes the camera:

```shell
$ libcamera-hello --list-cameras
Available cameras
-----------------
0 : imx477 [4056x3040 12-bit RGGB] (/base/axi/pcie@120000/rp1/i2c@80000/imx477@1a)
    Modes: 'SRGGB10_CSI2P' : 1332x990 [30.00 fps - (65535, 65535)/65535x65535 crop]
           'SRGGB12_CSI2P' : 2028x1080 [30.00 fps - (65535, 65535)/65535x65535 crop]
                             2028x1520 [30.00 fps - (65535, 65535)/65535x65535 crop]
                             4056x3040 [30.00 fps - (65535, 65535)/65535x65535 crop]
```

If the camera is poorly connected, it might either not respond or add a message such as "Could not open any dmaHeap device". In this case, check the ribbon cable connection.
