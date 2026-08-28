# -*- coding: utf-8 -*-
"""临时探测 8：帖子页真实媒体 URL + 前端 JS 的分页方式。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 帖子页 HTML 找所有图片 URL
r = requests.get(BASE + "/fanbox/user/13774247/post/12487176", headers=HEADERS, timeout=20)
print("=== 帖子页 status=", r.status_code, "len=", len(r.text))
html = r.text

# 所有 img src
imgs = re.findall(r'src="([^"]+)"', html)
print("图片 src 列表:")
for u in imgs:
    if "static" not in u and "logo" not in u:
        print("  ", u[:110])

# 所有链接
hrefs = re.findall(r'href="([^"]+)"', html)
data_links = [h for h in hrefs if "/data" in h or "img" in h]
print("data/img 链接:")
for u in data_links[:10]:
    print("  ", u[:110])

# 找 a[download] 或文件链接
downloads = re.findall(r'download[^>]*href="([^"]+)"', html) + re.findall(r'href="([^"]+)"[^>]*download', html)
print("download 链接:", [d[:100] for d in downloads[:5]])

print()
# 2. 检查全局 JS bundle 中的 API 线索（分页端点）
r2 = requests.get(BASE + "/static/bundle/assets/global-Beu6GV0_.js", headers=HEADERS, timeout=30)
js = r2.text
print("=== global JS len=", len(js))
# 找 api 调用
api_calls = re.findall(r'["\'](/api/v1/[^"\']+)["\']', js)
print("JS 中的 API 端点:")
for a in sorted(set(api_calls)):
    print("  ", a)

# 找 offset/limit 相关
for m in re.finditer(r'(offset|cursor|page)[=:][^,;]{0,40}', js[:200000]):
    s = m.group(0)[:60]
    print("  分页线索:", s)
    if m.start() > 5000:
        break
