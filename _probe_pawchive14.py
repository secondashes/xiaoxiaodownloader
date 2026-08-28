# -*- coding: utf-8 -*-
"""临时探测 14：画师页 q/tags 过滤验证 + 关注 API。"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,*/*",
    "Referer": "https://pawchive.pw/",
}

BASE = "https://pawchive.pw"

def sp(*args):
    text = " ".join(str(a) for a in args)
    print(text.encode("gbk", "replace").decode("gbk"))

# 1. 无过滤基线
r0 = requests.get(BASE + "/patreon/user/30500811", headers=HEADERS, timeout=20)
base_cards = re.findall(r'data-id="(\d+)"', r0.text)
base_titles = re.findall(r'<header class="post-card__header">\s*(.*?)\s*</header>', r0.text, re.S)
sp("基线卡片数:", len(base_cards))
sp("基线标题样本:", [t.strip()[:30] for t in base_titles[:5]])

# 2. q 参数（标题搜索）
r1 = requests.get(BASE + "/patreon/user/30500811?q=TEST", headers=HEADERS, timeout=20)
q_cards = re.findall(r'data-id="(\d+)"', r1.text)
q_titles = re.findall(r'<header class="post-card__header">\s*(.*?)\s*</header>', r1.text, re.S)
sp()
sp("q=TEST 卡片数:", len(q_cards), "| 标题:", [t.strip()[:30] for t in q_titles[:5]])

# 3. tags 参数（真实 tag 测试）
r2 = requests.get(BASE + "/patreon/user/30500811?tags=furry", headers=HEADERS, timeout=20)
t_cards = re.findall(r'data-id="(\d+)"', r2.text)
print("tags=furry 卡片数:", len(t_cards))

# 4. 关注/收藏按钮 API（画师页上的按钮）
html = r0.text
# 找 favorite/follow 相关的按钮和端点
fav_btns = re.findall(r'(favorite|follow|subscribe)[^"]*"[^>]*', html[:10000], re.I)
print()
print("关注/收藏按钮线索:", fav_btns[:8])
# 找 hx-post / hx-get（htmx 交互）
hx_posts = re.findall(r'hx-(post|get|delete)="([^"]*)"', html)
print("hx 请求:", hx_posts[:10])
# 找 api 端点
api_in_html = re.findall(r'/api/v1/[a-z_/{}]+', html)
print("HTML 中的 API:", sorted(set(api_in_html))[:10])
