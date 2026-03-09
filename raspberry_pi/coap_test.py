import asyncio
from aiocoap import Context, Message, GET, POST

PI_IP = "127.0.0.1"  # or your Pi hotspot IP
async def main():
    protocol = await Context.create_client_context()

    # GET telemetry
    req = Message(code=GET, uri=f"coap://{PI_IP}/enviroSense/telemetry")
    resp = await protocol.request(req).response
    print("telemetry:", resp.payload.decode())

    # Set MANUAL
    req = Message(code=POST, uri=f"coap://{PI_IP}/enviroSense/mode", payload=b"MANUAL")
    await protocol.request(req).response
    print("mode set to MANUAL")

    # Set brightness
    req = Message(code=POST, uri=f"coap://{PI_IP}/enviroSense/brightness", payload=b"120")
    await protocol.request(req).response
    print("brightness set")

asyncio.run(main())
