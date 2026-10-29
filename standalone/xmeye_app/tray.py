"""The icon in the menu bar / notification area: open, start at login, quit."""

from __future__ import annotations

import logging
from collections.abc import Callable

from . import APP_NAME, autostart
from .paths import resource

_LOGGER = logging.getLogger(__name__)


def run(open_ui: Callable[[], None], quit_app: Callable[[], None]) -> bool:
    """Show the icon and block until Quit. False if there is no tray here."""
    try:
        import pystray  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("No tray icon: %s", err)
        return False

    def toggle_autostart(_icon, _item) -> None:
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except OSError as err:
            _LOGGER.warning("Could not change start at login: %s", err)

    def on_quit(icon, _item) -> None:
        icon.stop()
        quit_app()

    menu = pystray.Menu(
        pystray.MenuItem(f"Open {APP_NAME}", lambda: open_ui(), default=True),
        pystray.MenuItem(
            "Start when I log in", toggle_autostart, checked=lambda _item: autostart.is_enabled()
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )
    image = Image.open(resource("web", "tray.png"))
    try:
        pystray.Icon("xmeye", image, APP_NAME, menu).run()
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("No tray icon: %s", err)
        return False
    return True
