from flask import Flask, request, jsonify, render_template_string
import subprocess
import shlex

app = Flask(__name__)

HOTSPOT_SSID = "WipiSetup"
HOTSPOT_PASSWORD = "configureme123"
WIFI_IFACE = "wlan0"


def run(cmd):
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "code": result.returncode,
    }


def nmcli(args):
    return run(["nmcli"] + args)


@app.route("/")
def index():
    return render_template_string("""
<!doctype html>
<html>
<head>
  <title>Wipi Setup</title>
  <style>
    body { font-family: sans-serif; max-width: 700px; margin: 40px auto; }
    input, select, button { width: 100%; padding: 10px; margin: 8px 0; }
    pre { background: #eee; padding: 12px; overflow: auto; }
  </style>
</head>
<body>
  <h1>Wipi Wi-Fi Setup</h1>

  <button onclick="scan()">Scan Wi-Fi</button>
  <select id="ssid"></select>

  <h2>WPA/WPA2 Personal</h2>
  <input id="password" type="password" placeholder="Wi-Fi password">
  <button onclick="connectPersonal()">Connect Personal Wi-Fi</button>

  <h2>WPA Enterprise</h2>
  <input id="enterprise_ssid" placeholder="Enterprise SSID">
  <input id="identity" placeholder="Username / identity">
  <input id="enterprise_password" type="password" placeholder="Enterprise password">
  <button onclick="connectEnterprise()">Connect WPA Enterprise</button>

  <h2>Status</h2>
  <button onclick="status()">Refresh Status</button>
  <button onclick="hotspot()">Start Setup Hotspot</button>

  <pre id="output"></pre>

<script>
async function post(url, data={}) {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });
  document.getElementById("output").textContent =
    JSON.stringify(await res.json(), null, 2);
}

async function scan() {
  const res = await fetch("/api/scan");
  const data = await res.json();
  document.getElementById("output").textContent = JSON.stringify(data, null, 2);

  const select = document.getElementById("ssid");
  select.innerHTML = "";
  for (const net of data.networks || []) {
    const opt = document.createElement("option");
    opt.value = net.ssid;
    opt.textContent = `${net.ssid} (${net.signal}%)`;
    select.appendChild(opt);
  }
}

async function status() {
  const res = await fetch("/api/status");
  document.getElementById("output").textContent =
    JSON.stringify(await res.json(), null, 2);
}

function connectPersonal() {
  post("/api/connect-personal", {
    ssid: document.getElementById("ssid").value,
    password: document.getElementById("password").value
  });
}

function connectEnterprise() {
  post("/api/connect-enterprise", {
    ssid: document.getElementById("enterprise_ssid").value,
    identity: document.getElementById("identity").value,
    password: document.getElementById("enterprise_password").value
  });
}

function hotspot() {
  post("/api/hotspot");
}
</script>
</body>
</html>
""")


@app.route("/api/status")
def status():
    return jsonify({
        "device": nmcli(["device", "status"]),
        "connections": nmcli(["connection", "show", "--active"]),
        "ip": run(["ip", "addr", "show", WIFI_IFACE]),
    })


@app.route("/api/scan")
def scan():
    nmcli(["device", "wifi", "rescan", "ifname", WIFI_IFACE])

    result = nmcli([
        "-t",
        "-f",
        "SSID,SIGNAL,SECURITY",
        "device",
        "wifi",
        "list",
        "ifname",
        WIFI_IFACE
    ])

    networks = []
    for line in result["stdout"].splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            ssid = parts[0].strip()
            signal = parts[1].strip()
            security = ":".join(parts[2:]).strip()
            if ssid:
                networks.append({
                    "ssid": ssid,
                    "signal": signal,
                    "security": security
                })

    return jsonify({"ok": result["ok"], "networks": networks})


@app.route("/api/connect-personal", methods=["POST"])
def connect_personal():
    data = request.json
    ssid = data.get("ssid")
    password = data.get("password")

    if not ssid or not password:
        return jsonify({"ok": False, "error": "SSID and password required"}), 400

    con_name = f"wifi-{ssid}"

    nmcli(["connection", "delete", con_name])

    result = nmcli([
        "device", "wifi", "connect", ssid,
        "password", password,
        "ifname", WIFI_IFACE,
        "name", con_name
    ])

    return jsonify(result)


@app.route("/api/connect-enterprise", methods=["POST"])
def connect_enterprise():
    data = request.json
    ssid = data.get("ssid")
    identity = data.get("identity")
    password = data.get("password")

    if not ssid or not identity or not password:
        return jsonify({
            "ok": False,
            "error": "SSID, identity, and password required"
        }), 400

    con_name = f"enterprise-{ssid}"

    nmcli(["connection", "delete", con_name])

    create = nmcli([
        "connection", "add",
        "type", "wifi",
        "ifname", WIFI_IFACE,
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
        "ipv4.method", "auto",
        "ipv6.method", "ignore"
    ])

    up = nmcli(["connection", "up", con_name])

    return jsonify({
        "create": create,
        "config": config,
        "up": up
    })


@app.route("/api/hotspot", methods=["POST"])
def hotspot():
    nmcli(["connection", "down", "WipiSetup"])
    nmcli(["connection", "delete", "WipiSetup"])

    result = nmcli([
        "device", "wifi", "hotspot",
        "ifname", WIFI_IFACE,
        "con-name", "WipiSetup",
        "ssid", HOTSPOT_SSID,
        "password", HOTSPOT_PASSWORD
    ])

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)