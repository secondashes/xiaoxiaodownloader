# -*- coding: utf-8 -*-
"""临时探测 5：登录表单 + 创作者页面结构。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 登录页表单
r = requests.get(BASE + "/account/login?location=/", headers=HEADERS, timeout=20)
print("=== /account/login status=", r.status_code, "len=", len(r.text))
forms = re.findall(r'<form[^>]*>.*?</form>', r.text, re.S)
for f in forms[:2]:
    print(f[:1200].encode("gbk", "replace").decode("gbk"))
    print("---")

# 找所有 input
inputs = re.findall(r'<input[^>]*>', r.text)
print("inputs:", [i[:100] for i in inputs[:10]])

print()

# 2. 创作者页（BOKABA patreon 30500811）
r2 = requests.get(BASE + "/patreon/user/30500811", headers=HEADERS, timeout=20)
print("=== /patreon/user/30500811 status=", r2.status_code, "len=", len(r2.text))
if r2.status_code == 200:
    html = r2.text
    # 找标题
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if m:
        print("H1:", m.group(1).strip()[:100])
    # 找帖子卡片数量
    cards = re.findall(r'class="post-card', html)
    print("帖子卡片数:", len(cards))
    # 找分页
    pages = re.findall(r'href="([^"]*offset[^"]*)"', html)
    print("分页链接:", pages[:5])
    # 找 tag
    tags = re.findall(r'href="/posts\?tags=[^"]*"[^>]*>([^<]*)</a>', html)
    print("tags:", tags[:10])
    # 关注按钮
    follow = re.findall(r'(follow|subscribe)[^>]{0,60}', html[:5000], re.I)
    print("follow 相关:", follow[:5])
