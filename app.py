from flask import Flask, request, jsonify, render_template
import subprocess

app = Flask(__name__)

WIFI_IF = "wlan0"
HOTSPOT_NAME = "WipiSetup"

LAN_IF = "eth0"
DNSMASQ_LEASES = "/var/lib/misc/dnsmasq.leases"

def get_active_wifi_ssid():
    result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "ACTIVE,SSID",
        "device", "wifi",
        "list",
        "ifname", WIFI_IF
    ])

    for line in result["stdout"].splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[0] == "yes":
            return parts[1]

    return None

def get_ipv4(interface):
    result = run(["ip", "-4", "addr", "show", interface])
    for line in result["stdout"].splitlines():
        line = line.strip()
        if line.startswith("inet "):
            return line.split()[1]
    return None


def run(cmd):
    r = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout.strip(),
        "stderr": r.stderr.strip(),
        "code": r.returncode,
        "cmd": " ".join(cmd),
    }


def nmcli(args):
    return run(["nmcli"] + args)


@app.route("/")
def index():
    return render_template("index.html")



@app.route("/api/network-info")
def network_info():
    leases = []

    try:
        with open(DNSMASQ_LEASES, "r") as f:
            for line in f.readlines():
                parts = line.strip().split()
                if len(parts) >= 4:
                    leases.append({
                        "expires": parts[0],
                        "mac": parts[1],
                        "ip": parts[2],
                        "hostname": parts[3],
                    })
    except FileNotFoundError:
        pass

    neigh_result = run(["ip", "neigh", "show", "dev", LAN_IF])

    neighbors = []
    for line in neigh_result["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 5:
            neighbors.append({
                "ip": parts[0],
                "mac": parts[4],
                "state": parts[-1],
            })

    return jsonify({
        "ok": True,
        "wifi": {
            "interface": WIFI_IF,
            "ip": get_ipv4(WIFI_IF),
            "ssid": get_active_wifi_ssid(),
        },
        "ethernet": {
            "interface": LAN_IF,
            "ip": get_ipv4(LAN_IF),
            "dhcp_leases": leases,
            "neighbors": neighbors,
        }
    })

@app.route("/api/status")
def status():

    device_result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "DEVICE,TYPE,STATE,CONNECTION",
        "device", "status"
    ])

    active_result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "NAME,TYPE,DEVICE",
        "connection", "show", "--active"
    ])

    devices = []

    for line in device_result["stdout"].splitlines():
        parts = line.split(":", 3)

        if len(parts) < 4:
            continue

        device, dtype, state, connection = parts

        devices.append({
            "device": device,
            "type": dtype,
            "state": state,
            "connection": connection
        })

    active_connections = []

    for line in active_result["stdout"].splitlines():
        parts = line.split(":", 2)

        if len(parts) < 3:
            continue

        name, ctype, device = parts

        active_connections.append({
            "name": name,
            "type": ctype,
            "device": device
        })

    ip_result = run(["hostname", "-I"])

    return jsonify({
        "ok": True,
        "internet_connected": any(
            d["device"] == WIFI_IF and "connected" in d["state"]
            for d in devices
        ),
        "devices": devices,
        "active_connections": active_connections,
        "ip_addresses": ip_result["stdout"].split(),
    })


@app.route("/api/connections")
def connections():
    result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "NAME,TYPE,DEVICE,AUTOCONNECT",
        "connection", "show"
    ])

    connections = []

    for line in result["stdout"].splitlines():
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue

        name, ctype, device, autoconnect = parts

        if ctype in ("wifi", "802-11-wireless"):
            connections.append({
                "name": name,
                "type": ctype,
                "device": device,
                "autoconnect": autoconnect,
                "active": device == WIFI_IF
            })

    return jsonify({
        "ok": result["ok"],
        "connections": connections,
        "raw": result["stdout"],
        "stderr": result["stderr"],
    })


