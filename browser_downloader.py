#!/usr/bin/env python3
"""Download an authorized Xiaoetong HLS stream through the logged-in browser session."""
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote
from app_runtime import ffmpeg_path, media_duration

def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', '_', name or 'video').strip(' .')
    return name[:160] or 'video'

def _probe_duration(path: Path) -> float:
    return media_duration(path)

def download_video(*, app_id: str, host: str, product_id: str, resource_id: str,
                   title: str, storage_state: str, download_dir: str,
                   wait_seconds: int = 10, log=None) -> tuple[bool, str]:
    if not Path(storage_state).exists():
        return False, '浏览器登录状态不存在，请重新登录'
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, f'Playwright 不可用: {exc}'
    stream = {'url': '', 'duration': 0.0}
    page_url = f'https://{app_id}.{host}/p/course/video/{resource_id}?product_id={quote(product_id)}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(storage_state))
            page = context.new_page()
            def on_response(response):
                if 'xe.material-center.play/getPlayUrl' in response.url:
                    try:
                        data = response.json().get('data') or {}
                        for entry in data.values():
                            play_list = entry.get('play_list') or {}
                            preferred = entry.get('default_play') or '720p_hls'
                            choices = [preferred, '1080p_hls', '720p_hls', '480p_hls']
                            for quality in choices:
                                url = (play_list.get(quality) or {}).get('play_url', '')
                                if '.m3u8' in url:
                                    stream['url'] = url
                                    break
                            if stream['url']:
                                break
                    except Exception:
                        pass
                if '.m3u8' in response.url:
                    stream['url'] = stream['url'] or response.url
                    try:
                        stream['duration'] = sum(float(x) for x in re.findall(
                            r'#EXTINF:([\d.]+)', response.text()))
                    except Exception:
                        pass
            page.on('response', on_response)
            page.goto(page_url, wait_until='domcontentloaded', timeout=60000)
            for _ in range(max(30, wait_seconds)):
                if stream['url']:
                    break
                page.wait_for_timeout(1000)
            if stream['url'] and not stream['duration']:
                try:
                    playlist = context.request.get(stream['url'], timeout=30000)
                    if playlist.ok:
                        stream['duration'] = sum(float(x) for x in re.findall(
                            r'#EXTINF:([\d.]+)', playlist.text()))
                except Exception:
                    pass
            browser.close()
    except Exception as exc:
        return False, f'打开视频页失败: {exc}'
    if not stream['url']:
        return False, '未捕获到授权播放地址，请确认课程仍可播放'
    out_dir = Path(download_dir); out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f'{_safe_name(title)}_{resource_id}.mp4'
    partial = out_dir / f'{_safe_name(title)}_{resource_id}.part.mp4'
    if output.exists() and stream['duration'] and abs(
            _probe_duration(output) - stream['duration']) <= 5:
        return True, f'文件已存在：{output}'
    progress = out_dir / f'{_safe_name(title)}_{resource_id}.progress'
    progress.unlink(missing_ok=True)
    try:
        ffmpeg = ffmpeg_path()
    except FileNotFoundError as exc:
        return False, str(exc)
    cmd = [ffmpeg, '-y', '-nostats', '-loglevel', 'error', '-progress', str(progress),
           '-protocol_whitelist', 'file,http,https,tcp,tls,crypto',
           '-i', stream['url'], '-c', 'copy', str(partial)]
    if log: log(f'已获取授权播放地址，开始下载：{output.name}')
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                text=True)
    except FileNotFoundError:
        return False, '未找到 ffmpeg，请先安装 ffmpeg'
    started = time.monotonic(); last_report = started
    while proc.poll() is None:
        if time.monotonic() - started > 7200:
            proc.kill(); proc.wait()
            return False, '下载超时，未完成文件保留为 .part.mp4'
        if log and progress.exists() and time.monotonic() - last_report >= 10:
            values = dict(line.split('=', 1) for line in progress.read_text(
                errors='replace').splitlines() if '=' in line)
            seconds = float(values.get('out_time_us', '0') or '0') / 1_000_000
            if seconds > 0:
                percent = f" / {stream['duration']:.0f} 秒 ({seconds/stream['duration']:.0%})" if stream['duration'] else ''
                log(f'下载进度：{seconds:.0f} 秒{percent}')
            last_report = time.monotonic()
        time.sleep(2)
    error_output = proc.stderr.read() if proc.stderr else ''
    progress.unlink(missing_ok=True)
    if proc.returncode != 0 or not partial.exists() or partial.stat().st_size == 0:
        detail = error_output.strip().splitlines()[-1:]
        return False, f'ffmpeg 下载失败: {detail[0] if detail else "未知错误"}'
    duration = _probe_duration(partial)
    if duration <= 0 or (stream['duration'] and abs(duration-stream['duration']) > 5):
        return False, '下载文件未通过播放格式检查，已保留 .part.mp4 供排查'
    partial.replace(output)
    return True, str(output)
