# -*- coding: utf-8 -*-
"""临时探测 3：标签搜索 + 登录页面结构。"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

# 1. 帖子页 HTML（找前端搜索用的 API）
try:
    r = requests.get(BASE + "/posts", headers=HEADERS, timeout=20)
    html = r.text
    print("GET /posts status=", r.status_code, "len=", len(html))
    # 找 script 引用和 API 线索
    import re
    for m in re.findall(r'src="([^"]+\.js[^"]*)"', html):
        print("  script:", m)
    for m in re.findall(r'href="([^"]+\.css[^"]*)"', html):
        print("  css:", m)
except Exception as e:
    print("posts error:", e)

print()

# 2. 带标签参数的帖子页（看是否 SSR 渲染出结果）
try:
    r = requests.get(BASE + "/posts?tags=furry", headers=HEADERS, timeout=20)
    html = r.text
    print("GET /posts?tags=furry status=", r.status_code, "len=", len(html))
    # 查找帖子卡片特征
    if "post-card" in html or "post__card" in html:
        print("  含帖子卡片（SSR）")
    else:
        print("  无帖子卡片（客户端渲染）")
except Exception as e:
    print("posts?tags error:", e)

print()

# 3. 登录页面
try:
    r = requests.get(BASE + "/login", headers=HEADERS, timeout=20)
    html = r.text
    print("GET /login status=", r.status_code, "len=", len(html))
    # 找表单和 API 线索
    import re
    forms = re.findall(r'<form[^>]*>', html)
    print("  forms:", forms[:3])
    for kw in ["api", "session", "password", "csrf"]:
        idx = html.lower().find(kw)
        if idx >= 0:
            print(f"  '{kw}' found at {idx}:", html[max(0,idx-40):idx+80].replace("\n", " ")[:120])
except Exception as e:
    print("login error:", e)

print()

# 4. Kemono 常见登录 API
for ep in ["/api/v1/authentication/login", "/api/v1/account/login", "/api/authentication/login"]:
    try:
        r = requests.get(BASE + ep, headers=HEADERS, timeout=15)
        print(f"GET {ep} -> {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"GET {ep} -> {type(e).__name__}")