@app.route("/api/scan")
def scan():
    result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "SSID,SIGNAL,SECURITY,CHAN,FREQ",
        "device", "wifi", "list",
        "ifname", WIFI_IF,
        "--rescan", "yes"
    ])

    networks = []

    for line in result["stdout"].splitlines():
        parts = line.split(":", 4)

        if len(parts) < 5:
            continue

        ssid, signal, security, channel, freq = parts

        networks.append({
            "ssid": ssid if ssid else "<hidden>",
            "signal": signal,
            "security": security,
            "channel": channel,
            "frequency": freq,
        })

    return jsonify({
        "ok": result["ok"],
        "count": len(networks),
        "networks": networks,
        "raw": result["stdout"],
        "stderr": result["stderr"],
    })

@app.route("/api/connect-personal", methods=["POST"])
def connect_personal():
    data = request.json or {}

    ssid = data.get("ssid")
    password = data.get("password")

    if not ssid or ssid == "<hidden>" or not password:
        return jsonify({"ok": False, "error": "SSID and password required"}), 400

    con_name = f"wifi-{ssid}"

    nmcli(["connection", "delete", con_name])

    create = nmcli([
        "connection", "add",
        "type", "wifi",
        "ifname", WIFI_IF,
        "con-name", con_name,
        "ssid", ssid
    ])

    config = nmcli([
        "connection", "modify", con_name,
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.psk", password,
        "ipv4.method", "auto",
        "ipv6.method", "ignore",
        "connection.autoconnect", "yes"
    ])

    up = nmcli(["connection", "up", con_name])

    hotspot_delete = None

    if up["ok"]:
        hotspot_delete = nmcli(["connection", "delete", HOTSPOT_NAME])

    return jsonify({
        "create": create,
        "config": config,
        "up": up,
        "hotspot_delete": hotspot_delete
    })



@app.route("/api/connect-enterprise", methods=["POST"])
def connect_enterprise():
    data = request.json or {}

    ssid = data.get("ssid")
    identity = data.get("identity")
    password = data.get("password")

    if not ssid or not identity or not password:
        return jsonify({"ok": False, "error": "SSID, identity, password required"}), 400

    con_name = f"enterprise-{ssid}"

    nmcli(["connection", "delete", con_name])

    create = nmcli([
        "connection", "add",
        "type", "wifi",
        "ifname", WIFI_IF,
        "con-name", con_name,
        "ssid", ssid
    ])

    config = nmcli([
        "connection", "modify", con_name,
        "wifi-sec.key-mgmt", "wpa-eap",
        "802-1x.eap", "peap",
        "802-1x.phase2-auth", "mschapv2",
        "802-1x.identity", identity,
        "802-1x.password", password,
        "802-1x.system-ca-certs", "yes",
        "ipv4.method", "auto",
        "ipv6.method", "ignore",
        "connection.autoconnect", "yes"
    ])

    up = nmcli(["connection", "up", con_name])

    hotspot_delete = None

    if up["ok"]:
        hotspot_delete = nmcli(["connection", "delete", HOTSPOT_NAME])

    return jsonify({
        "create": create,
        "config": config,
        "up": up,
        "hotspot_delete": hotspot_delete
    })

@app.route("/api/forget", methods=["POST"])
def forget():
    data = request.json or {}
    name = data.get("name")

    if not name:
        return jsonify({"ok": False, "error": "connection name required"}), 400

    result = nmcli(["connection", "delete", name])

    return jsonify(result)


@app.route("/api/enter-setup-mode", methods=["POST"])
def enter_setup_mode():
    """
    Deletes all saved Wi-Fi client profiles except the hotspot profile.
    The autohotspot daemon should then start WipiSetup.
    """
    result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "NAME,TYPE",
        "connection", "show"
    ])

    deleted = []

    for line in result["stdout"].splitlines():
        parts = line.split(":", 1)
        if len(parts) < 2:
            continue

        name, ctype = parts

        if ctype in ("wifi", "802-11-wireless") and name != HOTSPOT_NAME:
            deleted.append({
                "name": name,
                "result": nmcli(["connection", "delete", name])
            })

    return jsonify({
        "ok": True,
        "message": "Deleted saved Wi-Fi profile(s). Autohotspot should start WipiSetup shortly.",
        "deleted": deleted,
        "raw": result["stdout"],
        "stderr": result["stderr"],
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)