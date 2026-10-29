"""The web server: the panel, the settings page and a WebSocket API that
speaks enough of Home Assistant's for the panel to run unchanged.

Access: by default the server listens on localhost only. With LAN access on it
listens on all interfaces and asks everyone except this computer for the
web password. Requests must name this computer in their Host header (against
DNS rebinding) and WebSockets and POSTs must come from this origin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import socket
from typing import Any
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web
import voluptuous as vol

from xmeye_core.commands import COMMANDS, APIError, thumbnail
from xmeye_core.dvrip import DVRIPAuthError, DVRIPError
from xmeye_core.playback import hls_response
from xmeye_core.util import background

from . import APP_NAME, __version__, autostart
from .app import App
from .live import WebRTCSession
from .paths import resource
from .settings import check_password, hash_password

_LOGGER = logging.getLogger(__name__)

COOKIE = "xmeye_session"
PORT_TRIES = 10
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
# reachable without logging in (the HLS token is its own authorization)
PUBLIC = ("/login", "/app/app.css", "/panel/logo.png", "/api/ping", "/api/xmeye/hls/")
COMMANDS_BY_TYPE = {f"xmeye/{c.name}": c for c in COMMANDS}


class Server:
    def __init__(self, app: App, frontend: Any) -> None:
        self.app = app
        self.frontend = frontend
        self.web = resource("web")
        self.sessions: set[str] = set()
        self.port = 0
        self._runner: web.AppRunner | None = None
        self._sockets: set[web.WebSocketResponse] = set()

    # --- lifecycle -----------------------------------------------------------

    def make_app(self) -> web.Application:
        wapp = web.Application(middlewares=[self._guard])
        wapp.router.add_get("/", self._index)
        wapp.router.add_get("/setup", self._page("setup.html"))
        wapp.router.add_get("/login", self._page("login.html"))
        wapp.router.add_post("/login", self._login)
        wapp.router.add_post("/logout", self._logout)
        wapp.router.add_get("/api/ping", self._ping)
        wapp.router.add_get("/api/websocket", self._websocket)
        wapp.router.add_get("/api/xmeye/hls/{token}/{name}", self._hls)
        wapp.router.add_get("/api/xmeye/thumb/{entry_id}/{channel}/{stamp}", self._thumb)
        wapp.router.add_get("/api/snapshot/{entity_id}", self._snapshot)
        wapp.router.add_static("/panel", self.frontend)
        wapp.router.add_static("/app", self.web)
        return wapp

    async def start(self) -> None:
        """Listen on the configured port, or the next free one (which is then kept)."""
        s = self.app.settings
        self._runner = web.AppRunner(self.make_app(), access_log=None, shutdown_timeout=3)
        await self._runner.setup()
        host = None if s.lan else "127.0.0.1"
        for port in range(s.http_port, s.http_port + PORT_TRIES):
            try:
                await web.TCPSite(self._runner, host, port).start()
                break
            except OSError as err:
                _LOGGER.warning("Port %d is taken (%s)", port, err)
        else:
            await self._runner.cleanup()
            raise OSError(f"ports {s.http_port}-{port} are all taken")
        if port != s.http_port:
            s.http_port = port
            await asyncio.to_thread(self.app.config.save)
        self.port = port
        _LOGGER.info("Listening on %s port %d", "all interfaces" if s.lan else "localhost", self.port)

    async def stop(self) -> None:
        # open tabs would hold up the shutdown; they reconnect by themselves
        for ws in list(self._sockets):
            await ws.close(code=1001, message=b"restarting")
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def restart_later(self) -> None:
        """Rebind after the settings changed (the reply is sent first)."""
        await asyncio.sleep(0.5)
        await self.stop()
        await self.start()

    # --- access --------------------------------------------------------------

    def _local(self, request: web.Request) -> bool:
        hostname = urlsplit(f"//{request.host}").hostname or ""
        remote = request.remote or ""
        return hostname in LOOPBACK_NAMES and remote in ("127.0.0.1", "::1")

    @web.middleware
    async def _guard(self, request: web.Request, handler) -> web.StreamResponse:
        # Only requests to localhost from this computer skip the login. A page
        # elsewhere that rebinds its own name to 127.0.0.1 still needs it.
        local = self._local(request)
        if not local and not (self.app.settings.lan and self.app.settings.web_password):
            raise web.HTTPForbidden(text="Open it on this computer, or turn on network access.")
        origin = request.headers.get("Origin")
        if (request.method != "GET" or request.path == "/api/websocket") and origin:
            if urlsplit(origin).netloc != request.host:
                raise web.HTTPForbidden(text="Wrong origin")
        if not local and not request.path.startswith(PUBLIC):
            if request.cookies.get(COOKIE) not in self.sessions:
                if request.method == "GET" and not request.path.startswith("/api/"):
                    raise web.HTTPFound("/login")
                raise web.HTTPUnauthorized
        response = await handler(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith(("/app/", "/panel/")):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    async def _login(self, request: web.Request) -> web.StreamResponse:
        form = await request.post()
        stored = self.app.settings.web_password
        if not stored or not check_password(str(form.get("password", "")), stored):
            await asyncio.sleep(1)
            raise web.HTTPFound("/login?wrong=1")
        token = secrets.token_urlsafe(32)
        self.sessions.add(token)
        response = web.HTTPFound("/")
        response.set_cookie(COOKIE, token, httponly=True, samesite="Strict", max_age=30 * 86400)
        raise response

    async def _logout(self, request: web.Request) -> web.StreamResponse:
        self.sessions.discard(request.cookies.get(COOKIE, ""))
        response = web.HTTPFound("/login")
        response.del_cookie(COOKIE)
        raise response

    # --- pages ---------------------------------------------------------------

    def _page(self, name: str):
        async def handler(_request: web.Request) -> web.StreamResponse:
            return web.FileResponse(self.web / name, headers={"Cache-Control": "no-cache"})

        return handler

    async def _index(self, request: web.Request) -> web.StreamResponse:
        if not self.app.settings.configured:
            raise web.HTTPFound("/setup")
        return await self._page("index.html")(request)

    async def _ping(self, _request: web.Request) -> web.Response:
        return web.json_response({"app": "xmeye-full-nvr"})

    async def _hls(self, request: web.Request) -> web.StreamResponse:
        if not self.app.services:
            raise web.HTTPNotFound
        info = request.match_info
        return await hls_response(self.app.services.playback, info["token"], info["name"])

    async def _thumb(self, request: web.Request) -> web.StreamResponse:
        if not self.app.services:
            raise web.HTTPNotFound
        info = request.match_info
        return await thumbnail(self.app.services, info["entry_id"], info["channel"], info["stamp"])

    async def _snapshot(self, request: web.Request) -> web.StreamResponse:
        image = await self.app.snapshot(request.match_info["entity_id"])
        if image is None:
            raise web.HTTPNotFound
        return web.Response(body=image, content_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    # --- WebSocket -----------------------------------------------------------

    async def _websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=1 << 20)
        await ws.prepare(request)
        conn = Connection(self, ws)
        self._sockets.add(ws)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    msg_id = int(data["id"])
                except (ValueError, KeyError, TypeError):
                    continue
                background(conn.handle(msg_id, data), "xmeye ws command")
        finally:
            self._sockets.discard(ws)
            await conn.close()
        return ws

    def lan_urls(self) -> list[str]:
        """Addresses other devices can use (best guess)."""
        names = set()
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                names.add(info[4][0])
        except OSError:
            pass
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("192.0.2.1", 9))  # no packet is sent
                names.add(sock.getsockname()[0])
        except OSError:
            pass
        return [f"http://{n}:{self.port}" for n in sorted(names) if not n.startswith("127.")]


class Connection:
    """One browser tab."""

    def __init__(self, server: Server, ws: web.WebSocketResponse) -> None:
        self.server = server
        self.app = server.app
        self.ws = ws
        self.webrtc: dict[int, WebRTCSession] = {}  # subscription id → session
        self._session_ids: dict[str, int] = {}
        self._send_lock = asyncio.Lock()

    async def send(self, data: dict[str, Any]) -> None:
        if self.ws.closed:
            return
        async with self._send_lock:
            try:
                await self.ws.send_str(json.dumps(data))
            except ConnectionError:
                pass

    async def result(self, msg_id: int, result: Any = None) -> None:
        await self.send({"id": msg_id, "type": "result", "success": True, "result": result})

    async def error(self, msg_id: int, code: str, message: str) -> None:
        await self.send(
            {"id": msg_id, "type": "result", "success": False, "error": {"code": code, "message": message}}
        )

    async def handle(self, msg_id: int, msg: dict[str, Any]) -> None:
        kind = msg.get("type", "")
        try:
            if kind in COMMANDS_BY_TYPE:
                await self._command(msg_id, msg)
            elif kind.startswith("app/"):
                await self.result(msg_id, await self._app_command(kind[4:], msg))
            elif kind == "camera/webrtc/get_client_config":
                await self.result(msg_id, {"configuration": {"iceServers": []}})
            elif kind == "camera/webrtc/offer":
                await self._webrtc_offer(msg_id, msg)
            elif kind == "camera/webrtc/candidate":
                session = self.webrtc.get(self._session_ids.get(str(msg.get("session_id")), -1))
                if session:
                    await session.candidate(msg.get("candidate") or {})
                await self.result(msg_id)
            elif kind == "unsubscribe":
                session = self.webrtc.pop(int(msg.get("subscription", -1)), None)
                if session:
                    await session.close()
                await self.result(msg_id)
            else:
                await self.error(msg_id, "unknown_command", f"Unknown command {kind}")
        except APIError as err:
            await self.error(msg_id, "xmeye_error", str(err))
        except vol.Invalid as err:
            await self.error(msg_id, "invalid_format", str(err))
        except DVRIPAuthError:
            await self.error(msg_id, "auth", "The NVR rejected the user name or password.")
        except (DVRIPError, OSError, TimeoutError) as err:
            await self.error(msg_id, "nvr", f"Cannot reach the NVR: {err}")
        except Exception:
            _LOGGER.exception("Command %s failed", kind)
            await self.error(msg_id, "unknown_error", "Unexpected error, see the log")

    async def _command(self, msg_id: int, msg: dict[str, Any]) -> None:
        cmd = COMMANDS_BY_TYPE[msg["type"]]
        services = self.app.services
        if services is None:
            raise APIError(self.app.error or self.app.status)
        schema = vol.Schema(
            {vol.Required("id"): int, vol.Required("type"): str, **cmd.schema},
            extra=vol.REMOVE_EXTRA,
        )
        await self.result(msg_id, await cmd.handler(services, schema(msg)))

    async def _webrtc_offer(self, msg_id: int, msg: dict[str, Any]) -> None:
        stream = self.app.streams.get(str(msg.get("entity_id")))
        if not stream or not self.app.live:
            raise APIError("unknown camera")
        session_id = secrets.token_hex(8)
        self._session_ids[session_id] = msg_id
        await self.result(msg_id)

        async def send(event: dict[str, Any]) -> None:
            await self.send({"id": msg_id, "type": "event", "event": event})

        await send({"type": "session", "session_id": session_id})
        try:
            self.webrtc[msg_id] = await self.app.live.webrtc(stream, str(msg.get("offer")), send)
        except Exception as err:  # noqa: BLE001
            await send({"type": "error", "code": "go2rtc", "message": str(err)})

    async def _app_command(self, name: str, msg: dict[str, Any]) -> Any:
        app = self.app
        s = app.settings
        if name == "status":
            nvr = app.nvr
            return {
                "app": APP_NAME,
                "version": __version__,
                "status": app.status,
                "error": app.error,
                "connected": nvr is not None,
                "settings": s.public(),
                "channels": [
                    {"channel": ch + 1, "title": title}
                    for ch, title in (nvr.nvr_channels.items() if nvr else [])
                ],
                "model": nvr.model if nvr else None,
                "autostart": await asyncio.to_thread(autostart.is_enabled),
                "lan_urls": self.server.lan_urls() if s.lan else [],
            }
        if name == "test":
            return await app.test(
                str(msg["host"]).strip(), int(msg["port"]), str(msg["username"]), msg.get("password")
            )
        if name == "save":
            return await self._save(msg)
        if name == "autostart":
            await asyncio.to_thread(autostart.set_enabled, bool(msg["enabled"]))
            return {"autostart": await asyncio.to_thread(autostart.is_enabled)}
        raise APIError(f"Unknown command app/{name}")

    async def _save(self, msg: dict[str, Any]) -> Any:
        app = self.app
        s = app.settings
        before = (s.host, s.port, s.rtsp_port, s.username, dict(s.names), s.transcode_h265)
        listen_before = (s.lan, s.http_port)
        nvr = msg.get("nvr")
        if nvr is not None:
            s.host = str(nvr["host"]).strip()
            s.port = int(nvr.get("port", 34567))
            s.rtsp_port = int(nvr.get("rtsp_port", 554))
            s.username = str(nvr["username"])
            if nvr.get("password") is not None:
                await asyncio.to_thread(app.config.set_password, str(nvr["password"]))
                before = ()  # reconnect with the new password
        if "names" in msg:
            s.names = {str(k): str(v) for k, v in msg["names"].items()}
        if "transcode_h265" in msg:
            s.transcode_h265 = bool(msg["transcode_h265"])
        if msg.get("web_password"):
            if len(msg["web_password"]) < 8:
                raise APIError("The web password needs at least 8 characters.")
            s.web_password = hash_password(str(msg["web_password"]))
            self.server.sessions.clear()
        if "lan" in msg:
            if msg["lan"] and not s.web_password:
                raise APIError("Set a web password before turning on network access.")
            s.lan = bool(msg["lan"])
        if "http_port" in msg:
            port = int(msg["http_port"])
            if not 1024 <= port <= 65535:
                raise APIError("Use a port between 1024 and 65535.")
            s.http_port = port
        await asyncio.to_thread(app.config.save)
        if (s.host, s.port, s.rtsp_port, s.username, s.names, s.transcode_h265) != before:
            await app.reconnect()
        restart = (s.lan, s.http_port) != listen_before
        if restart:
            background(self.server.restart_later(), "xmeye rebind")
        return {"restart": restart, "port": s.http_port}

    async def close(self) -> None:
        for session in self.webrtc.values():
            await session.close()
        self.webrtc.clear()
