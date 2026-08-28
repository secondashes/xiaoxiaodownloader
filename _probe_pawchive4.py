# -*- coding: utf-8 -*-
"""临时探测 4：分析 SSR 页面结构 + 找登录入口。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 解析 /posts?tags=furry 的卡片结构
r = requests.get(BASE + "/posts?tags=furry", headers=HEADERS, timeout=20)
html = r.text
print("=== /posts?tags=furry 分析 ===")
# 找一个帖子卡片的完整 HTML
m = re.search(r'<article[^>]*>.*?</article>', html, re.S)
if m:
    card = m.group(0)
    print(card[:1500].encode("gbk", "replace").decode("gbk"))
else:
    # 尝试其他容器
    m = re.search(r'<a[^>]*href="/post/[^"]*"[^>]*>.*?</a>', html, re.S)
    if m:
        print("A 标签:", m.group(0)[:800].encode("gbk", "replace").decode("gbk"))
    else:
        print("未找到卡片，前 2000 字符:")
        print(html[:2000].encode("gbk", "replace").decode("gbk"))

print()

# 2. 找分页信息
pages = re.findall(r'href="([^"]*(?:offset|page|prev|next)[^"]*)"', html)
print("分页链接:", pages[:10])

# 3. 找登录入口（在首页 HTML 里找 account/session 相关链接）
r2 = requests.get(BASE + "/", headers=HEADERS, timeout=20)
html2 = r2.text
print()
print("=== 首页导航链接 ===")
for m in re.findall(r'href="(/[^"]*)"', html2)[:30]:
    print("  ", m)
print()
# 找 login/signin/account 相关词
for kw in ["login", "signin", "sign-in", "account", "session", "favorites", "follow"]:
    for m in re.finditer(kw, html2, re.I):
        ctx = html2[max(0, m.start()-60):m.start()+80].replace("\n", " ")
        print(f"[{kw}]:", ctx.encode("gbk", "replace").decode("gbk")[:140])
        break
