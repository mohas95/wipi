from flask import Flask, request, jsonify, render_template
import subprocess

app = Flask(__name__)

WIFI_IF = "wlan0"
HOTSPOT_NAME = "WipiSetup"


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


@app.route("/api/status")
def status():
    return jsonify({
        "devices": nmcli(["device", "status"]),
        "active": nmcli(["connection", "show", "--active"]),
        "connections": nmcli(["connection", "show"]),
        "wlan0": run(["ip", "addr", "show", WIFI_IF]),
    })


@app.route("/api/scan")
def scan():
    result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "SSID,BSSID,SIGNAL,SECURITY,CHAN,FREQ",
        "device", "wifi", "list",
        "ifname", WIFI_IF,
        "--rescan", "yes"
    ])

    networks = []

    for line in result["stdout"].splitlines():
        parts = line.split(":", 5)
        if len(parts) < 6:
            continue

        ssid, bssid, signal, security, channel, freq = parts

        networks.append({
            "ssid": ssid if ssid else "<hidden>",
            "bssid": bssid,
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

    result = nmcli([
        "device", "wifi", "connect", ssid,
        "password", password,
        "ifname", WIFI_IF
    ])

    return jsonify(result)


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

    return jsonify({
        "create": create,
        "config": config,
        "up": up
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
    Deletes active Wi-Fi client profiles.
    The autohotspot daemon should then notice no internet and start WipiSetup.
    """
    active = nmcli(["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])

    deleted = []

    for line in active["stdout"].splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue

        name, ctype, device = parts[0], parts[1], parts[2]

        if ctype == "wifi" and device == WIFI_IF and name != HOTSPOT_NAME:
            deleted.append({
                "name": name,
                "result": nmcli(["connection", "delete", name])
            })

    return jsonify({
        "ok": True,
        "message": "Deleted active Wi-Fi profile(s). Autohotspot daemon should start setup hotspot shortly.",
        "deleted": deleted
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)