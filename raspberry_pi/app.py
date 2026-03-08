from flask import Flask, request, jsonify, render_template_string
import threading, asyncio
from bleak import BleakScanner, BleakClient

CMD_UUID  = "19B10001-E8F2-537E-4F6C-D104768A1214"
TELE_UUID = "19B10002-E8F2-537E-4F6C-D104768A1214"

app = Flask(__name__)

latest = {
    "ambient_light": None,
    "temperature_c": None,
    "humidity_percent": None,
    "light_range": None,
    "brightness_pwm": None,
    "mode": None,
    "ble": "disconnected",
    "raw": ""
}
lock = threading.Lock()

def parse_kv(line: str):
    out = {}
    for p in line.split(","):
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out
class BLEBridge:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.address = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self):
        while True:
            try:
                with lock:
                    latest["ble"] = "scanning"

                # Connect by fixed MAC (most reliable)
                    self.address = "08:EA:34:0C:EC:11"
                with lock:
                    latest["ble"] = f"connecting {self.address}"

                async with BleakClient(self.address) as client:
                    self.client = client
                    with lock:
                        latest["ble"] = "connected"

                    def on_notify(_, data: bytearray):
                        line = data.decode(errors="ignore").strip()
                        kv = parse_kv(line)
                        with lock:
                            latest["raw"] = line
                            latest["ambient_light"] = float(kv.get("ambient_light")) if kv.get("ambient_light") else latest["ambient_light"]
                            latest["temperature_c"] = float(kv.get("temperature_c")) if kv.get("temperature_c") else latest["temperature_c"]
                            latest["humidity_percent"] = float(kv.get("humidity_percent")) if kv.get("humidity_percent") else latest["humidity_percent"]
                            latest["light_range"] = kv.get("light_range", latest["light_range"])
                            if kv.get("brightness_pwm") is not None:
                                latest["brightness_pwm"] = int(float(kv.get("brightness_pwm")))
                            latest["mode"] = kv.get("mode", latest["mode"])

                    await client.start_notify(TELE_UUID, on_notify)

                    while client.is_connected:
                        await asyncio.sleep(1)

            except Exception as e:
                with lock:
                    latest["ble"] = f"error: {type(e).__name__}: {e}"
                await asyncio.sleep(5)

    def send(self, cmd: str):
        cmd = cmd.strip().upper()
        async def _write():
            if self.client and self.client.is_connected:
                await self.client.write_gatt_char(CMD_UUID, cmd.encode())
        asyncio.run_coroutine_threadsafe(_write(), self.loop)

bridge = BLEBridge()
HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Smart Lamp (BLE)</title>
  <style>
    body{font-family:Arial;max-width:640px;margin:40px auto;}
    .card{padding:18px;border:1px solid #ddd;border-radius:14px;}
    button{padding:10px 14px;margin-right:8px;border-radius:10px;border:1px solid #ccc;cursor:pointer;}
    input[type=range]{width:100%;}
    .row{margin-top:14px;}
    .kv{background:#f6f6f6;padding:10px;border-radius:10px;white-space:pre-wrap;}
    .small{color:#666;font-size:12px;}
  </style>
</head>
<body>
  <h2>Smart Lamp (BLE)</h2>
  <div class="card">
    <div class="row">
      <button onclick="sendCmd('AUTO')">AUTO</button>
      <button onclick="sendCmd('MANUAL')">MANUAL</button>
      <button onclick="sendCmd('RECAL')">RECAL</button>
      <button onclick="sendCmd('STATUS')">STATUS</button>
    </div>

    <div class="row">
      <label>Manual Brightness: <b id="val">160</b></label>
      <input id="rng" type="range" min="0" max="255" value="160"
             oninput="val.textContent=this.value"
             onchange="setBright(this.value)">
      <div class="small">BLE: <b id="ble">...</b></div>
    </div>

    <div class="row">
      <div class="kv" id="tele">loading...</div>
      <div class="small" id="raw">...</div>
    </div>
  </div>

<script>
async function setBright(v){
  await fetch('/brightness', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({value:parseInt(v)})});
}
async function sendCmd(c){
  await fetch('/cmd', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({cmd:c})});
}
async function refresh(){
  let r = await fetch('/telemetry');
  let j = await r.json();
  document.getElementById('ble').textContent = j.ble;
  document.getElementById('tele').textContent =
`ambient_light:    ${j.ambient_light}
temperature_c:    ${j.temperature_c}
humidity_percent: ${j.humidity_percent}
light_range:      ${j.light_range}
brightness_pwm:   ${j.brightness_pwm}
mode:             ${j.mode}`;
  document.getElementById('raw').textContent = "raw: " + j.raw;
}
setInterval(refresh, 500);
refresh();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/telemetry")
def telemetry():
    with lock:
        return jsonify(latest)

@app.route("/cmd", methods=["POST"])
def cmd():
    c = request.json.get("cmd", "").strip().upper()
    if c not in ("AUTO", "MANUAL", "RECAL", "STATUS"):
        return jsonify({"ok": False}), 400
    bridge.send(c)
    return jsonify({"ok": True})

@app.route("/brightness", methods=["POST"])
def brightness():
    v = int(request.json.get("value", 160))
    v = max(0, min(255, v))
    # If you want slider to force manual, uncomment next line:
    # bridge.send("MANUAL")
    bridge.send(f"SET {v}")
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
