#!/usr/bin/env bash

WIFI_IF="wlan0"

HOTSPOT_NAME="WipiSetup"
HOTSPOT_SSID="WipiSetup"
HOTSPOT_PASS="configureme123"

CHECK_INTERVAL=60

has_internet() {
    ping -I "$WIFI_IF" -c 1 -W 3 8.8.8.8 >/dev/null 2>&1
}

hotspot_active() {
    nmcli -t -f NAME connection show --active | grep -q "^${HOTSPOT_NAME}$"
}

start_hotspot() {

    if hotspot_active; then
        echo "[wipi] Hotspot already active"
        return
    fi

    echo "[wipi] Starting hotspot"

    nmcli connection down "$HOTSPOT_NAME" >/dev/null 2>&1 || true
    nmcli connection delete "$HOTSPOT_NAME" >/dev/null 2>&1 || true

    nmcli device wifi hotspot \
        ifname "$WIFI_IF" \
        con-name "$HOTSPOT_NAME" \
        ssid "$HOTSPOT_SSID" \
        password "$HOTSPOT_PASS"
}

stop_hotspot() {

    if hotspot_active; then
        echo "[wipi] Stopping hotspot"

        nmcli connection down "$HOTSPOT_NAME" || true
    fi
}

connect_saved_wifi() {

    echo "[wipi] Trying saved WiFi profiles"

    nmcli radio wifi on

    nmcli device connect "$WIFI_IF" >/dev/null 2>&1 || true
}

echo "[wipi] AutoHotspot daemon started"

while true; do

    if has_internet; then

        echo "[wipi] Internet OK"

        stop_hotspot

    else

        echo "[wipi] Internet LOST"

        connect_saved_wifi

        sleep 15

        if has_internet; then

            echo "[wipi] Reconnected successfully"

            stop_hotspot

        else

            echo "[wipi] Failed to reconnect"

            start_hotspot
        fi
    fi

    sleep "$CHECK_INTERVAL"

done