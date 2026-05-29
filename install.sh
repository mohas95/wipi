#!/usr/bin/env bash
set -e

echo "[1/9] Checking root..."

if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo:"
    echo "  sudo ./install.sh"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

cd "$PROJECT_DIR"

echo "[2/9] Installing Python venv dependencies..."

apt update
apt install -y python3-venv python3-pip

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install --upgrade -r "$PROJECT_DIR/requirements.txt"

echo "[3/9] Installing Ethernet gateway..."

chmod +x "$PROJECT_DIR/setup-pi-ethernet-gateway.sh"
"$PROJECT_DIR/setup-pi-ethernet-gateway.sh"

echo "[4/9] Installing autohotspot script..."

chmod +x "$PROJECT_DIR/autohotspot.sh"

echo "[5/9] Installing systemd services..."

ln -sf \
    "$PROJECT_DIR/wipi-autohotspot.service" \
    /etc/systemd/system/wipi-autohotspot.service

ln -sf \
    "$PROJECT_DIR/wipi-portal.service" \
    /etc/systemd/system/wipi-portal.service

echo "[6/9] Reloading systemd..."

systemctl daemon-reload

echo "[7/9] Enabling services..."

systemctl enable wipi-autohotspot
systemctl enable wipi-portal

echo "[8/9] Starting services..."

systemctl restart wipi-autohotspot
systemctl restart wipi-portal

echo "[9/9] Service status..."

echo
systemctl --no-pager --full status wipi-autohotspot || true

echo
systemctl --no-pager --full status wipi-portal || true

echo
echo "Installation complete."
echo
echo "Portal should be available at:"
echo "  http://$(hostname -I | awk '{print $1}')"