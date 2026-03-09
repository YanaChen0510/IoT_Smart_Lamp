import asyncio
import json
from aiocoap import resource, Context, Message, GET, POST
import urllib.request

PI_HTTP_BASE = "http://127.0.0.1:5000"  # reuse existing Flask app

def http_get(path: str) -> dict:
    with urllib.request.urlopen(PI_HTTP_BASE + path, timeout=2) as r:
        return json.loads(r.read().decode())

def http_post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        PI_HTTP_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read().decode())

class Telemetry(resource.ObservableResource):
    def __init__(self):
        super().__init__()
        self._cache = None
        asyncio.create_task(self._poll())

    async def _poll(self):
        # Poll Flask telemetry and notify observers if changed
        while True:
            try:
                data = http_get("/telemetry")
                if data != self._cache:
                    self._cache = data
                    self.updated_state()  # CoAP Observe notify
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def render_get(self, request):
        data = http_get("/telemetry")
        payload = json.dumps(data).encode()
        return Message(payload=payload, content_format=50)  # 50 = application/json

class Mode(resource.Resource):
    async def render_post(self, request):
        cmd = request.payload.decode().strip().upper()
        if cmd not in ("AUTO", "MANUAL"):
            return Message(code=resource.aiocoap.numbers.codes.Code.BAD_REQUEST, payload=b"Use AUTO or MANUAL")
        http_post("/cmd", {"cmd": cmd})
        return Message(payload=b"OK")

class Brightness(resource.Resource):
    async def render_post(self, request):
        txt = request.payload.decode().strip().upper()
        # allow "120" or "SET 120"
        if txt.startswith("SET"):
            txt = txt[3:].strip()
        try:
            v = int(txt)
        except ValueError:
            return Message(code=resource.aiocoap.numbers.codes.Code.BAD_REQUEST, payload=b"Use 0-255")
        v = max(0, min(255, v))
        http_post("/brightness", {"value": v})
        return Message(payload=b"OK")

class Recal(resource.Resource):
    async def render_post(self, request):
        http_post("/cmd", {"cmd": "RECAL"})
        return Message(payload=b"OK")

class Status(resource.Resource):
    async def render_post(self, request):
        http_post("/cmd", {"cmd": "STATUS"})
        return Message(payload=b"OK")

async def main():
    root = resource.Site()
    root.add_resource(("enviroSense", "telemetry"), Telemetry())
    root.add_resource(("enviroSense", "mode"), Mode())
    root.add_resource(("enviroSense", "brightness"), Brightness())
    root.add_resource(("enviroSense", "recal"), Recal())
    root.add_resource(("enviroSense", "status"), Status())

    await Context.create_server_context(root, bind=("0.0.0.0", 5683))
    print("CoAP server running on udp/5683")
    await asyncio.get_running_loop().create_future()

if __name__ == "__main__":
    asyncio.run(main())
