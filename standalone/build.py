"""Build the standalone app for this platform with PyInstaller.

    pip install -r requirements-build.txt
    python build.py

Output in dist/: XMeye-Full-NVR-<os>-<arch>(.exe | .zip with the macOS app).
"""

from __future__ import annotations

import platform
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "custom_components" / "xmeye"
BUILD = HERE / "build"
DIST = HERE / "dist"
NAME = "XMeye Full NVR"
# the integration's modules the app uses; none may import homeassistant (except for type checking)
CORE = ["alarm", "commands", "const", "dvrip", "go2rtc", "homekit", "nvr", "nvrconfig",
        "playback", "thumbnails", "tsmux", "util"]  # fmt: skip
ARCH = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}


def core_package() -> Path:
    """Copy the shared modules into build/pkg/xmeye_core."""
    pkg = BUILD / "pkg" / "xmeye_core"
    shutil.rmtree(pkg.parent, ignore_errors=True)
    pkg.mkdir(parents=True)
    for name in CORE:
        text = (SOURCE / f"{name}.py").read_text("utf-8")
        if re.search(r"^(from|import) homeassistant", text, re.M):
            sys.exit(f"{name}.py imports homeassistant")
        (pkg / f"{name}.py").write_text(text, "utf-8")
    (pkg / "__init__.py").write_text('"""Shared with the Home Assistant integration."""\n')
    shutil.copytree(SOURCE / "frontend", pkg / "frontend")
    return pkg.parent


def icons() -> dict[str, Path]:
    logo = Image.open(SOURCE / "brand" / "icon@2x.png").convert("RGBA")
    ico, icns = BUILD / "icon.ico", BUILD / "icon.icns"
    logo.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    logo.resize((512, 512)).save(icns)
    return {"ico": ico, "icns": icns}


def version() -> str:
    text = (HERE / "xmeye_app" / "__init__.py").read_text()
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    shutil.rmtree(DIST, ignore_errors=True)
    pkg_root = core_package()
    icon = icons()
    system = platform.system()
    sep = ";" if system == "Windows" else ":"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", NAME,
        "--distpath", str(DIST), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
        "--paths", str(pkg_root), "--paths", str(HERE),
        "--add-data", f"{pkg_root / 'xmeye_core' / 'frontend'}{sep}xmeye_core/frontend",
        "--add-data", f"{HERE / 'xmeye_app' / 'web'}{sep}xmeye_app/web",
        "--collect-submodules", "pystray",
        "--collect-submodules", "keyring.backends",
        "--copy-metadata", "keyring",
        "--hidden-import", "xmeye_core",
    ]  # fmt: skip
    if system == "Windows":
        args += ["--onefile", "--windowed", "--icon", str(icon["ico"])]
    elif system == "Darwin":
        args += ["--windowed", "--icon", str(icon["icns"]),
                 "--osx-bundle-identifier", "io.github.kasik96.xmeye-full-nvr"]  # fmt: skip
    else:
        args += ["--onefile"]
    args.append(str(HERE / "run.py"))
    subprocess.run(args, check=True)

    arch = ARCH.get(platform.machine().lower(), platform.machine().lower())
    out = f"XMeye-Full-NVR-{version()}"
    if system == "Windows":
        (DIST / f"{NAME}.exe").rename(DIST / f"{out}-windows-{arch}.exe")
    elif system == "Darwin":
        app = DIST / f"{NAME}.app"
        info = app / "Contents" / "Info.plist"
        plist = plistlib.loads(info.read_bytes())
        plist.update(
            CFBundleShortVersionString=version(),
            LSUIElement=True,  # menu bar app, no Dock icon
            NSHumanReadableCopyright="MIT License",
        )
        info.write_bytes(plistlib.dumps(plist))
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
        # ditto keeps the bundle's symlinks and signature intact
        subprocess.run(
            ["ditto", "-c", "-k", "--keepParent", str(app), str(DIST / f"{out}-macos-{arch}.zip")],
            check=True,
        )
    else:
        (DIST / NAME).rename(DIST / f"{out}-linux-{arch}")
    print("\n".join(str(p) for p in DIST.iterdir()))


if __name__ == "__main__":
    main()
