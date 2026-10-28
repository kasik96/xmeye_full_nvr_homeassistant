"""Sidebar panel: live grid, single camera with timeline and events."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import PANEL_URL

FRONTEND = Path(__file__).parent / "frontend"


async def async_setup(hass: HomeAssistant) -> None:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(FRONTEND), cache_headers=False)]
    )
    version = await hass.async_add_executor_job(
        lambda: int((FRONTEND / "xmeye-panel.js").stat().st_mtime)
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path="xmeye",
        webcomponent_name="xmeye-panel",
        sidebar_title="NVR",
        sidebar_icon="mdi:cctv",
        module_url=f"{PANEL_URL}/xmeye-panel.js?v={version}",
        require_admin=False,
        config={"hls": f"{PANEL_URL}/hls.light.min.js"},
    )
