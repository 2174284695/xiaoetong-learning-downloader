#!/usr/bin/env python3
import json, queue, re, subprocess, sys, threading, time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse
from browser_downloader import download_video as download_browser_video
from browser_catalog import discover_lessons
from browser_ebook import download_ebook
from app_runtime import CourseConfig, FROZEN, configure_browser, data_dir, default_download_dir

configure_browser()
BASE=Path(__file__).parent; DATA_DIR=data_dir(); CONFIG_PATH=DATA_DIR/'config.json'; SESSION_DIR=DATA_DIR/'.browser_session'

def parse_url(url):
    u=urlparse(url); parts=(u.hostname or '').split('.')
    app=parts[0] if len(parts)>=3 else ''
    m=re.search(r'/p/course/(?:column|video)/([^/?]+)',u.path)
    product=m.group(1) if m else parse_qs(u.query).get('product_id',[''])[0]
    host='.'.join(parts[1:]) if len(parts)>=3 else 'h5.xiaoeknow.com'
    return app, product, host

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('小鹅通视频下载器'); self.geometry('920x720'); self.minsize(800,600)
        self.proc=None; self.courses=[]; self.chapters=[]; self.cookie=''; self.config_obj=None; self.current_course_index=None; self.load_seq=0; self.ui_queue=queue.Queue(); self._build(); self._load_config(); self._set_state(False); self.after(100,self._drain_ui)
    def _build(self):
        f=ttk.Frame(self,padding=14); f.pack(fill='both',expand=True); f.columnconfigure(1,weight=1); f.rowconfigure(6,weight=1)
        self.vars={k:tk.StringVar() for k in ('download_dir',)}; self.vars['download_dir'].set(str(default_download_dir()))
        ttk.Label(f,text='登录').grid(row=0,column=0,sticky='nw',pady=6)
        bar=ttk.Frame(f); bar.grid(row=0,column=1,columnspan=2,sticky='ew',pady=6)
        self.open_btn=ttk.Button(bar,text='打开浏览器登录',command=self.open_browser); self.open_btn.pack(side='left')
        self.pull_btn=ttk.Button(bar,text='读取登录状态和课程',command=self.pull_login); self.pull_btn.pack(side='left',padx=8)
        self.status=ttk.Label(bar,text='未登录',foreground='#a33'); self.status.pack(side='left')
        ttk.Label(f,text='我的课程').grid(row=1,column=0,sticky='nw',pady=6)
        cf=ttk.Frame(f); cf.grid(row=1,column=1,columnspan=2,sticky='nsew',pady=6); cf.columnconfigure(0,weight=1); cf.rowconfigure(0,weight=1)
        self.course_list=tk.Listbox(cf,selectmode=tk.SINGLE,height=8,exportselection=False); self.course_list.grid(row=0,column=0,sticky='nsew'); cs=ttk.Scrollbar(cf,command=self.course_list.yview); cs.grid(row=0,column=1,sticky='ns'); self.course_list.configure(yscrollcommand=cs.set)
        self.course_list.bind('<<ListboxSelect>>', self._course_selected)
        self.course_btn=ttk.Button(cf,text='读取所选课程章节',command=self.load_chapters); self.course_btn.grid(row=1,column=0,columnspan=2,sticky='w',pady=5)
        ttk.Label(f,text='章节（可多选）').grid(row=2,column=0,sticky='nw',pady=6)
        hf=ttk.Frame(f); hf.grid(row=2,column=1,columnspan=2,sticky='nsew',pady=6); hf.columnconfigure(0,weight=1); hf.rowconfigure(0,weight=1)
        self.chapter_list=tk.Listbox(hf,selectmode=tk.EXTENDED,height=12,exportselection=False); self.chapter_list.grid(row=0,column=0,sticky='nsew'); hs=ttk.Scrollbar(hf,command=self.chapter_list.yview); hs.grid(row=0,column=1,sticky='ns'); self.chapter_list.configure(yscrollcommand=hs.set)
        hb=ttk.Frame(hf); hb.grid(row=1,column=0,columnspan=2,sticky='ew',pady=5)
        self.all_btn=ttk.Button(hb,text='全选',command=lambda:self.chapter_list.select_set(0,'end')); self.all_btn.pack(side='left')
        self.none_btn=ttk.Button(hb,text='清空选择',command=lambda:self.chapter_list.selection_clear(0,'end')); self.none_btn.pack(side='left',padx=6)
        self.down_btn=ttk.Button(hb,text='下载选中章节',command=self.download); self.down_btn.pack(side='right')
        ttk.Label(f,text='下载目录').grid(row=3,column=0,sticky='w',pady=6); ttk.Entry(f,textvariable=self.vars['download_dir']).grid(row=3,column=1,sticky='ew',pady=6); ttk.Button(f,text='选择目录',command=self.choose_dir).grid(row=3,column=2,padx=8)
        ttk.Label(f,text='日志').grid(row=4,column=0,sticky='nw',pady=6); self.log=tk.Text(f,height=8,state='disabled',bg='#f5f5f5'); self.log.grid(row=4,column=1,columnspan=2,sticky='nsew',pady=6); f.rowconfigure(4,weight=1)
    def _set_state(self,ok):
        st='normal' if ok else 'disabled'
        self.course_btn.configure(state=st)
        for x in (self.all_btn,self.none_btn,self.down_btn): x.configure(state='disabled')
    def _course_selected(self,_event=None):
        selected=self.course_list.curselection()
        index=selected[0] if selected else None
        if index==self.current_course_index:return
        self.current_course_index=index; self.load_seq+=1
        self.chapters=[]; self.config_obj=None
        self.chapter_list.delete(0,'end')
        for x in (self.all_btn,self.none_btn,self.down_btn): x.configure(state='disabled')
    def choose_dir(self):
        x=filedialog.askdirectory();
        if x:self.vars['download_dir'].set(x)
    def open_browser(self):
        SESSION_DIR.mkdir(parents=True,exist_ok=True); self.result=SESSION_DIR/'result.json'; self.signal=SESSION_DIR/'continue'; self.result.unlink(missing_ok=True); self.signal.unlink(missing_ok=True)
        cmd=([sys.executable,'--browser-session'] if FROZEN else [sys.executable,str(BASE/'browser_session.py')])+[str(self.result),str(self.signal)]
        self.proc=subprocess.Popen(cmd,cwd=BASE,stdout=subprocess.PIPE,text=True)
        threading.Thread(target=self._watch_browser,daemon=True).start(); self._append('浏览器已启动，请在窗口中完成小鹅通登录')
    def _watch_browser(self):
        if self.proc and self.proc.stdout:
            for line in self.proc.stdout:
                if 'READY' in line:self._append('浏览器登录页已就绪')
    def pull_login(self):
        if not self.proc or self.proc.poll() is not None:
            messagebox.showinfo('请先打开浏览器','先点击“打开浏览器登录”')
            return
        self.pull_btn.configure(state='disabled'); self.signal.touch(); threading.Thread(target=self._read_result,daemon=True).start()
    def _read_result(self):
        for _ in range(120):
            if self.result.exists(): break
            time.sleep(.5)
        try:
            data=json.loads(self.result.read_text(encoding='utf-8'))
            self._call_ui(lambda:self._apply_login_result(data))
        except Exception as e:
            self._append(f'读取失败：{e}')
            self._call_ui(lambda:self.pull_btn.configure(state='normal'))

    def _apply_login_result(self,data):
        try:
            self.cookie='; '.join(f"{c['name']}={c['value']}" for c in data['cookies'] if c.get('value'))
            if not self.cookie: raise RuntimeError('没有读取到登录 Cookie')
            self.courses=[]; self.chapters=[]; self.config_obj=None; self.current_course_index=None; self.load_seq+=1
            seen=set()
            for item in data.get('course_data',[]):
                app=str(item.get('app_id') or item.get('content_app_id') or '')
                product=str(item.get('product_id') or item.get('resource_id') or '')
                title=str(item.get('title') or item.get('name') or '未命名课程')
                key=(app,product)
                if product and key not in seen:
                    seen.add(key); self.courses.append({'title':title,'url':'','app_id':app,'product_id':product,'host':'h5.xiaoeknow.com','raw':item})
            if not self.courses:
                for item in data.get('courses',[]):
                    app,product,host=parse_url(item['href'])
                    key=(app,product,host)
                    if product and key not in seen: seen.add(key); self.courses.append({'title':item['text'],'url':item['href'],'app_id':app,'product_id':product,'host':host,'raw':{}})
            self.course_list.delete(0,'end')
            self.chapter_list.delete(0,'end')
            for c in self.courses:self.course_list.insert('end',c['title'])
            self.status.configure(text=f'已登录，课程 {len(self.courses)} 门',foreground='#187a3d'); self._append(f'登录验证成功，读取到 {len(self.courses)} 门课程'); self._set_state(bool(self.courses))
        except Exception as e:self._append(f'读取失败：{e}')
        finally:self.pull_btn.configure(state='normal')
    def load_chapters(self):
        ix=self.course_list.curselection()
        if not ix:return
        self.current_course_index=ix[0]; self.load_seq+=1; seq=self.load_seq
        self.course_btn.configure(state='disabled')
        c=self.courses[ix[0]]; download_dir=self.vars['download_dir'].get() or 'download'
        threading.Thread(target=self._chapters_worker,args=(c,seq,download_dir),daemon=True).start()
    def _chapters_worker(self,c,seq,download_dir):
        try:
            host,course_id,lessons=discover_lessons(c,SESSION_DIR/'storage_state.json')
            config=CourseConfig(c['app_id'],self.cookie,course_id,download_dir,host,(c.get('raw') or {}).get('user_id',''))
            self._call_ui(lambda:self._show_chapters(lessons,config,c,seq))
        except Exception as e:self._append(f'读取章节失败：{e}')
        finally:self._call_ui(lambda:self.course_btn.configure(state='normal'))

    def _show_chapters(self,lessons,config,course,seq):
        if seq!=self.load_seq:return
        self.chapters=lessons; self.config_obj=config
        course['host']=config.host; course['product_id']=config.product_id
        self.chapter_list.delete(0,'end')
        for item in lessons:
            label=f"{item['group']} / {item['title']}" if item['group'] else item['title']
            self.chapter_list.insert('end',label)
        self._append(f'已读取 {len(lessons)} 节课程内容（视频或电子书）')
        for x in (self.all_btn,self.none_btn,self.down_btn): x.configure(state='normal' if lessons else 'disabled')

    def download(self):
        ix=self.chapter_list.curselection()
        if not ix:return messagebox.showinfo('未选择','请先选择章节')
        if not self.config_obj:return messagebox.showinfo('未读取课程','请先读取所选课程章节')
        chosen=[self.chapters[i] for i in ix]
        details=(self.config_obj.app_id,self.config_obj.host,self.vars['download_dir'].get() or 'download')
        self.down_btn.configure(state='disabled')
        threading.Thread(target=self._download_worker,args=(chosen,details),daemon=True).start()
    def _download_worker(self,ids,details):
        app_id,host,download_dir=details
        for n,item in enumerate(ids,1):
            rid,title=item['id'],item['title']
            self._append(f'开始下载 [{n}/{len(ids)}] {title} [{rid}]')
            downloader=download_ebook if item.get('kind')=='ebook' else download_browser_video
            ok,msg=downloader(
                app_id=app_id, host=host,
                product_id=item['product_id'], resource_id=rid,
                title=(item['group']+' - '+title if item['group'] else title), storage_state=str(SESSION_DIR/'storage_state.json'),
                download_dir=download_dir, log=self._append)
            self._append(('完成' if ok else '失败')+': '+msg)
        self._append('下载结束')
        self._call_ui(lambda:self.down_btn.configure(state='normal'))
    def _load_config(self):
        if CONFIG_PATH.exists():
            try:self.vars['download_dir'].set(json.loads(CONFIG_PATH.read_text()).get('download_dir','download'))
            except Exception:pass
    def _append(self,text):
        self._call_ui(lambda:(self.log.configure(state='normal'),self.log.insert('end',text+'\n'),self.log.see('end'),self.log.configure(state='disabled')))
    def _call_ui(self,callback):
        self.ui_queue.put(callback)
    def _drain_ui(self):
        while not self.ui_queue.empty():
            self.ui_queue.get_nowait()()
        self.after(100,self._drain_ui)
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--browser-session':
        from browser_session import run_browser_session
        run_browser_session(Path(sys.argv[2]),Path(sys.argv[3]))
    elif len(sys.argv)>2 and sys.argv[1]=='--self-test':
        from app_runtime import ffmpeg_path
        from playwright.sync_api import sync_playwright
        result={'ffmpeg':ffmpeg_path()}
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(); page.goto('about:blank')
            result['browser']=page.url
            browser.close()
        Path(sys.argv[2]).write_text(json.dumps(result),encoding='utf-8')
    else:
        App().mainloop()
