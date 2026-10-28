"""Tiny DVRIP mock NVR for testing the integration without hardware.

    python tools/mock_nvr.py VIDEO.xm [--port 34567]

Login: admin / test. Channels 1 and 9 have a recording every 10 minutes today
and yesterday; every download streams VIDEO.xm (a file in the NVR's frame format).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import struct
from datetime import datetime, timedelta

HEADER = struct.Struct("<BB2xIIBBHI")
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def sofia(pw: str) -> str:
    d = hashlib.md5(pw.encode()).digest()
    return "".join(CHARS[(d[i] + d[i + 1]) % 62] for i in range(0, 16, 2))


class Mock:
    def __init__(self, video: bytes) -> None:
        self.video = video
        self.next_session = 0x100
        self.data_conns: dict[int, asyncio.StreamWriter] = {}

    def files(self, channel: int, begin: str, end: str) -> list[dict]:
        if channel not in (0, 8):
            return []
        b = datetime.strptime(begin, "%Y-%m-%d %H:%M:%S")
        e = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        t = today - timedelta(days=1)
        while t < datetime.now():
            if b <= t <= e:
                tag = "M" if t.minute % 20 else "R"
                stop = t + timedelta(seconds=37)
                out.append({
                    "BeginTime": f"{t:%Y-%m-%d %H:%M:%S}",
                    "EndTime": f"{stop:%Y-%m-%d %H:%M:%S}",
                    "DiskNo": 0, "SerialNo": 0, "FileLength": "0x00000087",
                    "FileName": f"/idea0/{t:%Y-%m-%d}/{channel + 1:03d}/"
                    f"{t:%H.%M.%S}-{stop:%H.%M.%S}[{tag}][@1][0].h264",
                })
            t += timedelta(minutes=10)
        return out[:64]

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session = 0

        def send(msg: int, obj: dict | None, raw: bytes | None = None) -> None:
            body = raw if raw is not None else json.dumps(obj).encode() + b"\n\0"
            writer.write(HEADER.pack(0xFF, 1, session, 0, 0, 0, msg, len(body)) + body)

        try:
            while True:
                hdr = await reader.readexactly(20)
                _, _, sess, _, _, _, msg, ln = HEADER.unpack(hdr)
                body = json.loads((await reader.readexactly(ln)).rstrip(b"\n\0") or b"{}")
                if msg == 1000:
                    if body.get("UserName") != "admin" or body.get("PassWord") != sofia("test"):
                        send(1001, {"Ret": 203})
                        continue
                    session = self.next_session
                    self.next_session += 1
                    send(1001, {"Ret": 100, "SessionID": f"0x{session:08X}", "AliveInterval": 21, "ChannelNum": 16})
                elif msg == 1006:
                    send(1007, {"Ret": 100, "Name": "KeepAlive"})
                elif msg == 1020:
                    send(1021, {"Ret": 100, "Name": "SystemInfo", "SystemInfo": {"SerialNo": "mock0001", "HardWare": "MOCK-NVR"}})
                elif msg == 1048:
                    send(1049, {"Ret": 100, "ChannelTitle": ["Shed", "Front Door"] + [f"D{i}" for i in range(3, 17)]})
                elif msg == 1042:
                    st = [{"Status": "Connected" if i in (0, 1, 8) else "NoConfig"} for i in range(16)]
                    send(1043, {"Ret": 100, "Name": body.get("Name"), body.get("Name"): st})
                elif msg == 1446:
                    now = datetime.now()
                    mask = (1 << (now.day - 1)) | ((1 << (now.day - 2)) if now.day > 1 else 0)
                    send(1447, {"Ret": 100, "OPSCalendar": {"Mask": mask}})
                elif msg == 1440:
                    q = body["OPFileQuery"]
                    files = self.files(q["Channel"], q["BeginTime"], q["EndTime"])
                    send(1441, {"Ret": 100 if files else 119, "OPFileQuery": files})
                elif msg == 1424:
                    session = sess
                    self.data_conns[sess] = writer
                    send(1425, {"Ret": 100})
                elif msg == 1420:
                    action = body["OPPlayBack"]["Action"]
                    send(1421, {"Ret": 100})
                    if action == "DownloadStart":
                        asyncio.create_task(self.stream(session))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def stream(self, session: int) -> None:
        w = self.data_conns.pop(session)
        for i in range(0, len(self.video), 32768):
            chunk = self.video[i : i + 32768]
            w.write(HEADER.pack(0xFF, 1, session, 0, 0, 0, 1426, len(chunk)) + chunk)
            await w.drain()
        w.write(HEADER.pack(0xFF, 1, session, 0, 0, 0, 1426, 0))
        await w.drain()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--port", type=int, default=34567)
    args = ap.parse_args()
    mock = Mock(open(args.video, "rb").read())
    server = await asyncio.start_server(mock.handle, "127.0.0.1", args.port)
    print(f"mock NVR on 127.0.0.1:{args.port}", flush=True)
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
