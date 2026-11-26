"""Build a self-contained desktop app on the current operating system."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSERS = ROOT / 'build' / 'ms-playwright'
NAME = 'XiaoetongDownloader'


def main() -> None:
    if sys.platform not in ('darwin', 'win32'):
        raise SystemExit('当前仅支持在 macOS 或 Windows 上构建')
    env = os.environ.copy()
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(BROWSERS)
    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                   cwd=ROOT, env=env, check=True)
    if not any(BROWSERS.iterdir()):
        raise SystemExit('Chromium 下载失败')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--windowed', '--onedir', '--name', NAME,
               '--collect-all', 'playwright',
               '--collect-all', 'imageio_ffmpeg',
               str(ROOT / 'gui.py')]
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    target = f'{NAME}.app' if sys.platform == 'darwin' else NAME
    if sys.platform == 'darwin':
        browser_target = ROOT / 'dist' / target / 'Contents' / 'Resources' / 'ms-playwright'
    else:
        browser_target = ROOT / 'dist' / target / '_internal' / 'ms-playwright'
    if browser_target.exists():
        shutil.rmtree(browser_target)
    shutil.copytree(BROWSERS, browser_target, symlinks=True)
    if sys.platform == 'darwin':
        app_path = ROOT / 'dist' / target
        # Chromium is copied after PyInstaller signs the app. Seal the complete
        # bundle again so Gatekeeper does not report a damaged application.
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app_path)],
                       check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app_path)],
                       check=True)
    archive = ROOT / 'dist' / f'{NAME}-{"macOS" if sys.platform == "darwin" else "Windows"}'
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(ROOT / 'dist' / target), f'{archive}.zip'], check=True)
    else:
        shutil.make_archive(str(archive), 'zip', root_dir=ROOT / 'dist', base_dir=target)
    print(f'Built: {archive}.zip')


if __name__ == '__main__':
    main()
