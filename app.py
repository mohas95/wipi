from flask import Flask, request, jsonify, render_template_string
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
    }


def nmcli(args):
    return run(["nmcli"] + args)


HTML = """
<!doctype html>
<html>
<head>
  <title>Wipi Portal</title>
  <style>
    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; }
    input, button, select { width: 100%; padding: 10px; margin: 8px 0; }
    pre { background: #eee; padding: 12px; overflow: auto; }
  </style>
</head>
<body>
  <h1>Wipi Wi-Fi Portal</h1>

  <button onclick="scan()">Scan Wi-Fi</button>
  <select id="ssid"></select>

  <h2>Normal Wi-Fi</h2>
  <input id="password" type="password" placeholder="Wi-Fi password">
  <button onclick="connectPersonal()">Connect</button>

  <h2>WPA Enterprise</h2>
  <input id="ent_ssid" value="wpa.mcgill.ca" placeholder="Enterprise SSID">
  <input id="identity" placeholder="Username">
  <input id="ent_password" type="password" placeholder="Password">
  <button onclick="connectEnterprise()">Connect Enterprise</button>

  <h2>Controls</h2>
  <button onclick="status()">Status</button>
  <button onclick="hotspot()">Enter Hotspot Mode</button>

  <pre id="out"></pre>

<script>
async function api(url, data=null) {
  const opts = data ? {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  } : {};

  const res = await fetch(url, opts);
  const json = await res.json();
  document.getElementById("out").textContent = JSON.stringify(json, null, 2);
  return json;
}

async function scan() {
  const data = await api("/api/scan");

  const select = document.getElementById("ssid");
  select.innerHTML = "";

  for (const n of data.networks || []) {
    const opt = document.createElement("option");
    opt.value = n.ssid;
    opt.textContent = `${n.ssid} | ${n.signal}% | ch ${n.channel} | ${n.security}`;
    select.appendChild(opt);
  }
}

function connectPersonal() {
  api("/api/connect-personal", {
    ssid: document.getElementById("ssid").value,
    password: document.getElementById("password").value
  });
}

function connectEnterprise() {
  api("/api/connect-enterprise", {
    ssid: document.getElementById("ent_ssid").value,
    identity: document.getElementById("identity").value,
    password: document.getElementById("ent_password").value
  });
}

function hotspot() {
  api("/api/hotspot", {});
}

function status() {
  api("/api/status");
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/status")
def status():
    return jsonify({
        "devices": nmcli(["device", "status"]),
        "active_connections": nmcli(["connection", "show", "--active"]),
        "wifi_connections": nmcli(["connection", "show"]),
        "wlan0_ip": run(["ip", "addr", "show", WIFI_IF]),
    })


@app.route("/api/scan")
def scan():
    result = nmcli([
        "-t",
        "--escape", "no",
        "-f", "SSID,BSSID,SIGNAL,SECURITY,CHAN,FREQ,RATE",
        "device", "wifi", "list",
        "ifname", WIFI_IF,
        "--rescan", "yes"
    ])

    networks = []

    for line in result["stdout"].splitlines():
        parts = line.split(":", 6)

        if len(parts) < 7:
            continue

        ssid, bssid, signal, security, channel, freq, rate = parts

        if not ssid:
            ssid = "<hidden>"

        networks.append({
            "ssid": ssid,
            "bssid": bssid,
            "signal": signal,
            "security": security,
            "channel": channel,
            "frequency": freq,
            "rate": rate,
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

    nmcli(["connection", "down", HOTSPOT_NAME])

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

    nmcli(["connection", "down", HOTSPOT_NAME])
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


@app.route("/api/hotspot", methods=["POST"])
def hotspot():
    result = nmcli(["connection", "up", HOTSPOT_NAME])
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)