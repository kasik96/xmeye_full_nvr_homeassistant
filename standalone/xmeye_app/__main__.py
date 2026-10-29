"""Start the app: web server, NVR connection, browser window and tray icon.

    python -m xmeye_app [--background] [--no-tray]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import logging.handlers
import os
import signal
import ssl
import subprocess
import sys
import threading
import urllib.request
import webbrowser

from . import APP_NAME, __version__, core, paths, stale

_LOGGER = logging.getLogger("xmeye_app")


def _setup_logging(debug: bool) -> None:
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            paths.data_dir() / "xmeye.log", maxBytes=1 << 20, backupCount=3, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:  # a windowed app has none
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _ca_certificates() -> None:
    """The bundled Python looks for CA certificates where the build machine kept
    them; on macOS they are not there, and every download fails. Use certifi's
    then (through SSL_CERT_FILE, which also covers the helpers we start)."""
    paths = ssl.get_default_verify_paths()
    if os.environ.get("SSL_CERT_FILE") or (paths.cafile and os.path.isfile(paths.cafile)):
        return
    if paths.capath and os.path.isdir(paths.capath) and os.listdir(paths.capath):
        return
    import certifi  # noqa: PLC0415

    os.environ["SSL_CERT_FILE"] = certifi.where()


def _hide_console_windows() -> None:
    """A windowed app on Windows would open a console window for every ffmpeg
    and go2rtc it starts; the shared modules call asyncio's function."""
    original = asyncio.create_subprocess_exec

    async def create(*args, **kwargs):
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return await original(*args, **kwargs)

    asyncio.create_subprocess_exec = create  # type: ignore[assignment]


def _running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as resp:
            return json.load(resp).get("app") == "xmeye-full-nvr"
    except (OSError, ValueError):
        return False


class Runner:
    def __init__(self, background: bool, frontend) -> None:
        self.background = background
        self.frontend = frontend
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stopped: asyncio.Event | None = None
        self.port = 0
        self.ready = threading.Event()

    def url(self) -> str:
        return f"http://localhost:{self.port}/"

    def open_ui(self) -> None:
        if self.port:
            webbrowser.open(self.url())

    def quit(self) -> None:
        if self.loop and self.stopped:
            self.loop.call_soon_threadsafe(self.stopped.set)

    async def main(self) -> None:
        from .app import App  # noqa: PLC0415
        from .server import Server  # noqa: PLC0415

        self.loop = asyncio.get_running_loop()
        self.stopped = asyncio.Event()
        # quit cleanly on SIGTERM (not on Windows, nor outside the main thread)
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            self.loop.add_signal_handler(signal.SIGTERM, self.stopped.set)
        await asyncio.to_thread(stale.stop_stale_helpers, paths.data_dir())
        app = App(paths.data_dir())
        server = Server(app, self.frontend)
        try:
            await server.start()
        except OSError as err:
            _LOGGER.error("Cannot listen on port %d: %s", app.settings.http_port, err)
            self.ready.set()
            return
        self.port = server.port
        await app.start()
        _LOGGER.info("%s %s at %s", APP_NAME, __version__, self.url())
        self.ready.set()
        if not self.background:
            self.open_ui()
        try:
            await self.stopped.wait()
        finally:
            await server.close()
            await app.stop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="xmeye", description=APP_NAME)
    parser.add_argument("--background", action="store_true", help="do not open the browser")
    parser.add_argument("--no-tray", action="store_true", help="no tray icon (Ctrl+C quits)")
    parser.add_argument("--debug", action="store_true", help="debug logging")
    args = parser.parse_args()
    _setup_logging(args.debug)
    _ca_certificates()
    frontend = core.load()
    if sys.platform == "win32":
        _hide_console_windows()

    from .settings import SettingsFile  # noqa: PLC0415

    port = SettingsFile(paths.data_dir()).settings.http_port
    if _running(port):
        # already running: just show it
        if not args.background:
            webbrowser.open(f"http://localhost:{port}/")
        return

    runner = Runner(args.background, frontend)
    if args.no_tray:
        try:
            asyncio.run(runner.main())
        except KeyboardInterrupt:
            pass
        return

    thread = threading.Thread(target=lambda: asyncio.run(runner.main()), name="xmeye")
    thread.start()
    runner.ready.wait()
    from . import tray  # noqa: PLC0415

    if not thread.is_alive():
        return
    if not tray.run(runner.open_ui, runner.quit):
        # no tray here: run until the process is stopped
        try:
            thread.join()
        except KeyboardInterrupt:
            runner.quit()
    thread.join()


if __name__ == "__main__":
    main()
