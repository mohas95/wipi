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


@app.route("/")
def index():
    return render_template_string("""
<!doctype html>
<html>
<head>
  <title>Wipi Portal</title>
  <style>
    body { font-family: sans-serif; max-width: 700px; margin: 40px auto; }
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
  <input id="ent_ssid" value="wpa.mcgill.ca" placeholder="SSID">
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
  document.getElementById("out").textContent =
    JSON.stringify(await res.json(), null, 2);
}

async function scan() {
  const res = await fetch("/api/scan");
  const data = await res.json();
  document.getElementById("out").textContent = JSON.stringify(data, null, 2);

  const select = document.getElementById("ssid");
  select.innerHTML = "";
  for (const n of data.networks || []) {
    const opt = document.createElement("option");
    opt.value = n.ssid;
    opt.textContent = `${n.ssid} (${n.signal}%) ${n.security}`;
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
""")


@app.route("/api/status")
def status():
    return jsonify({
        "devices": nmcli(["device", "status"]),
        "active_connections": nmcli(["connection", "show", "--active"]),
        "wlan0_ip": run(["ip", "addr", "show", WIFI_IF]),
    })


@app.route("/api/scan")
def scan():
    nmcli(["device", "wifi", "rescan", "ifname", WIFI_IF])

    result = nmcli([
        "-t",
        "-f", "SSID,SIGNAL,SECURITY",
        "device", "wifi", "list",
        "ifname", WIFI_IF
    ])

    networks = []
    for line in result["stdout"].splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0]:
            networks.append({
                "ssid": parts[0],
                "signal": parts[1],
                "security": ":".join(parts[2:])
            })

    return jsonify({"ok": result["ok"], "networks": networks})


@app.route("/api/connect-personal", methods=["POST"])
def connect_personal():
    data = request.json or {}
    ssid = data.get("ssid")
    password = data.get("password")

    if not ssid or not password:
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