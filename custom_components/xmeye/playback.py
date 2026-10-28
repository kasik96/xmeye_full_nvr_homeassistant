"""On-demand playback: NVR file → ffmpeg → HLS (fMP4) served from a temp dir.

Nothing is kept: a session's segments live in a temporary directory that is
deleted when nobody has fetched from it for a while.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant

from .const import (
    DOMAIN,
    HLS_SEGMENT_SECONDS,
    MAX_SESSIONS,
    PLAYLIST_WAIT,
    SESSION_IDLE,
)
from .dvrip import (
    AUDIO_ALAW,
    AUDIO_ULAW,
    CODEC_H265,
    FRAME_AUDIO,
    FRAME_I,
    FRAME_P,
    DVRIPClient,
    DVRIPError,
    FrameParser,
    Recording,
    stamp_seconds,
)
from .tsmux import TsMuxer

_LOGGER = logging.getLogger(__name__)

PLAYLIST = "index.m3u8"
TEMP_PREFIX = "xmeye-"
# Frames buffered before starting ffmpeg, to learn fps and whether there is audio.
PROBE_VIDEO_FRAMES = 50
AUDIO_FORMATS = {AUDIO_ALAW: "alaw", AUDIO_ULAW: "mulaw"}
SILENCE = {"alaw": b"\xd5", "mulaw": b"\xff"}
SAMPLE_RATE = 8000
FAST_SPEED = 4
FPS_WINDOW = 6  # s of time stamps before trusting the measured frame rate
GAP_SECONDS = 10


class PlaybackSession:
    def __init__(
        self,
        hass: HomeAssistant,
        client: DVRIPClient,
        rec: Recording,
        ffmpeg: str,
        transcode_h265: bool,
        speed: int = 1,
    ) -> None:
        self.hass = hass
        self.speed = speed
        # ≥ FAST_SPEED: key frames only, no audio, time line compressed by `speed`
        self._fast = speed >= FAST_SPEED
        self.client = client
        self.rec = rec
        self.token = secrets.token_urlsafe(24)
        self.dir = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        self._ffmpeg = ffmpeg
        self._transcode_h265 = transcode_h265
        self.transcode_h265 = transcode_h265
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None
        self.finished = asyncio.Event()
        self.error: str | None = None
        self.last_access = asyncio.get_running_loop().time()
        self._fps = 25
        self._ts = TsMuxer("h264")
        self._silence = b""
        self._video_frames = 0
        self._audio_samples = 0
        self._padded = 0
        # Video clock from the I-frames' NVR time stamps (the fps in the header can be off)
        self._clock = 0.0  # seconds of footage
        self._fps_est = 25.0
        self._anchor: tuple[int, int, float] | None = None  # (frame index, stamp s, clock)
        self._last_stamp = 0

    def start(self) -> None:
        self._task = self.hass.async_create_background_task(
            self._run(), f"{DOMAIN} playback {self.rec.file_name}"
        )

    def touch(self) -> None:
        self.last_access = asyncio.get_running_loop().time()

    async def _run(self) -> None:
        audio_writer: asyncio.StreamWriter | None = None
        try:
            async with self.client.download(self.rec) as chunks:
                parser = FrameParser()
                pending = []
                started = False
                fps = 0
                video_codec = 0
                audio_codec: int | None = None
                video_frames = 0
                loop = asyncio.get_running_loop()
                received, report = 0, loop.time() + 10
                async for chunk in chunks:
                    received += len(chunk)
                    if loop.time() > report:
                        report = loop.time() + 10
                        _LOGGER.debug(
                            "%s: %.1f MB, %d video frames, audio %.1f s (+%.1f s silence)",
                            self.rec.file_name, received / 1e6, self._video_frames,
                            self._audio_samples / SAMPLE_RATE, self._padded / SAMPLE_RATE,
                        )
                    frames = parser.feed(chunk)
                    if not started:
                        for frame in frames:
                            if frame.kind in FRAME_I and not fps:
                                fps, video_codec = frame.fps or 25, frame.codec
                            if not fps:
                                continue  # drop everything before the first I-frame
                            pending.append(frame)
                            if frame.kind in FRAME_I or frame.kind == FRAME_P:
                                video_frames += 1
                            elif frame.kind == FRAME_AUDIO and audio_codec is None:
                                audio_codec = frame.codec
                        if video_frames < PROBE_VIDEO_FRAMES:
                            continue
                        audio_writer = await self._start_ffmpeg(
                            fps, video_codec, None if self._fast else AUDIO_FORMATS.get(audio_codec)
                        )
                        frames, pending, started = pending, [], True
                    await self._write(frames, audio_writer)
                if not started and pending:
                    audio_writer = await self._start_ffmpeg(
                        fps, video_codec, None if self._fast else AUDIO_FORMATS.get(audio_codec)
                    )
                    await self._write(pending, audio_writer)
                _LOGGER.debug(
                    "%s: %d video frames over %.1f s (%.2f fps, header %d), %.1f s audio "
                    "(%.1f s silence added), %d junk bytes",
                    self.rec.file_name,
                    self._video_frames,
                    self._clock,
                    self._fps_est,
                    fps,
                    self._audio_samples / SAMPLE_RATE,
                    self._padded / SAMPLE_RATE,
                    parser.skipped,
                )
            await self._finish_ffmpeg(audio_writer)
        except asyncio.CancelledError:
            raise
        except (DVRIPError, OSError, ConnectionError) as err:
            self.error = str(err)
            _LOGGER.warning("Playback of %s failed: %s", self.rec.file_name, err)
        finally:
            if self._proc and self._proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()
            self.finished.set()

    async def _start_ffmpeg(
        self, fps: int, codec: int, audio: str | None
    ) -> asyncio.StreamWriter | None:
        h265 = codec == CODEC_H265
        self._fps = fps
        self._fps_est = float(fps or 25)
        self._ts = TsMuxer("hevc" if h265 else "h264")
        self._silence = SILENCE.get(audio or "", b"")
        args = [
            self._ffmpeg, "-hide_banner", "-loglevel", "warning",
            "-thread_queue_size", "1024", "-f", "mpegts", "-i", "pipe:0",
        ]  # fmt: skip
        audio_fd = None
        if audio:
            read_fd, audio_fd = os.pipe()
            args += [
                "-thread_queue_size", "1024",
                "-f", audio, "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", f"pipe:{read_fd}",
            ]  # fmt: skip
        args += ["-map", "0:v"]
        if h265 and self._transcode_h265:
            args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
        else:
            args += ["-c:v", "copy"]
            if h265:
                args += ["-tag:v", "hvc1"]
        if audio:
            args += ["-map", "1:a", "-c:a", "aac", "-b:a", "48k", "-ar", "16000"]
        args += [
            "-f", "hls", "-hls_time", str(HLS_SEGMENT_SECONDS), "-hls_list_size", "0",
            "-hls_playlist_type", "event", "-hls_segment_type", "fmp4",
            "-hls_flags", "independent_segments+temp_file",
            "-hls_fmp4_init_filename", "init.mp4",
            "-hls_segment_filename", str(self.dir / "seg%05d.m4s"),
            str(self.dir / PLAYLIST),
        ]  # fmt: skip
        _LOGGER.debug("Starting %s", " ".join(args))
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            pass_fds=(read_fd,) if audio else (),
        )
        self.hass.async_create_background_task(
            self._log_stderr(self._proc), f"{DOMAIN} ffmpeg log"
        )
        if not audio:
            return None
        os.close(read_fd)
        loop = asyncio.get_running_loop()
        pipe = os.fdopen(audio_fd, "wb", buffering=0)
        transport, protocol = await loop.connect_write_pipe(
            lambda: asyncio.streams.FlowControlMixin(loop=loop), pipe
        )
        return asyncio.StreamWriter(transport, protocol, None, loop)

    async def _log_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr
        async for line in proc.stderr:
            _LOGGER.debug("ffmpeg %s: %s", self.rec.file_name, line.decode(errors="replace").rstrip())

    async def _write(self, frames, audio_writer: asyncio.StreamWriter | None) -> None:
        """Feed ffmpeg. Audio gaps are filled with silence up to the video clock:
        ffmpeg reads its inputs in timestamp order, so an audio input that falls
        behind (cameras send audio only now and then) would stall the video."""
        assert self._proc and self._proc.stdin
        video = self._proc.stdin
        for frame in frames:
            if frame.kind in FRAME_I or frame.kind == FRAME_P:
                keyframe = frame.kind in FRAME_I
                if keyframe:
                    self._sync_clock(frame.stamp)
                if keyframe or not self._fast:
                    if keyframe:
                        video.write(self._ts.psi())
                    pts = int(self._clock / self.speed * 90000)
                    video.write(self._ts.video(frame.data, pts, keyframe))
                self._video_frames += 1
                self._clock += 1 / self._fps_est
                if audio_writer:
                    behind = int(self._clock * SAMPLE_RATE) - self._audio_samples
                    if behind > SAMPLE_RATE // 4:
                        audio_writer.write(self._silence * behind)
                        self._audio_samples += behind
                        self._padded += behind
            elif frame.kind == FRAME_AUDIO and audio_writer:
                audio_writer.write(frame.data)
                self._audio_samples += len(frame.data)
        await video.drain()
        # Audio is tiny; only wait for it if it piles up, never block video on it.
        if audio_writer and audio_writer.transport.get_write_buffer_size() > 1 << 20:
            await audio_writer.drain()

    def _sync_clock(self, stamp: int) -> None:
        """Estimate the real frame rate from the I-frames' 1-second time stamps."""
        seconds = stamp_seconds(stamp)
        if not seconds:
            return
        if self._anchor is None or not 0 <= seconds - self._last_stamp <= GAP_SECONDS:
            if self._anchor is not None and seconds > self._last_stamp:
                # recording gap (camera was offline): jump the clock forward
                self._clock += seconds - self._last_stamp - 1 / self._fps_est
            # (a clock that went backwards just starts a new measurement)
            self._anchor = (self._video_frames, seconds, self._clock)
        else:
            frames0, seconds0, _ = self._anchor
            if seconds - seconds0 >= FPS_WINDOW:
                fps = (self._video_frames - frames0) / (seconds - seconds0)
                self._fps_est = min(max(fps, self._fps * 0.5, 1.0), self._fps * 1.5 + 1)
        self._last_stamp = seconds

    async def _finish_ffmpeg(self, audio_writer: asyncio.StreamWriter | None) -> None:
        if not self._proc:
            self.error = "no video in recording"
            return
        if audio_writer:
            audio_writer.close()
        assert self._proc.stdin
        self._proc.stdin.close()
        try:
            await asyncio.wait_for(self._proc.wait(), 60)
        except TimeoutError:
            self._proc.kill()

    async def playlist(self) -> str | None:
        """The playlist once it has a segment, made to start at the beginning."""
        self.touch()
        path = self.dir / PLAYLIST
        loop = asyncio.get_running_loop()
        deadline = loop.time() + PLAYLIST_WAIT
        while loop.time() < deadline:
            text = await self.hass.async_add_executor_job(_read_text, path)
            if text and ("#EXT-X-ENDLIST" in text or text.count("#EXTINF") >= 2):
                break
            if self.finished.is_set() and not text:
                return None
            await asyncio.sleep(0.3)
        else:
            if not text:
                return None
        # An EVENT playlist is treated as live by players; start at 0 instead.
        return text.replace(
            "#EXTM3U\n", "#EXTM3U\n#EXT-X-START:TIME-OFFSET=0,PRECISE=YES\n", 1
        )

    async def close(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        await self.hass.async_add_executor_job(shutil.rmtree, self.dir, True)


def _remove_stale_dirs() -> None:
    for path in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*"):
        shutil.rmtree(path, ignore_errors=True)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


class PlaybackManager:
    """Owns the playback sessions of all config entries."""

    def __init__(self, hass: HomeAssistant, ffmpeg: str) -> None:
        self.hass = hass
        self.ffmpeg = ffmpeg
        self.sessions: dict[str, PlaybackSession] = {}
        self._reaper: asyncio.Task | None = None

    async def async_setup(self) -> None:
        """Remove temp dirs left by a crash and clean up on shutdown."""
        await self.hass.async_add_executor_job(_remove_stale_dirs)

        async def _on_stop(_event: Event) -> None:
            await self.close()

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)

    async def start(
        self, client: DVRIPClient, rec: Recording, transcode_h265: bool, speed: int = 1
    ) -> PlaybackSession:
        for session in self.sessions.values():
            if (
                session.client is client
                and session.rec == rec
                and session.speed == speed
                and session.transcode_h265 == transcode_h265
                and not session.error
            ):
                session.touch()
                return session
        while len(self.sessions) >= MAX_SESSIONS:
            oldest = min(self.sessions.values(), key=lambda s: s.last_access)
            await self._remove(oldest)
        session = PlaybackSession(
            self.hass, client, rec, self.ffmpeg, transcode_h265, speed
        )
        self.sessions[session.token] = session
        session.start()
        if self._reaper is None or self._reaper.done():
            self._reaper = self.hass.async_create_background_task(
                self._reap(), f"{DOMAIN} playback reaper"
            )
        return session

    async def _remove(self, session: PlaybackSession) -> None:
        self.sessions.pop(session.token, None)
        await session.close()

    async def _reap(self) -> None:
        loop = asyncio.get_running_loop()
        while self.sessions:
            await asyncio.sleep(15)
            now = loop.time()
            for session in list(self.sessions.values()):
                if now - session.last_access > SESSION_IDLE:
                    await self._remove(session)

    async def close_client(self, client: DVRIPClient) -> None:
        for session in list(self.sessions.values()):
            if session.client is client:
                await self._remove(session)

    async def close(self) -> None:
        for session in list(self.sessions.values()):
            await self._remove(session)


class PlaybackView(HomeAssistantView):
    """Serves the HLS files. The random session token is the authorization,
    like HA's own camera streams, because players fetch segments without
    the signed-path parameter."""

    url = "/api/xmeye/hls/{token}/{name}"
    name = "api:xmeye:hls"
    requires_auth = False

    def __init__(self, manager: PlaybackManager) -> None:
        self.manager = manager

    async def get(self, request: web.Request, token: str, name: str) -> web.StreamResponse:
        session = self.manager.sessions.get(token)
        if session is None:
            raise web.HTTPNotFound
        headers = {"Cache-Control": "no-cache"}
        if name == PLAYLIST:
            text = await session.playlist()
            if text is None:
                _LOGGER.warning(
                    "No video for %s: %s", session.rec.file_name, session.error or "timeout"
                )
                raise web.HTTPNotFound
            return web.Response(
                text=text, content_type="application/vnd.apple.mpegurl", headers=headers
            )
        if "/" in name or ".." in name or not name.endswith((".mp4", ".m4s")):
            raise web.HTTPNotFound
        session.touch()
        path = session.dir / name
        if not await self.manager.hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(path, headers={"Content-Type": "video/mp4", **headers})
