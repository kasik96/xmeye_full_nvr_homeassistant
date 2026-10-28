"""Minimal video-only MPEG-TS muxer.

ffmpeg gets no timestamps from a raw H.264 pipe, and without them it does not
interleave the separate audio input; wrapping the video in TS with a PTS per
frame fixes that.
"""

from __future__ import annotations

import struct

PMT_PID = 0x1000
VIDEO_PID = 0x100
STREAM_TYPE = {"h264": 0x1B, "hevc": 0x24}
AUD = {"h264": b"\x00\x00\x00\x01\x09\xf0", "hevc": b"\x00\x00\x00\x01\x46\x01\x50"}
PTS_OFFSET = 90000


def _crc32_mpeg(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else crc << 1
            crc &= 0xFFFFFFFF
    return crc


def _pts_bytes(marker: int, pts: int) -> bytes:
    pts &= (1 << 33) - 1
    return bytes(
        [
            (marker << 4) | (((pts >> 30) & 0x07) << 1) | 1,
            (pts >> 22) & 0xFF,
            (((pts >> 15) & 0x7F) << 1) | 1,
            (pts >> 7) & 0xFF,
            ((pts & 0x7F) << 1) | 1,
        ]
    )


class TsMuxer:
    def __init__(self, video_codec: str) -> None:
        self.video_codec = video_codec
        self._cc: dict[int, int] = {}

    def _next_cc(self, pid: int) -> int:
        cc = (self._cc.get(pid, -1) + 1) & 0x0F
        self._cc[pid] = cc
        return cc

    def _section(self, pid: int, table: bytes) -> bytes:
        payload = b"\x00" + table + struct.pack(">I", _crc32_mpeg(table))
        header = struct.pack(">BHB", 0x47, 0x4000 | pid, 0x10 | self._next_cc(pid))
        return header + payload + b"\xff" * (184 - len(payload))

    def psi(self) -> bytes:
        pat = struct.pack(">BHHBBBHH", 0x00, 0xB00D, 1, 0xC1, 0, 0, 1, 0xE000 | PMT_PID)
        streams = struct.pack(
            ">BHH", STREAM_TYPE[self.video_codec], 0xE000 | VIDEO_PID, 0xF000
        )
        body = struct.pack(">HBBBHH", 1, 0xC1, 0, 0, 0xE000 | VIDEO_PID, 0xF000) + streams
        pmt = struct.pack(">BH", 0x02, 0xB000 | (len(body) + 4)) + body
        return self._section(0, pat) + self._section(PMT_PID, pmt)

    def _packetize(self, pid: int, pes: bytes, pcr: int, rai: bool) -> bytes:
        out = bytearray()
        pos = 0
        first = True
        while pos < len(pes):
            af: bytes | None = None
            if first:
                base = pcr & ((1 << 33) - 1)
                af = bytes([(0x40 if rai else 0) | 0x10]) + struct.pack(
                    ">IH", base >> 1, ((base & 1) << 15) | 0x7E00
                )
            room = 184 - (1 + len(af) if af is not None else 0)
            remaining = len(pes) - pos
            if remaining < room:
                stuffing = room - remaining
                if af is None:
                    af = b"" if stuffing == 1 else b"\x00" + b"\xff" * (stuffing - 2)
                else:
                    af += b"\xff" * stuffing
                room = remaining
            ctrl = 0x30 if af is not None else 0x10
            out += struct.pack(
                ">BHB", 0x47, (0x4000 if first else 0) | pid, ctrl | self._next_cc(pid)
            )
            if af is not None:
                out += bytes([len(af)]) + af
            out += pes[pos : pos + room]
            pos += room
            first = False
        return bytes(out)

    def video(self, au: bytes, pts: int, keyframe: bool) -> bytes:
        """One access unit (Annex-B) at `pts` (90 kHz, from 0)."""
        pts += PTS_OFFSET
        pes = (
            b"\x00\x00\x01\xe0\x00\x00\x80\x80\x05"
            + _pts_bytes(2, pts)
            + AUD[self.video_codec]
            + au
        )
        return self._packetize(VIDEO_PID, pes, pcr=pts - 9000, rai=keyframe)
