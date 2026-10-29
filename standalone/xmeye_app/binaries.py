"""ffmpeg and go2rtc: from the PATH, else downloaded once into the data dir.

ffmpeg comes from the imageio-ffmpeg wheels on PyPI (static builds for every
platform, with libx264), go2rtc from its GitHub releases. Both are pinned
and checked against these hashes.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from pathlib import Path

from aiohttp import ClientSession

from xmeye_core import go2rtc
from xmeye_core.util import download_binary

_LOGGER = logging.getLogger(__name__)

FFMPEG_VERSION = "imageio-ffmpeg 0.7.0"
FFMPEG_MEMBER = "imageio_ffmpeg/binaries/ffmpeg-"
_PYPI = "https://files.pythonhosted.org/packages/"
FFMPEG_WHEELS = {
    ("Darwin", "arm64"): (
        "24/d3/be06b86c75acc49113aaf869b8c3d1e721ee01e1d1d7fa12cfc7d9708ea3/imageio_ffmpeg-0.7.0-py3-none-macosx_11_0_arm64.whl",
        "5cb5c37d3c19aa8e7cd95b9f4833e6a3d9fd33e4b1d126a42995b14aef9fef02",
    ),
    ("Darwin", "amd64"): (
        "f1/ef/e006996ba8735c1605b05fc931b7b49297cbdf11603259701bd0d62e17e1/imageio_ffmpeg-0.7.0-py3-none-macosx_10_9_intel.macosx_10_9_x86_64.whl",
        "fafa399433b571e8963471487cd7a7bb3ee7b532af42e6342145add6379f479b",
    ),
    ("Linux", "amd64"): (
        "04/96/15fe7ef562f7494c358cbd9b521d2da82d7a331b5513703756166478bd5f/imageio_ffmpeg-0.7.0-py3-none-manylinux2014_x86_64.whl",
        "4e1f36bef7bedd4bc5dc25f60a8345d88f57133fa1e754f09b411ac61b854408",
    ),
    ("Linux", "arm64"): (
        "9c/68/5c7eac9733c0a35b46f939df7079bbf72463dc347d4ff51fbad138d15ba9/imageio_ffmpeg-0.7.0-py3-none-manylinux2014_aarch64.whl",
        "588a23c6a1c55a7cb51febfe97d3ef8dd5e7fa0ef7e14c7da8828e2886bdd3a3",
    ),
    # also for Windows on ARM, which runs x64 programs
    ("Windows", "amd64"): (
        "e5/55/1d50cdd78d862a30c2ce44f01cea387f77b364b21fa2fecf1590258b215b/imageio_ffmpeg-0.7.0-py3-none-win_amd64.whl",
        "7a22b45f60321d4172bdf2bc61f716bce4c81b85727bd59c7c7e371055a6a440",
    ),
}  # fmt: skip


def _exe(name: str) -> str:
    return name + (".exe" if platform.system() == "Windows" else "")


async def ffmpeg(session: ClientSession, cache_dir: Path) -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    target = cache_dir / _exe("ffmpeg-imageio-0.7.0")
    if target.is_file():
        return str(target)
    system, arch = go2rtc.platform_key()
    if system == "Windows":
        arch = "amd64"
    if (system, arch) not in FFMPEG_WHEELS:
        raise RuntimeError(f"no ffmpeg download for {platform.system()} {platform.machine()}")
    path, sha256 = FFMPEG_WHEELS[(system, arch)]
    _LOGGER.info("Downloading ffmpeg (%s)", FFMPEG_VERSION)
    await download_binary(session, _PYPI + path, sha256, target, FFMPEG_MEMBER)
    return str(target)


async def go2rtc_binary(session: ClientSession, cache_dir: Path) -> str:
    found = await asyncio.to_thread(go2rtc.find_binary, cache_dir)
    return found or await go2rtc.download(session, cache_dir)
