# 小鹅通课程本地下载器

本机图形程序：在浏览器中登录小鹅通，读取账号下的课程，选择具体课时后保存可访问的视频或电子书图片。仅用于保存你有权下载的内容；请遵守课程授权和平台条款。

## 已验证功能

- 浏览器登录后读取课程列表。
- 读取大专栏下的视频、电子书课时。
- 将视频保存为 MP4，将电子书按页保存为原始分辨率图片。
- 数学课程第一节的完整 MP4 和英语电子书的 5 张图片已在 macOS 上实际下载验证。

## 源码运行

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python gui.py
```

启动后依次点击“打开浏览器登录”“读取登录状态和课程”，选中课程并读取课时，再勾选要保存的内容。浏览器登录状态保存在本机 `.browser_session/`；下载文件保存在 `download/`。这些目录已被 Git 忽略。

本项目为独立实现。早期需求探索曾参考 [miaoyc666/xiaoetong-video-downloader](https://github.com/miaoyc666/xiaoetong-video-downloader)，但本仓库不包含该项目的源代码。课程网站的接口可能变化，未验证的课程类型可能需要适配。
