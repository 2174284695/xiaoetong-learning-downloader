"""Read the course and its actual video lessons in the logged-in browser."""
import re
from urllib.parse import urlparse


def discover_lessons(course, storage_state):
    """Return (actual host, course id, video lessons) using the site's own APIs."""
    from playwright.sync_api import sync_playwright

    raw = course.get('raw') or {}
    if not raw.get('resource_id'):
        raise RuntimeError('课程缺少浏览器课程信息，请重新读取登录状态')
    gateway_payload = {
        'type': 2, 'app_id': raw.get('app_id') or course['app_id'],
        'user_id': raw.get('user_id', ''),
        'resource_type': raw.get('resource_type', ''),
        'resource_id': raw['resource_id'],
        'content_app_id': raw.get('content_app_id', ''),
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=str(storage_state))
            page = context.new_page()
            page.goto('https://study.xiaoe-tech.com/t_l/learnIndex?type=wx',
                      wait_until='domcontentloaded', timeout=60000)
            gateway = page.evaluate("""async payload => {
                const r = await fetch('/xe.learn-pc/get_new_gateway/1.0.0', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify(payload), credentials:'include'});
                return await r.json();
            }""", gateway_payload)
            url = (gateway.get('data') or {}).get('url') if isinstance(gateway, dict) else ''
            if not url:
                raise RuntimeError(f"课程入口失败：{gateway.get('msg', '未知错误')}")
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_url(re.compile(r'/p/course/'), timeout=60000)
            page_url = urlparse(page.url)
            match = re.search(r'/p/course/(?:big_column|column)/([^/?]+)', page_url.path)
            if not match:
                raise RuntimeError(f'无法识别课程页面：{page_url.path}')
            course_id = match.group(1)
            host = '.'.join(page_url.hostname.split('.')[1:])

            def fetch_items(kind, column_id):
                items = []
                for index in range(1, 100):
                    result = page.evaluate("""async arg => {
                        const form = new URLSearchParams();
                        form.set('bizData[column_id]', arg.id);
                        form.set('bizData[page_index]', String(arg.page));
                        form.set('bizData[page_size]', '100');
                        if (arg.kind === 'column') form.set('bizData[content_app_id]', '');
                        const prefix = arg.kind === 'column' ?
                            'xe.course.business_go.column.items.get' :
                            'xe.course.business.topic.items.get';
                        const r = await fetch('/' + prefix + '/2.0.0', {
                            method:'POST', body:form, credentials:'include'});
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return await r.json();
                    }""", {'kind': kind, 'id': column_id, 'page': index})
                    if result.get('code') != 0:
                        raise RuntimeError(f"读取课程目录失败：{result.get('msg', '未知错误')}")
                    data = result.get('data') or {}
                    batch = data.get('list') or []
                    items.extend(batch)
                    if not batch or len(items) >= int(data.get('total') or len(items)):
                        break
                return items

            groups = fetch_items('topic', course_id)
            lessons = []
            for group in groups:
                group_id = group.get('resource_id', '')
                group_title = group.get('resource_title') or '未命名分组'
                if group_id.startswith(('v_', 'e_')):
                    lessons.append({'id': group_id, 'title': group_title,
                                    'group': '', 'product_id': course_id,
                                    'kind': 'ebook' if group_id.startswith('e_') else 'video'})
                elif group_id.startswith('p_'):
                    for item in fetch_items('column', group_id):
                        rid = item.get('resource_id', '')
                        if rid.startswith(('v_', 'e_')):
                            lessons.append({
                                'id': rid, 'title': item.get('resource_title') or '未命名课时',
                                'group': group_title, 'product_id': group_id,
                                'kind': 'ebook' if rid.startswith('e_') else 'video',
                            })
            # The gateway sets a shop-specific login cookie. Persist it for the
            # subsequent video page, which opens in a separate browser context.
            context.storage_state(path=str(storage_state))
            return host, course_id, lessons
        finally:
            browser.close()
