"""The integration's HA-free modules as the package `xmeye_core`.

The built app bundles a copy of them (see build.py). From a checkout they are
loaded straight from custom_components/xmeye, without running its
__init__.py (which needs Home Assistant).
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "custom_components" / "xmeye"


def load() -> Path:
    """Make `import xmeye_core.<module>` work; returns the frontend directory."""
    if getattr(sys, "frozen", False):
        import xmeye_core  # noqa: PLC0415  (the bundled copy)

        return Path(xmeye_core.__file__).parent / "frontend"
    if "xmeye_core" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("xmeye_core", None, is_package=True)
        spec.submodule_search_locations = [str(SOURCE)]
        module = importlib.util.module_from_spec(spec)
        sys.modules["xmeye_core"] = module
    return SOURCE / "frontend"
