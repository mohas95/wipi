# wipi

default hostname: wipi.local



## Installation

```bash

git clone git@github.com:mohas95/wipi.git
cd wipi

chmod +x setup-pi-ethernet-gateway.sh
sudo ./setup-pi-ethernet-gateway.sh

chmod +x autohotspot.sh
sudo ln -s /home/pi/wipi/wipi-autohotspot.service /etc/systemd/system/wipi-autohotspot.service

```

##
``` bash
[Main WiFi Network]
        |
    (WiFi)
        |
   Raspberry Pi
   wlan0 -> internet
   eth0  -> shared LAN
        |
    Ethernet cable
        |
   Secondary Router
        |
   Devices
```