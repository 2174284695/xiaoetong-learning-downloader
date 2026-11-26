"""Save the numbered page images from an authorized Xiaoetong ebook reader."""
import re
from pathlib import Path
from urllib.parse import quote

from browser_downloader import _safe_name


def download_ebook(*, app_id: str, host: str, product_id: str, resource_id: str,
                   title: str, storage_state: str, download_dir: str,
                   log=None) -> tuple[bool, str]:
    if not Path(storage_state).exists():
        return False, '浏览器登录状态不存在，请重新登录'
    if not resource_id.startswith('e_'):
        return False, '这不是电子书课时'
    from playwright.sync_api import sync_playwright

    url = (f'https://{app_id}.{host}/p/course/ebook/study/{resource_id}'
           f'?course_id={quote(product_id)}')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(storage_state=str(storage_state))
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_selector('img[src*="ebook.cdn.xiaoeknow.com"]', timeout=30000)
                page.wait_for_timeout(1000)
                sources = page.locator('img[src*="ebook.cdn.xiaoeknow.com"]').evaluate_all(
                    "els => els.map(el => el.getAttribute('src') || '')")
                pages = {}
                for source in sources:
                    match = re.search(r'/picture/(\d+)\.(jpe?g|png)', source, re.I)
                    if match:
                        # Thumbnail URLs carry the same per-page signature. Remove
                        # the resizing suffix to retrieve the original page image.
                        full = source.split('&imageView2', 1)[0]
                        pages[int(match.group(1))] = (full, match.group(2).lower())
                if not pages:
                    return False, '阅读页没有发现可下载的正文图片'
                folder = Path(download_dir) / f'{_safe_name(title)}_{resource_id}'
                folder.mkdir(parents=True, exist_ok=True)
                for index, (image_url, ext) in sorted(pages.items()):
                    target = folder / f'{index:03d}.{ext}'
                    if target.exists() and target.stat().st_size > 1000:
                        continue
                    response = context.request.get(image_url, timeout=60000)
                    if not response.ok:
                        return False, f'第 {index} 页下载失败：HTTP {response.status}'
                    content = response.body()
                    if len(content) < 1000 or not (
                            content.startswith(b'\xff\xd8\xff') or
                            content.startswith(b'\x89PNG\r\n\x1a\n')):
                        return False, f'第 {index} 页不是有效图片'
                    temporary = target.with_suffix(target.suffix + '.part')
                    temporary.write_bytes(content)
                    temporary.replace(target)
                    if log:
                        log(f'已保存图片 {index}/{len(pages)}：{target.name}')
                if len(list(folder.glob('[0-9][0-9][0-9].*'))) != len(pages):
                    return False, '图片数量不完整'
                return True, f'已保存 {len(pages)} 页图片：{folder}'
            finally:
                browser.close()
    except Exception as exc:
        return False, f'电子书下载失败：{exc}'
