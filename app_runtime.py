"""Paths and bundled tools shared by source and packaged builds."""
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


FROZEN = getattr(sys, 'frozen', False)
SOURCE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class CourseConfig:
    app_id: str
    cookie: str
    product_id: str
    download_dir: str
    host: str
    user_id: str = ''


def data_dir() -> Path:
    if not FROZEN:
        return SOURCE_DIR
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    elif os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        root = Path.home() / '.local' / 'share'
    return root / 'XiaoetongDownloader'


def default_download_dir() -> Path:
    if not FROZEN:
        return SOURCE_DIR / 'download'
    return Path.home() / 'Downloads' / 'XiaoetongDownloader'


def configure_browser() -> None:
    if FROZEN:
        browser_path = Path(sys._MEIPASS) / 'ms-playwright'
        if browser_path.exists():
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(browser_path)


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        executable = shutil.which('ffmpeg')
        if executable:
            return executable
    raise FileNotFoundError('未找到 ffmpeg，请安装 ffmpeg 或使用完整安装包')


def media_duration(path: Path) -> float:
    """Read MP4 duration from ffmpeg's probe output without a separate ffprobe."""
    try:
        result = subprocess.run([ffmpeg_path(), '-hide_banner', '-i', str(path)],
                                capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0.0
    match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', result.stderr)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
