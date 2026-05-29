#!/usr/bin/env bash
set -e

WAN_IF="wlan0"
LAN_IF="eth0"
LAN_IP="192.168.50.1"
LAN_CIDR="24"
DHCP_START="192.168.50.10"
DHCP_END="192.168.50.200"

echo "[1/7] Checking root..."
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo"
  exit 1
fi

echo "[2/7] Installing packages..."
apt update
apt install -y dnsmasq iptables-persistent netfilter-persistent

echo "[3/7] Enabling IPv4 forwarding..."
cat >/etc/sysctl.d/99-pi-gateway.conf <<EOF
net.ipv4.ip_forward=1
EOF
sysctl --system

echo "[4/7] Configuring static IP on $LAN_IF..."

if systemctl is-active --quiet NetworkManager; then
  echo "Detected NetworkManager."

  nmcli con delete pi-ethernet-gateway 2>/dev/null || true

  nmcli con add type ethernet \
    ifname "$LAN_IF" \
    con-name pi-ethernet-gateway \
    ipv4.method manual \
    ipv4.addresses "$LAN_IP/$LAN_CIDR" \
    ipv6.method disabled

  nmcli con up pi-ethernet-gateway

else
  echo "Using dhcpcd-style config."

  if ! grep -q "interface $LAN_IF" /etc/dhcpcd.conf; then
    cat >>/etc/dhcpcd.conf <<EOF

interface $LAN_IF
static ip_address=$LAN_IP/$LAN_CIDR
EOF
  fi

  systemctl restart dhcpcd || true
fi

echo "[5/7] Configuring dnsmasq DHCP on $LAN_IF..."
mkdir -p /etc/dnsmasq.d

# cat >/etc/dnsmasq.d/pi-ethernet-gateway.conf <<EOF
# interface=$LAN_IF
# bind-interfaces
# dhcp-range=$DHCP_START,$DHCP_END,255.255.255.0,24h
# dhcp-option=3,$LAN_IP
# dhcp-option=6,1.1.1.1,8.8.8.8
# EOF

cat >/etc/dnsmasq.d/pi-ethernet-gateway.conf <<EOF
interface=$LAN_IF
bind-interfaces
dhcp-range=$DHCP_START,$DHCP_END,255.255.255.0,24h
dhcp-option=3,$LAN_IP
dhcp-option=6,$LAN_IP
EOF

systemctl restart dnsmasq
systemctl enable dnsmasq

echo "[6/7] Configuring NAT firewall rules..."

iptables -t nat -C POSTROUTING -o "$WAN_IF" -j MASQUERADE 2>/dev/null || \
iptables -t nat -A POSTROUTING -o "$WAN_IF" -j MASQUERADE

iptables -C FORWARD -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT

iptables -C FORWARD -i "$WAN_IF" -o "$LAN_IF" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -i "$WAN_IF" -o "$LAN_IF" -m state --state RELATED,ESTABLISHED -j ACCEPT

netfilter-persistent save

echo "[7/7] Done."
echo
echo "Pi gateway configured:"
echo "  Internet side: $WAN_IF"
echo "  Router side:   $LAN_IF"
echo "  Pi LAN IP:     $LAN_IP"
echo "  DHCP range:    $DHCP_START - $DHCP_END"
echo
echo "Connect your router WAN port to the Pi Ethernet port."
echo "Set the router WAN/internet mode to DHCP."