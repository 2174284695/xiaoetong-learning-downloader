#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
URL='https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index'
from app_runtime import configure_browser

def run_browser_session(out: Path, signal: Path):
    configure_browser()
    state=out.with_name('storage_state.json'); out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False)
        context=browser.new_context()
        page=context.new_page(); responses=[]
        def on_response(r):
            if any(x in r.url.lower() for x in ('course','product','column','learn')):
                item={'url':r.url,'method':r.request.method,'post_data':r.request.post_data}
                if 'my_attend_normal_list.get' in r.url:
                    try: item['json']=r.json()
                    except Exception: pass
                responses.append(item)
        page.on('response', on_response)
        page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        print('READY', flush=True)
        while not signal.exists(): time.sleep(.5)
        time.sleep(3)
        cookies=context.cookies()
        links=page.locator('a[href], [data-href], [data-url]').evaluate_all("els => els.map(a => ({text:(a.innerText||a.textContent||'').trim(), href:a.href || a.dataset.href || a.dataset.url || ''})).filter(x => x.text && x.href)")
        cards=page.locator('[class*=course], [class*=product], [class*=column]').evaluate_all("els => els.slice(0,300).map(a => ({text:(a.innerText||a.textContent||'').trim(), href:a.href || a.dataset.href || a.dataset.url || '', cls:a.className})).filter(x => x.text)")
        course_data=[]
        for item in responses:
            payload=item.get('json') if isinstance(item,dict) else None
            if isinstance(payload,dict) and isinstance(payload.get('data'),dict) and isinstance(payload['data'].get('list'),list):
                course_data.extend(payload['data']['list'])
        context.storage_state(path=str(state))
        result={'cookies':cookies,'courses':links,'course_data':course_data,'links':links,'cards':cards,'title':page.title(),'body':page.locator('body').inner_text()[:20000],'responses':responses[-300:]}
        out.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        browser.close()

if __name__ == '__main__':
    run_browser_session(Path(sys.argv[1]), Path(sys.argv[2]))
