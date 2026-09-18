# -*- coding: utf-8 -*-
"""FC2 站点模块（通用站点框架，复制自 site_template.py；接入清单见
任务中心/任务清单/FC2站-通用框架接入-任务清单.md）。

考古结论（2026-09-10 真站探针 + yt-dlp FC2IE）：
- 免费列表：/a/search/video/free/?page=N（50/页）；搜索 /a/search/video/?keyword=X&page=N
  （子分区 /free/ /follow/ /friend/ /funclub/ /premium/；category_id= 分类筛选）
- 内容页 /a/content/{id}：SSR HTML，内嵌 window.FC2VideoObject.push(['ae', '<32hex>'])
- 播放：GET /api/v3/videoplayer/{id}?{ae}=1&tk=&fs=0&token= →
        GET /api/v3/videoplaylist/{id}?sh=1&fs=0 → {type:1|2, playlist:{nq|hq|sample: url}}
        type 1 = mp4 直链（vip-videoprem*.fc2.com，mid 签名）；匿名免费=nq，付费=sample 剪切版，hq 需 Premium
- 相关推荐：/api/v3/video/{id}/suggest?format=html&lang=cn&adult=true&sell=true →
        JSON {found, html}，卡片 .c-boxList-sub（a[href=/a/content/..] + c-videoLength-101 时长）
- 上传者：/a/account/{id}
- 风控：高频请求 API 会整体临时 401（IP 级，冷却恢复）——全站节流 + 401 退避重试

模块级名字会被 _state.register 注入 bridge 扁平命名空间（跨段引用直接写名字）。
"""
from __future__ import annotations

from . import _state as _state

_state.apply_prev(globals())  # 注入此前已加载模块的全部名字（requests/emit/…；注册后本行必需）

import asyncio
import json
import logging
import re
import time

# ============================
# 0. 站点标识
# ============================
SITE_KEY = "fc2"
SITE_NAME = "FC2"

FC2_BASE = "https://video.fc2.com"
FC2_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ============================
# 1. 会话 / 代理 / 节流
# ============================
_fc2_session = requests.Session()  # noqa: F821
_fc2_session.headers.update({"User-Agent": FC2_UA, "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8"})
# 受控 cookie dict（浏览器语义）：请求时构建 Cookie 头，响应 Set-Cookie 回写——
# 避免 JAR 多域同名 cookie（fc2.com + video.fc2.com 各一份 PHPSESSID）互相覆盖导致会话混乱
_fc2_cookies = {"_ac": "1", "GDPRCHECK": "true"}
_fc2_proxy = ""
_fc2_last_ts = 0.0


def _fc2_cookie_header() -> str:
    """当前 cookie dict → Cookie 头。"""
    return "; ".join(f"{k}={v}" for k, v in _fc2_cookies.items() if v)


_fc2_login_ok = False        # 最近一次 check_login 结果（登录态下才允许回写账号档案）


def fc2_is_login_ok() -> bool:
    """最近一次 fc2_check_login 是否网络确认登录。

    供 command_loop 判定——_state 机制是名字值拷贝，跨模块直读 _fc2_login_ok
    变量拿到的是注册时的快照，必须走函数。"""
    return _fc2_login_ok
_fc2_last_cred_sync = 0.0


def _fc2_sync_cred_cookie() -> None:
    """登录态下把轮换后的最新会话回写加密账号档案（60s 节流）。

    此前运行时轮换的新会话只活在进程内 dict——重启后 restore 拿到的是登录时刻的
    旧快照（服务端早已轮换作废）→ 每次重启都要求重新登录。"""
    global _fc2_last_cred_sync
    if not _fc2_login_ok:
        return
    now = time.time()
    if now - _fc2_last_cred_sync < 60:
        return

    def _sid(s: str) -> str:
        m = re.search(r'PHPSESSID=([^;]+)', s or "")
        return m.group(1) if m else ""

    new_str = _fc2_cookie_header()
    if not _sid(new_str):
        return
    try:
        if _sid(new_str) == _sid(_generic_cookie_str("fc2")):  # noqa: F821
            _fc2_last_cred_sync = now     # 会话未轮换，无需写
            return
        cred = _generic_load_cookies("fc2")  # noqa: F821
        if not cred.get("cookie_str"):
            return
        cred["cookie_str"] = new_str
        _secure_store_write_cred("fc2", cred)  # noqa: F821
        _fc2_last_cred_sync = now
    except Exception:
        pass


def fc2_proxy() -> str:
    """当前 FC2 代理（media_proxy 跨模块调用：函数绑定定义模块 globals，取值不 stale）。"""
    return _fc2_proxy


FC2_DEFAULT_PROXY = "http://127.0.0.1:10809"


def fc2_set_proxy(proxy: str) -> None:
    """设置 FC2 代理（空 = 默认代理；FC2 国内必须代理，webview 登录同样依赖）。"""
    global _fc2_proxy
    _fc2_proxy = (proxy or "").strip() or FC2_DEFAULT_PROXY
    if not _fc2_proxy.startswith("http"):
        _fc2_proxy = "http://" + _fc2_proxy
    _fc2_session.proxies.update(
        {"http": _fc2_proxy, "https": _fc2_proxy} if _fc2_proxy else {})
    emit({"event": "fc2_proxy_set", "proxy": _fc2_proxy})  # noqa: F821


def _fc2_restore_session() -> None:
    """把保存的登录 cookie 合并进受控 cookie dict（浏览/播放/下载自动带会话）。"""
    cookie_str = _generic_cookie_str("fc2")  # noqa: F821 —— 通用凭据（fc2 已入 _GENERIC_OAUTH_SITES）
    if cookie_str:
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            idx = pair.find("=")
            if idx > 0:
                _fc2_cookies[pair[:idx].strip()] = pair[idx + 1:].strip()


def fc2_rollback_session(cookie_str: str) -> None:
    """把会话 dict 回滚为指定 cookie 字符串。

    前端 NEED_LOGIN 触发同步推来的分区 cookie 可能是游客会话（用户在内置浏览器
    打开过 FC2 页面即降级游客），fc2_set_cookies 覆盖档案后网络校验若发现并非
    登录态，用此函数把内存与档案一并回滚到推入前的会话（避免冲掉轮换保存的登录会话）。"""
    _fc2_cookies.clear()
    _fc2_cookies["_ac"] = "1"
    _fc2_cookies["GDPRCHECK"] = "true"
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        idx = pair.find("=")
        if idx > 0:
            _fc2_cookies[pair[:idx].strip()] = pair[idx + 1:].strip()


def fc2_check_login(silent: bool = False) -> None:
    """FC2 登录态检查（网络验证）：游客页头部含 c-header_main_login 登录块，登录后消失。"""
    logged_in = False
    username = ""
    network_issue = False
    cred = _generic_load_cookies("fc2")  # noqa: F821
    if cred.get("cookies"):
        _fc2_restore_session()
        try:
            r = _fc2_get("/a/")
            if r is not None and r.status_code == 200:
                # 登录后头部显示 c-header_main_userName（实测 yuejiaxiaosi 2026-09-10）——最强信号
                mu = re.search(r'c-header_main_userName">\s*([^<]{1,40}?)\s*<', r.text)
                if mu:
                    logged_in = True
                    username = mu.group(1)
                    if cred.get("username") != username:
                        cred["username"] = username
                        _secure_store_write_cred("fc2", cred)  # noqa: F821
                else:
                    logged_in = "c-header_main_login" not in r.text
        except Exception:
            network_issue = True
            logged_in = True  # 网络异常时降级为 cookie 存在判定，避免误报未登录
    global _fc2_login_ok
    # 网络异常降级时不能置登录标志——否则游客会话的 Set-Cookie 轮换会把游客会话
    # 回写加密账号档案，污染轮换保存的登录会话（反复要求重新登录的元凶之一）
    _fc2_login_ok = bool(logged_in) and not network_issue
    emit({"event": "site_login_result", "site": "fc2", "silent": silent,
          "logged_in": logged_in, "username": username,
          "cookie_count": len(cred.get("cookies") or {}),
          "message": ("FC2 已登录" if logged_in else
                      ("网络异常，登录态结果可能不准" if network_issue else
                       "FC2 未登录（点左侧按钮在内置浏览器登录）")),
          "network_issue": network_issue})


def _fc2_throttle(min_gap: float = 0.6) -> None:
    """全站节流（默认 0.6s/请求；API 风控为 IP 级累计计数，量大后整体 401 一段时间）。

    原 1.2s 间隔在批量并发解析下过慢（92 个视频近 2 分钟）——实测 0.6s 稳定。"""
    global _fc2_last_ts
    wait = min_gap - (time.time() - _fc2_last_ts)
    if wait > 0:
        time.sleep(wait)
    _fc2_last_ts = time.time()


def _fc2_get(path_or_url: str, referer: str = "", xhr: bool = False,
             headers_extra: dict | None = None) -> requests.Response | None:  # noqa: F821
    """同步 GET（节流；xhr=True 带 AJAX 头；headers_extra 可覆盖如 Cookie）。

    FC2 网关会间歇性掐断连接（SSL EOF/超时）→ 3 次重试指数退避。"""
    url = path_or_url if path_or_url.startswith("http") else f"{FC2_BASE}{path_or_url}"
    headers = {"Referer": referer or FC2_BASE + "/"}
    if xhr:
        headers.update({"X-Requested-With": "XMLHttpRequest", "Accept": "*/*"})
    if headers_extra:
        headers.update(headers_extra)
    if "Cookie" not in headers:   # headers_extra 显式 Cookie（如匿名回退）优先
        headers["Cookie"] = _fc2_cookie_header()
    last_exc: Exception | None = None
    for attempt in range(3):
        _fc2_throttle()
        try:
            resp = _fc2_session.get(url, headers=headers, timeout=30, allow_redirects=True)
            # 响应 Set-Cookie 回写（服务端轮换会话 → dict 自然更新）；
            # 登录态下顺带持久化最新会话到账号档案（重启恢复不拿死会话）
            for c in resp.cookies:
                if c.value:
                    _fc2_cookies[c.name] = c.value
            _fc2_sync_cred_cookie()
            return resp
        except requests.RequestException as exc:  # noqa: F821
            last_exc = exc
            logging.warning("FC2 GET 失败(第 %d 次) %s: %s", attempt + 1, url, exc)
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    logging.error("FC2 GET 重试耗尽 %s: %s", url, last_exc)
    return None


_AE_RE = re.compile(r"FC2VideoObject\.push\(\['ae',\s*'([0-9a-f]{32})'\]")


def _fc2_login_wall(html: str) -> bool:
    """登录墙判定：login.html 模板页（瞬态空结果/限制页都会带此标记）。

    注意：c-header_main_login 在正常列表页也会出现（不能作为判定依据）。"""
    return bool(html) and "login.html" in html[:3000]


def _fc2_fetch_page(path: str, referer: str = "") -> requests.Response:
    """抓列表/详情页（3 次尝试）：瞬时空结果页/登录墙 → 轮换保存 cookie 与干净匿名 cookie 重试。

    正常页特征：200 + 页面 >40KB 且无 login.html 标记。"""
    last = None
    for attempt in range(3):
        if attempt == 0:
            r = _fc2_get(path, referer=referer or FC2_BASE + "/")
        else:
            time.sleep(2 * attempt)
            cookie = _fc2_session.headers.get("Cookie") or "_ac=1; GDPRCHECK=true"
            if attempt == 2:
                cookie = "_ac=1; GDPRCHECK=true"  # 末次固定干净匿名 cookie
            r = _fc2_get(path, referer=referer or FC2_BASE + "/",
                         headers_extra={"Cookie": cookie})
        if r is not None:
            last = r
            if r.status_code == 200 and len(r.text) > 40000 and not _fc2_login_wall(r.text):
                return r
    return last


def _fc2_ae_from_page(html: str) -> str:
    m = _AE_RE.search(html or "")
    return m.group(1) if m else ""


# ============================
# 2. 页面解析（SSR HTML，无框架 JSON）
# ============================
_CARD_ID_RE = re.compile(r'/(?:a/)?content/([0-9A-Za-z]{12,20})')


def _fc2_prepare_thumbs(items: list) -> None:
    """缩略图展示准备：本地缓存优先（thumb://local/ 秒开）；未命中走媒体代理。

    FC2 CDN 国内直连超时，裸 URL 首次访问全部挂掉（用户页/搜索"没有预览图"根因，
    旧逻辑只有缓存热了才显示）；后台仍异步落盘（_cache_thumbnails），命中后下次变
    thumb://local 直读。"""
    _apply_cached_thumbnails(items)  # noqa: F821
    for it in items:
        u = it.get("thumbnail") or ""
        if u.startswith("http"):
            it["thumbnail"] = media_proxy_url(u)  # noqa: F821


def _fc2_card_from_html_block(block: str, vid: str, html: str = "") -> dict:
    """从一段卡片 HTML 提取条目（标题/缩略图/时长）。"""
    title = ""
    # 标题锚（结构化）：c-boxList-111_video_ttl（列表）——aria-label="thumbnail link" 是
    # 缩略图链接的标签而非标题，绝不能作为标题来源
    mt = re.search(r'_video_ttl[^>]*>\s*([^<]{1,200}?)\s*</a>', block)
    if mt:
        title = mt.group(1).strip()
    if not title:
        m = re.search(r'title="([^"]+)"', block)
        if m and 'thumbnail' not in m.group(1).lower():
            title = m.group(1)
    img = ""
    # 兼容 url(...) 与 url('...')（用户页/收藏页的 background-image 带单引号——
    # 此前只匹配无引号形式，用户页视频缩略图全部提取失败）
    mi = re.search(r'(?:background-image:\s*url\([\'"]?|src=[\'"])(https?://[^)\'"]+(?:thumb|pic)[^)\'"]*)', block)
    if mi:
        img = mi.group(1)
    dur = ""
    md = re.search(r'c-videoLength-101">\s*([0-9:]+)\s*<', block)
    if md:
        dur = md.group(1)
    # 上传时间（相对，如 3 年前）+ 可见范围标签（全員/無料/R-18）
    posted = ""
    mp = re.search(r'contentUpdateDate[^>]*>\s*([^<]{1,24})\s*<', block)
    if mp:
        posted = mp.group(1).strip()
    access = ""
    ma = re.search(r'class="text ([a-z]+)">([^<]{1,10})<', block)
    if ma:
        access = {"all": "全員", "free": "無料"}.get(ma.group(1), ma.group(2))
    # 上传者（搜索/列表卡片的 postBy 块：by <a href=".../a/member?mid={id}">名字</a>；
    # mid 是上传者数字 id，归一成 /a/account/{id} 供前端作者跳转）
    author = ""
    author_url = ""
    mby = re.search(r'postBy[^>]*>\s*by(?:&nbsp;|\s)+<a href="([^"]+)"[^>]*>([^<]{1,40}?)</a>', block)
    if mby:
        author = mby.group(2).strip()
        mm = re.search(r'mid=(\d+)', mby.group(1))
        author_url = f"{FC2_BASE}/a/account/{mm.group(1)}" if mm else _fc2_abs_url(mby.group(1))
    return {
        "album_name": title.strip() or f"FC2 {vid}",
        "album_url": (f"{FC2_BASE}/a/content/{vid}" if vid.startswith("a_") else f"{FC2_BASE}/content/{vid}"),
        "thumbnail": img,
        "files": 1,
        "site": "fc2",
        "video_id": vid,
        "author": author,
        "author_url": author_url,
        "views": "",
        "likes": "",
        "rating": "",
        "duration": dur,
        "duration_sec": 0,
        "created": "",
        "posted": posted,
        "access": access,
        "is_hd": False,
        "kind": "video",
    }


def _fc2_parse_list(html: str, limit: int = 60) -> list[dict]:
    """列表页 → 卡片数组（按 content id 去重保序）。

    标题取链接之后的第一个锚文本（链接前的 title= 属性可能是轮播横幅广告文案）。"""
    items: list[dict] = []
    seen: set[str] = set()
    for m in _CARD_ID_RE.finditer(html or ""):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        after = html[m.end():m.end() + 700]
        tm = re.search(r'>\s*([^<>]{4,140})\s*</a>', after)
        block = html[m.start():m.end() + 2500]
        card = _fc2_card_from_html_block(block, vid, html)
        if tm and not re.match(r"^(https?:|//)", tm.group(1).strip())                 and "thumbnail" not in tm.group(1).lower():
            card["album_name"] = tm.group(1).strip()
        items.append(card)
        if len(items) >= limit:
            break
    return items


def _fc2_parse_max_page(html: str) -> int:
    pgs = [int(x) for x in re.findall(r'[?&]page=(\d+)', html or "")]
    return max(pgs) if pgs else 0


# ============================
# 3. 播放源（videoplayer + videoplaylist；401 风控退避重试一次）
# ============================
def _fc2_play_urls(vid: str, referer: str) -> dict:
    """返回 {quality: url}（nq/hq/sample）+ type（1=mp4 2=m3u8）。

    匿名调用 API 必须不带 PHPSESSID（游客会话会被判 401，实测 2026-09-10）——
    页面取 ae 后，API 请求改用干净 Cookie 头；登录用户保留完整登录 cookie。"""
    page = _fc2_get(f"/a/content/{vid}", referer=FC2_BASE + "/")
    if page is None or page.status_code != 200:
        raise PermissionError("FC2 内容页获取失败")
    ae = _fc2_ae_from_page(page.text)
    if not ae:
        raise PermissionError("FC2 页面缺少播放凭据（可能已下架或风控）")
    # 过期登录会话会被 FC2 掐断连接（实测）：API 默认剥离会话 cookie（匿名可播免费视频），
    # 401 时再带完整登录 cookie 重试（登录内容场景）
    _session_keys = ("PHPSESSID", "FCSID")
    clean_cookie = "; ".join(f"{k}={v}" for k, v in _fc2_cookies.items()
                             if k not in _session_keys and v) or "_ac=1; GDPRCHECK=true"
    login_cookie = _fc2_cookie_header()
    api_cookie = clean_cookie
    h = {"Referer": base_referer(vid), "X-Requested-With": "XMLHttpRequest",
         "Accept": "*/*", "Cookie": api_cookie}
    def _vp(ae_val, ck):
        return _fc2_get(f"/api/v3/videoplayer/{vid}?{ae_val}=1&tk=&fs=0&token=",
                        referer=base_referer(vid), xhr=True, headers_extra={"Cookie": ck})

    def _pl(ck):
        return _fc2_get(f"/api/v3/videoplaylist/{vid}?sh=1&fs=0",
                        referer=base_referer(vid), xhr=True, headers_extra={"Cookie": ck})

    r1 = _vp(ae, api_cookie)
    if r1 is None or r1.status_code != 200:
        # 风控退避：冷却 8s 重拉页面换新 ae；先匿名重试，再登录 cookie 重试
        time.sleep(8)
        page = _fc2_get(f"/a/content/{vid}", referer=FC2_BASE + "/")
        ae = _fc2_ae_from_page(page.text) if page is not None else ""
        if not ae:
            raise PermissionError("FC2 播放凭据获取失败（风控限流，请稍后重试）")
        for ck in (clean_cookie, login_cookie):
            if not ck or ck == api_cookie:
                continue
            r1 = _vp(ae, ck)
            if r1 is not None and r1.status_code == 200:
                api_cookie = ck
                break
        if r1 is None or r1.status_code != 200:
            raise PermissionError(f"FC2 播放器接口失败（HTTP {r1.status_code if r1 else '无响应'}，风控限流请稍后重试）")
    r2 = _pl(api_cookie)
    if r2 is None or r2.status_code != 200:
        raise PermissionError(f"FC2 播放列表接口失败（HTTP {r2.status_code if r2 else '无响应'}）")
    data = r2.json()
    pl = data.get("playlist") or {}
    urls = {k: _fc2_abs_url(v) for k, v in pl.items() if isinstance(v, str) and v}
    urls["__type"] = str(data.get("type") or "1")
    return urls


def base_referer(vid: str) -> str:
    return f"{FC2_BASE}/a/content/{vid}"


def _fc2_abs_url(u: str) -> str:
    u = (u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    elif u and not u.startswith("http"):
        u = FC2_BASE + u
    return u


def _fc2_best(quality_urls: dict) -> tuple[str, str]:
    """选最高可用画质：hq > nq > sample（匿名实际能拿到的最高档）。"""
    for key in ("hq", "nq", "sample"):
        if quality_urls.get(key):
            return key, quality_urls[key]
    for k, v in quality_urls.items():
        if k != "__type" and v:
            return k, v
    return "", ""


# ============================
# 4. 命令实现（gs_state 契约）
# ============================
_fc2_last_view = "home"
_fc2_last_state: dict | None = None   # 最近一次完整 gs_state（批次进度合并回传保持视图内容）


def _gs_emit(state: dict) -> None:
    global _fc2_last_view, _fc2_last_state
    if state.get("view"):
        _fc2_last_view = state["view"]
    _fc2_last_state = dict(state)
    emit({"event": "gs_state", "site": SITE_KEY, **state})  # noqa: F821


def _fc2_batch_progress(message: str, done: int, total: int, failed: list | None = None) -> None:
    """批次进度：保持当前视图与内容（items/detail 合并回传），只附加 batchProgress。

    此前只发 view+batchProgress → App 整替换 gs_state 后 items/detail 丢失 → 界面清空。"""
    base = dict(_fc2_last_state or {"view": _fc2_last_view})
    base["loading"] = False
    base["batchProgress"] = {"message": message, "done": done, "total": total}
    if failed:
        base["failed"] = failed
    _gs_emit(base)


async def fc2_home(page: int = 1, tab: str = "new") -> None:
    """首页三 Tab：recommend=推荐（/a/ 顶部）｜new=新着（免费区）｜popular=人气（免费 sort）。"""
    _gs_emit({"view": "home", "items": [], "loading": True, "page": page, "tab": tab})
    try:
        page = max(1, page or 1)
        if tab == "recommend":
            path = "/a/" + (f"?page={page}" if page > 1 else "")
            label = f"FC2 推荐 · 第 {page} 页"
        elif tab == "popular":
            path = "/a/search/video/free/?sort=popular" + (f"&page={page}" if page > 1 else "")
            label = f"FC2 人气 · 第 {page} 页"
        else:
            tab = "new"
            path = "/a/search/video/free/" + (f"?page={page}" if page > 1 else "")
            label = f"FC2 新着 · 第 {page} 页"
        r = await asyncio.to_thread(_fc2_fetch_page, path)
        if r is None or r.status_code != 200:
            raise PermissionError(f"列表获取失败（HTTP {r.status_code if r else '无响应'}，可能风控限流）")
        if _fc2_login_wall(r.text):
            raise PermissionError("NEED_LOGIN: 该列表需要登录 FC2（请在左侧登录后重试）")
        items = _fc2_parse_list(r.text)
        max_page = _fc2_parse_max_page(r.text)
        _fc2_prepare_thumbs(items)  # noqa: F821 —— 缓存优先，未命中走媒体代理
        asyncio.create_task(_cache_thumbnails(items))  # noqa: F821
        _gs_emit({"view": "home", "items": items, "page": page, "tab": tab,
                  "has_more": bool(max_page and page < max_page),
                  "total": max_page * 50, "loading": False, "label": label})
    except Exception as exc:
        _gs_emit({"view": "home", "items": [], "loading": False,
                  "tab": tab, "error": f"获取失败: {exc}"})


async def fc2_search(query: str, page: int = 1, tab: str = "") -> None:
    """关键词搜索（tab: ''=全部 /free /premium …）。"""
    from urllib.parse import quote
    query = (query or "").strip()
    if not query:
        _gs_emit({"view": "list", "items": [], "loading": False, "error": "搜索关键词为空"})
        return
    _gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    try:
        page = max(1, page or 1)
        sub = f"/{tab}" if tab else ""
        qs = f"?keyword={quote(query)}" + (f"&page={page}" if page > 1 else "")
        r = await asyncio.to_thread(_fc2_fetch_page, f"/a/search/video{sub}/{qs}")
        if r is None or r.status_code != 200:
            raise PermissionError(f"搜索失败（HTTP {r.status_code if r else '无响应'}）")
        if _fc2_login_wall(r.text):
            raise PermissionError("NEED_LOGIN: 搜索结果需要登录 FC2（请在左侧登录后重试）")
        items = _fc2_parse_list(r.text)
        max_page = _fc2_parse_max_page(r.text)
        _fc2_prepare_thumbs(items)  # noqa: F821
        asyncio.create_task(_cache_thumbnails(items))  # noqa: F821
        _gs_emit({"view": "list", "items": items, "page": page,
                  "has_more": bool(max_page and page < max_page),
                  "loading": False, "label": f"FC2 搜索: {query} · 第 {page} 页"})
    except Exception as exc:
        _gs_emit({"view": "list", "items": [], "loading": False, "error": f"搜索失败: {exc}"})


async def fc2_categories() -> None:
    """分类目录（分类 id 列表供 toolbar 选择）。"""
    _gs_emit({"view": "list", "items": [], "loading": True, "page": 1})
    try:
        r = await asyncio.to_thread(_fc2_fetch_page, "/a/search/video/")
        if r is None or r.status_code != 200:
            raise PermissionError("分类页获取失败")
        html = r.text
        cats = []
        seen = set()
        for m in re.finditer(r'category_id=(\d+)[^>]*>\s*([^<]{1,24})\s*<', html):
            cid, name = m.group(1), m.group(2).strip()
            if cid in seen or not name:
                continue
            seen.add(cid)
            cats.append({"id": cid, "name": name, "count": 0,
                         "kind": "category", "site": "fc2"})
            if len(cats) >= 60:
                break
        _gs_emit({"view": "categories", "items": cats, "loading": False, "label": "FC2 分类"})
    except Exception as exc:
        _gs_emit({"view": "categories", "items": [], "loading": False, "error": f"获取失败: {exc}"})


async def fc2_list(category_id: str = "", page: int = 1, keyword: str = "", tab: str = "") -> None:
    """分类/搜索结果列表。"""
    _gs_emit({"view": "list", "items": [], "loading": True, "page": page})
    try:
        page = max(1, page or 1)
        sub = f"/{tab}" if tab else ""
        params = []
        if category_id:
            params.append(f"category_id={category_id}")
        if keyword:
            from urllib.parse import quote
            params.append(f"keyword={quote(keyword)}")
        if page > 1:
            params.append(f"page={page}")
        qs = ("?" + "&".join(params)) if params else ""
        r = await asyncio.to_thread(_fc2_fetch_page, f"/a/search/video{sub}/{qs}")
        if r is None or r.status_code != 200:
            raise PermissionError(f"列表获取失败（HTTP {r.status_code if r else '无响应'}）")
        if _fc2_login_wall(r.text):
            raise PermissionError("NEED_LOGIN: 该列表需要登录 FC2（请在左侧登录后重试）")
        items = _fc2_parse_list(r.text)
        max_page = _fc2_parse_max_page(r.text)
        _fc2_prepare_thumbs(items)  # noqa: F821
        asyncio.create_task(_cache_thumbnails(items))  # noqa: F821
        _gs_emit({"view": "list", "items": items, "page": page,
                  "has_more": bool(max_page and page < max_page),
                  "loading": False, "label": "FC2 列表"})
    except Exception as exc:
        _gs_emit({"view": "list", "items": [], "loading": False, "error": f"获取失败: {exc}"})


def _fc2_parse_detail_page(html: str, vid: str) -> dict:
    """内容页 → 详情 dict（标题/封面/上传者/标签/相关）。"""
    title = ""
    mt = re.search(r'<title>([^<]+)</title>', html)
    if mt:
        title = re.sub(r"\s*-\s*FC2動画.*$", "", mt.group(1))
        title = re.sub(r"\s*-\s*FC2视频.*$", "", title)
    img = ""
    mi = re.search(r'og:image["\']\s+content="([^"]+)"', html) or \
        re.search(r'og:image"\s+content="([^"]+)"', html) or \
        re.search(r'property="og:image"\s+content="([^"]+)"', html)
    if mi:
        img = mi.group(1)
    desc = ""
    md = re.search(r'og:description"\s+content="([^"]+)"', html)
    if md:
        desc = md.group(1)
    author, author_url, avatar = "", "", ""
    ma = re.search(r'<a class="sellerInfo_image" href="([^"]+/a/account/(\d+))"[^>]*(?:title="([^"]*)")?', html)
    if ma:
        author_url = ma.group(1)
        author = ma.group(3) or ""
    mn = re.search(r'sellerInfo_name[^>]*>\s*<a[^>]*>([^<]+)</a>', html) or \
        re.search(r'sellerInfo_name[^>]*>\s*([^<]+)<', html)
    if mn:
        author = mn.group(1).strip()
    mv = re.search(r'sellerInfo_image"[^>]*background-image:\s*url\(([^)]+)\)', html)
    if mv:
        avatar = mv.group(1)
    tags = [t.strip() for t in re.findall(r'videoTags[^>]*>.*?</a>', html, re.S) if t.strip()][:0]
    return {
        "id": vid,
        "album_name": title.strip() or f"FC2 {vid}",
        "album_url": (f"{FC2_BASE}/a/content/{vid}" if vid.startswith("a_") else f"{FC2_BASE}/content/{vid}"),
        "thumbnail": _fc2_abs_url(img),
        "description": desc,
        "author": author,
        "author_url": _fc2_abs_url(author_url),
        "author_avatar": _fc2_abs_url(avatar),
        "tags": tags,
        "site": "fc2",
    }


def _fc2_parse_suggest(json_text: str) -> list[dict]:
    """相关推荐 JSON {found, html} → 卡片数组。"""
    try:
        d = json.loads(json_text)
    except Exception:
        return []
    html = d.get("html") or ""
    items: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="https://video\.fc2\.com/a/content/([0-9A-Za-z]{12,20})"', html):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        block = html[m.start():m.end() + 600]
        card = _fc2_card_from_html_block(block, vid)
        items.append(card)
        if len(items) >= 12:
            break
    return items


_FC2_CONTENT_URL_RE = re.compile(r"/(?:a/)?content/([0-9A-Za-z]{12,20})")


def is_fc2_url(url: str) -> bool:
    """FC2 内容页链接判定（video.fc2.com/content/{id} 或 /a/content/{id}）。"""
    u = (url or "").lower()
    return "fc2.com/" in u and "/content/" in u


async def fc2_inspect(url: str) -> None:
    """gui_inspect URL 路由：FC2 内容页链接 → 解析并推入 FC2 详情视图。

    兼作本地收藏点击打开与搜索框粘贴 FC2 链接的解析入口（与各站 *_inspect 同型）；
    文件列表保持空 → 前端继续显示 Fc2View 与已推入的详情。此前无分支，FC2 链接
    落到 Bunkr 兜底解析 → 报「无法获取页面」。"""
    m = _FC2_CONTENT_URL_RE.search(url or "")
    if not m:
        emit({"event": "inspect_error", "message": f"无法识别的 FC2 链接: {url}"})  # noqa: F821
        return
    await fc2_detail(m.group(1))
    emit({"event": "inspect_complete", "files": [], "album_name": "", "album_id": url,
          "is_album": False})  # noqa: F821 —— 结束前端解析反馈（不切文件列表视图）


async def fc2_detail(item_id: str) -> None:
    """详情：元数据 + 播放源（内嵌 video 用）+ 文件条目 + 相关推荐。"""
    vid = (item_id or "").strip()
    if not vid:
        m = re.search(r"/content/([0-9A-Za-z]{12,20})", item_id or "")
        vid = m.group(1) if m else ""
    if not vid:
        _gs_emit({"view": "detail", "detail": None, "error": "缺少视频 id"})
        return
    _gs_emit({"view": "detail", "detail": None, "files": [], "loading": True})
    try:
        page = await asyncio.to_thread(_fc2_fetch_page, f"/a/content/{vid}", referer=FC2_BASE + "/")
        if page is None or page.status_code != 200:
            raise PermissionError(f"内容页获取失败（HTTP {page.status_code if page else '无响应'}）")
        if _fc2_login_wall(page.text):
            raise PermissionError("NEED_LOGIN: 该视频需要登录 FC2（请在左侧登录后重试）")
        detail = _fc2_parse_detail_page(page.text, vid)
        detail["file_count"] = 1
        # 播放源（内嵌播放器 + 下载条目共用；失败不阻塞详情展示）
        try:
            urls = _fc2_play_urls(vid, base_referer(vid))
            quality, url = _fc2_best(urls)
            # 播放走本地媒体代理（FC2 CDN 国内直连超时；代理分支带 Referer/FC2 代理）
            detail["play_url"] = media_proxy_url(url)  # noqa: F821
            detail["quality"] = quality
            detail["play_type"] = urls.get("__type", "1")
            detail["is_sample"] = quality == "sample"
        except Exception as exc:
            detail["play_url"] = ""
            detail["play_error"] = str(exc)
        files = [{
            "filename": f"{sanitize_directory_name(detail['album_name']) or 'fc2_' + vid}.mp4",  # noqa: F821
            "size": None,
            "item_page": detail["album_url"],
            "status": "ok",
            "thumbnail": detail.get("thumbnail") or "",
            "media_url": detail.get("play_url") or "",
            "site": "fc2",
            "video_id": vid,
            "post_title": detail["album_name"],
            "post_date": "",
            "artist": detail.get("author") or "FC2",
            "media_type": "video",
            "type": "video",
        }]
        # 相关推荐（失败不阻塞详情展示）
        related: list[dict] = []
        try:
            rs = await asyncio.to_thread(
                _fc2_get, f"/api/v3/video/{vid}/suggest?format=html&lang=cn&vid={vid}&adult=true&sell=true",
                referer=f"{FC2_BASE}/a/content/{vid}", xhr=True)
            if rs is not None and rs.status_code == 200:
                related = _fc2_parse_suggest(rs.text)
        except Exception:
            logging.debug("FC2 相关推荐获取失败", exc_info=True)
        detail["related"] = related
        detail["thumbnail"] = media_proxy_url(detail.get("thumbnail") or "")  # noqa: F821
        _fc2_prepare_thumbs(related)  # noqa: F821
        asyncio.create_task(_cache_thumbnails(related))  # noqa: F821
        _gs_emit({"view": "detail", "detail": detail, "files": files, "loading": False})
    except Exception as exc:
        _gs_emit({"view": "detail", "detail": None, "files": [], "loading": False,
                  "error": f"获取详情失败: {exc}"})


_fc2_user_ctx: dict = {"profile": None, "items": []}   # 用户页资料/累计条目（翻页追加复用）


async def fc2_user(user_id: str, page: int = 1, tab: str = "content", group: str = "adult") -> None:
    """上传者页：资料卡（名字/头像/性别/视频发布/关注/粉丝/好友/简介/关注状态）
    + 内容 Tab（content=视频发布 / album=收藏）。"""
    _gs_emit({"view": "user", "items": [], "loading": True, "page": page, "tab": tab,
              "profile": {"user_id": user_id}})
    try:
        page = max(1, page or 1)
        tab = tab if tab in ("content", "album") else "content"
        # 翻页复用资料（省 1 请求且 counts 不丢）；换用户/Tab/分组（page=1）时重拉
        if page > 1 and (_fc2_user_ctx.get("profile") or {}).get("user_id") == user_id:
            profile = _fc2_user_ctx["profile"]
        else:
            prof_page = await asyncio.to_thread(_fc2_fetch_page, f"/a/account/{user_id}",
                                                referer=FC2_BASE + "/")
            profile = {"user_id": user_id, "name": "", "avatar": "", "gender": "",
                       "intro": "", "stats": {}, "following": False,
                       "follow_url": f"{FC2_BASE}/a/account/{user_id}"}
            if prof_page is not None and prof_page.status_code == 200 and not _fc2_login_wall(prof_page.text):
                ph = prof_page.text
                mt = re.search(r'<title>([^<]+)</title>', ph)
                if mt:
                    profile["name"] = re.sub(r"\s*[-–]\s*FC2(视频|動画).*$", "", mt.group(1)).replace("档案", "").strip()
                mi = re.search(r'og:image"\s+content="([^"]+)"', ph) or                 re.search(r'c-card-user_thumb[^>]*>.*?background-image:\s*url\(([^)]+)\)', ph, re.S)
                if mi:
                    profile["avatar"] = _fc2_abs_url(mi.group(1))
                md = re.search(r'og:description"\s+content="([^"]+)"', ph)
                if md:
                    profile["intro"] = md.group(1)[:500]
                stats = {}
                # 统计键归一化：登录后 FC2 页面随账号语言渲染（日文账号 each_ttl 是
                # 動画投稿/フォロー中/フォロワー/友達），前端按中文键取值会全部落空
                _stat_labels = {
                    "動画投稿": "视频发布", "投稿動画": "视频发布", "動画": "视频发布",
                    "フォロー中": "关注", "フォロー": "关注",
                    "フォロワー": "粉丝", "友達": "好友", "友だち": "好友", "フレンド": "好友",
                }
                # 按 <li class="each"> 块逐块配对（块内 ttl + number 独立提取）——
                # 跨块非贪婪配对在某块 number 缺失/带属性时会错位到相邻块
                for block in re.findall(r'<li class="each">.*?</li>', ph, re.S):
                    t = re.search(r'each_ttl">\s*([^<]{1,20}?)\s*</span>', block)
                    n = re.search(r'each_btm_number"[^>]*>\s*([\d.]+[万k]?)\s*<', block)
                    if t and n:
                        st = _stat_labels.get(t.group(1).strip(), t.group(1).strip())
                        if st and st not in stats:
                            stats[st] = n.group(1)
                profile["stats"] = stats
                mg = re.search(r'性别</th>(.{0,600})', ph, re.S)
                if mg:
                    lbl = re.findall(r'<label for="[^"]*">([^<]+)</label>', mg.group(1))
                    chk = re.search(r'name="gender" value="(\d)"\s*checked', mg.group(1))
                    if lbl and chk:
                        try:
                            profile["gender"] = lbl[int(chk.group(1))]
                        except (IndexError, ValueError):
                            pass
                mf = re.search(r'data-button-follow="unfollow"[^>]*aria-hidden="(false|true)"', ph)
                if mf:
                    profile["following"] = mf.group(1) == "false"
        sub = "album" if tab == "album" else "content"
        prefix = "/a" if group == "adult" else ""
        qs = f"?page={page}" if page > 1 else ""
        r = await asyncio.to_thread(_fc2_fetch_page, f"{prefix}/account/{user_id}/{sub}{qs}",
                                    referer=f"{FC2_BASE}/a/account/{user_id}")
        items: list[dict] = []
        has_more = False
        if r is not None and r.status_code == 200 and not _fc2_login_wall(r.text):
            items = _fc2_parse_list(r.text)
            max_page = _fc2_parse_max_page(r.text)
            has_more = bool(max_page and page < max_page)
            for c in items:
                c["author"] = profile.get("name") or user_id
                c["author_url"] = f"{FC2_BASE}/a/account/{user_id}"
            # 翻页追加（加载更多 = 继续累计浏览，而非替换——作者全部视频可一次滚动看完）
            if page > 1:
                seen = {c.get("video_id") for c in _fc2_user_ctx.get("items", [])}
                items = _fc2_user_ctx.get("items", []) + [c for c in items if c.get("video_id") not in seen]
            _fc2_user_ctx["items"] = items
            _fc2_user_ctx["profile"] = profile

        # 分区数量估算（用户要求 Tab/分组按钮显示数量）：
        # 数量 ≈ (max_page-1)*50 + 第一页条数（FC2 每页 50；max_page=0 视为无内容）。
        # 只在第一页时估算（翻页不重算）；一般区与收藏页各需 1 个额外请求。
        async def _count_region(path: str) -> int:
            rr = await asyncio.to_thread(_fc2_fetch_page, path,
                                         referer=f"{FC2_BASE}/a/account/{user_id}")
            if rr is None or rr.status_code != 200 or _fc2_login_wall(rr.text):
                return 0
            mp = _fc2_parse_max_page(rr.text)
            first = _fc2_parse_list(rr.text, limit=60)
            if mp <= 1:
                return len(first)   # 单页（无分页条或仅一页）——直接数卡片
            # 多页：尾页常不满 50，公式会高估（如 98 估成 100）——拉尾页数实际条数
            rl = await asyncio.to_thread(_fc2_fetch_page, f"{path.split('?')[0]}?page={mp}",
                                         referer=f"{FC2_BASE}/a/account/{user_id}")
            last = _fc2_parse_list(rl.text, limit=60) if (rl is not None and rl.status_code == 200) else []
            return (mp - 1) * 50 + len(last) if last else (mp - 1) * 50 + len(first)

        counts = profile.get("counts") or {}
        if page == 1:
            try:
                # 三个分区统一走 _count_region（含尾页修正——尾页常不满 50，
                # 首页满页公式会高估：98 估成 100）；gather 并行防串行节流拖慢
                ca, cg, gal = await asyncio.gather(
                    _count_region(f"/a/account/{user_id}/content"),
                    _count_region(f"/account/{user_id}/content"),
                    _count_region(f"/a/account/{user_id}/album"),
                )
                counts["adult"] = ca
                counts["general"] = cg
                counts["album"] = gal
            except Exception:
                pass
            # 视频发布 = 成人 + 一般 总数（用户口径；FC2 页面统计块只计部分分区）
            counts["video"] = counts.get("adult", 0) + counts.get("general", 0)
            profile["counts"] = counts
        _fc2_prepare_thumbs(items)  # noqa: F821
        asyncio.create_task(_cache_thumbnails(items))  # noqa: F821
        _gs_emit({"view": "user", "items": items, "page": page, "tab": tab,
                  "has_more": has_more, "profile": profile,
                  "loading": False, "label": f"FC2 上传者 {profile.get('name') or user_id}"})
    except Exception as exc:
        _gs_emit({"view": "user", "items": [], "loading": False,
                  "profile": {"user_id": user_id},
                  "error": f"获取失败: {exc}"})


# ============================
# 5. 下载（解析条目 + 播放源再解析）
# ============================
def fc2_download_info(vid: str) -> dict:
    """返回 {url, quality, type}——下载时现解析（mid 签名会过期）。"""
    urls = _fc2_play_urls(vid, base_referer(vid))
    quality, url = _fc2_best(urls)
    if not url:
        raise PermissionError("FC2 无可用播放源（可能付费内容或风控限流）")
    return {"url": url, "quality": quality, "type": urls.get("__type", "1")}




# ============================
# 6. 命令表
# ============================
_fc2_last_list = {"keyword": "", "tab": "", "category_id": ""}  # load-more 上下文


async def _cmd_home(command: dict) -> None:
    _fc2_last_list.update({"keyword": "", "tab": "", "category_id": ""})
    await fc2_home(int(command.get("page") or 1), str(command.get("tab") or "new"))


async def _cmd_search(command: dict) -> None:
    kw = str(command.get("query") or command.get("keyword") or "")
    if not kw:
        # 全局搜索框发起的搜索，前端"加载更多"只回传 page 不带 query——用上下文关键词兜底，
        # 否则空 kw 会清掉 _fc2_last_list 并搜空词
        kw = str(_fc2_last_list.get("keyword") or "")
    _fc2_last_list.update({"keyword": kw, "tab": str(command.get("tab") or ""), "category_id": ""})
    await fc2_search(kw, int(command.get("page") or 1), str(command.get("tab") or ""))


async def _cmd_categories(command: dict) -> None:
    await fc2_categories()


async def _cmd_list(command: dict) -> None:
    _fc2_last_list.update({"keyword": str(command.get("keyword") or ""),
                           "tab": str(command.get("tab") or ""),
                           "category_id": str(command.get("category_id") or "")})
    await fc2_list(str(command.get("category_id") or ""), int(command.get("page") or 1),
                   str(command.get("keyword") or ""), str(command.get("tab") or ""))


async def _cmd_load_more(command: dict) -> None:
    page = int(command.get("page") or 2)
    ctx = _fc2_last_list
    if ctx.get("keyword"):
        await fc2_search(ctx["keyword"], page, ctx.get("tab") or "")
    elif ctx.get("category_id"):
        await fc2_list(ctx["category_id"], page)
    else:
        await fc2_home(page)


async def _cmd_open_detail(command: dict) -> None:
    """列表卡片点击：item（video_id 或 album_url）→ 详情。"""
    item = command.get("item") or {}
    vid = str(item.get("video_id") or "")
    if not vid:
        m = re.search(r"/content/([0-9A-Za-z]{12,20})", str(item.get("album_url") or ""))
        vid = m.group(1) if m else ""
    await fc2_detail(vid)


async def _cmd_detail(command: dict) -> None:
    await fc2_detail(str(command.get("item_id") or command.get("url") or ""))


async def _cmd_user(command: dict) -> None:
    await fc2_user(str(command.get("user_id") or ""), int(command.get("page") or 1),
                   str(command.get("tab") or "content"), str(command.get("group") or "adult"))


async def _cmd_favorite(command: dict) -> None:
    it = command.get("item") or {}
    # 字段映射：本地收藏契约用 url/title，FC2 卡片是 album_url/album_name
    add_local_favorite({  # noqa: F821
        "url": it.get("album_url") or it.get("url") or "",
        "title": it.get("album_name") or it.get("title") or "",
        "site": "fc2",
        "type": "video",
        "thumbnail": it.get("thumbnail") or "",
    })


async def _cmd_download_files(command: dict) -> None:
    """GSV 详情「下载选中」：files（含 item_page/media_url）→ download_manager 提交。
    mid 签名会过期 → 下载时由 _fc2_download_one 重新解析。"""
    files = [f for f in (command.get("files") or []) if isinstance(f, dict) and f.get("item_page")]
    if not files:
        _fc2_batch_progress("没有可下载的文件", 0, 0)
        return
    artists = {f.get("artist") for f in files if f.get("artist")}
    album = next(iter(artists)) if len(artists) == 1 else "FC2 下载"
    task_id = download_manager.submit(  # noqa: F821
        f"{FC2_BASE}/", files, command.get("options") or {}, album or "FC2 下载",
        f"fc2_batch_{album}",
    )
    download_manager.start(task_id)  # noqa: F821
    _fc2_batch_progress(f"下载已提交：{len(files)} 个文件", len(files), len(files))


async def _cmd_batch_download(command: dict) -> None:
    """批量下载：GSV 只回传勾选 ids → 逐个 解析页面(标题)→播放源 → 提交。"""
    ids = [str(v).strip() for v in (command.get("ids") or []) if str(v).strip()]
    if not ids:
        _fc2_batch_progress("请先勾选要下载的视频", 0, 0)
        return
    total = len(ids)
    failed: list[str] = []
    out: list[dict] = []
    # 占位式批量：先立即创建空任务（下载管理面板秒见、可暂停/取消），
    # 每解析成功一个就增量并入，全部完成后统一 start——
    # 此前全部解析完（几十秒到几分钟）才建任务，用户不知道有没有成功
    task_album_id = f"fc2_batch:{int(time.time() * 1000)}"
    task_id = download_manager.submit(  # noqa: F821
        f"{FC2_BASE}/", [], {}, "FC2 批量下载", task_album_id,
    )
    _fc2_batch_progress(f"正在解析 {total} 个条目...", 0, total)

    # 并发解析（信号量 3；占位式任务已建，进度事件驱动 UI）——
    # 串行 1.2s 节流下一个 92 个视频要近 2 分钟，用户等待过久
    sem = asyncio.Semaphore(3)
    progress_lock = asyncio.Lock()
    done_count = 0

    async def _resolve_one(idx: int, vid: str):
        nonlocal done_count
        async with sem:
            try:
                page = await asyncio.to_thread(_fc2_get, f"/a/content/{vid}", referer=FC2_BASE + "/")
                if page is None or page.status_code != 200:
                    raise PermissionError(f"内容页失败（HTTP {page.status_code if page else '无响应'}）")
                meta = _fc2_parse_detail_page(page.text, vid)
                urls = _fc2_play_urls(vid, base_referer(vid))
                quality, url = _fc2_best(urls)
                if not url:
                    raise PermissionError("无可用播放源")
                title = sanitize_directory_name(meta["album_name"]) or f"fc2_{vid}"  # noqa: F821
                entry = {
                    "filename": f"{title}.mp4",
                    "size": None,
                    "item_page": meta["album_url"],
                    "status": "ok",
                    "thumbnail": meta.get("thumbnail") or "",
                    "media_url": url,
                    "hls_url": url if urls.get("__type") == "2" else "",
                    "site": "fc2",
                    "video_id": vid,
                    "post_title": meta["album_name"],
                    "post_date": "",
                    "artist": meta.get("author") or "FC2",
                    "media_type": "video",
                    "fc2_quality": quality,
                }
                # 增量并入占位任务（下载面板实时增长）
                download_manager.submit(  # noqa: F821
                    f"{FC2_BASE}/", [entry], {}, "FC2 批量下载", task_album_id,
                )
                # 2026-09-13 修复：结果必须入 out——此前 out 恒空 → if out 恒 False
                # → start 永不执行 → 任务永远 pending（"批量任务没有开始下载"真凶）
                out.append(entry)
                return entry
            except Exception as exc:
                failed.append(f"{vid}（{exc}）")
                logging.warning("FC2 批量解析失败 %s: %s", vid, exc)
                return None
            finally:
                async with progress_lock:
                    done_count += 1
                    _fc2_batch_progress(f"解析进度 {done_count}/{total}", done_count, total)

    await asyncio.gather(*(_resolve_one(i, vid) for i, vid in enumerate(ids)))

    if out:
        download_manager.start(task_id)  # noqa: F821 —— 文件已增量并入占位任务，这里直接启动
    summary = f"批量下载已提交：{len(out)} 个文件 / {total} 个条目"
    if failed:
        summary += f"；失败：{'、'.join(failed[:6])}"
    _fc2_batch_progress(summary, total, total, failed)


async def fc2_following() -> None:
    """我的关注：登录态从头部取我的账号 id → /a/account/{id}/following 列表。"""
    _gs_emit({"view": "following", "items": [], "loading": True})
    try:
        r = await asyncio.to_thread(_fc2_get, "/a/", referer=FC2_BASE + "/")
        if r is None or r.status_code != 200:
            raise PermissionError("FC2 页面获取失败")
        html = r.text
        # 登录判定对齐 check_login：userName 存在即已登录（头部登录块与用户块可能共存，不能只看登录块）
        mu = re.search(r'c-header_main_userName">\s*([^<]{1,40}?)\s*<', html)
        my_id = ""
        if mu:
            m = re.search(r'/a/account/(\d+)', html[max(0, mu.start() - 1500):mu.end() + 1500])
            my_id = m.group(1) if m else ""
        if not mu or not my_id:
            _gs_emit({"view": "following", "items": [], "loading": False,
                      "error": "请先在左侧登录 FC2 后再查看我的关注（登录过期的话重新登录一次即可）"})
            return
        fr = await asyncio.to_thread(_fc2_get, f"/a/account/{my_id}/following",
                                     referer=f"{FC2_BASE}/a/account/{my_id}")
        if fr is None or fr.status_code != 200:
            raise PermissionError(f"关注列表获取失败（HTTP {fr.status_code if fr else '无响应'}）")
        fhtml = fr.text
        items: list[dict] = []
        seen: set[str] = set()
        # c-card-user 结构：thumb(background-image 头像) + c-card-user_name 锚文本(真实名字)
        for m in re.finditer(r'c-card-user_name">\s*<a[^>]*href="[^"]*/a/account/(\d+)"[^>]*>\s*([^<]{1,40}?)\s*<', fhtml):
            aid, name = m.group(1), m.group(2).strip()
            if aid == my_id or aid in seen or not name:
                continue
            seen.add(aid)
            block = fhtml[m.start():m.end() + 900]
            mi = re.search(r'background-image:\s*url\(([^)]+)\)', block)
            items.append({
                "user_id": aid,
                "name": name,
                "avatar": _fc2_abs_url(mi.group(1).strip()) if mi else "",
            })
            if len(items) >= 60:
                break
        # 兜底：旧解析（无名字卡片时）
        if not items:
            for m in re.finditer(r'href="[^"]*/a/account/(\d+)"', fhtml):
                aid = m.group(1)
                if aid == my_id or aid in seen:
                    continue
                seen.add(aid)
                items.append({"user_id": aid, "name": f"账号 {aid}", "avatar": ""})
                if len(items) >= 60:
                    break
        _gs_emit({"view": "following", "items": items, "loading": False,
                  "label": f"我的关注（{len(items)}）"})
    except Exception as exc:
        _gs_emit({"view": "following", "items": [], "loading": False,
                  "error": f"获取失败: {exc}"})


async def fc2_user_relations(user_id: str, kind: str = "followers") -> None:
    """用户关系列表：following=关注 / followers=粉丝 / friends=好友（c-card-user 卡片）。"""
    subs = {"following": "following", "followers": "followers", "friends": "friends"}
    labels = {"following": "关注", "followers": "粉丝", "friends": "好友"}
    sub = subs.get(kind, "followers")
    label = labels.get(kind, kind)
    _gs_emit({"view": "relations", "items": [], "loading": True,
              "label": f"{label}列表", "kind": kind})
    try:
        r = await asyncio.to_thread(_fc2_fetch_page, f"/a/account/{user_id}/{sub}",
                                    referer=f"{FC2_BASE}/a/account/{user_id}")
        if r is None or r.status_code != 200:
            raise PermissionError(f"获取失败（HTTP {r.status_code if r else '无响应'}）")
        if _fc2_login_wall(r.text):
            raise PermissionError("NEED_LOGIN: 需要登录 FC2（请在左侧登录后重试）")
        fhtml = r.text
        items: list[dict] = []
        seen: set[str] = set()
        for m in re.finditer(r'c-card-user_name">\s*<a[^>]*href="[^"]*/a/account/(\d+)"[^>]*>\s*([^<]{1,40}?)\s*<', fhtml):
            aid, name = m.group(1), m.group(2).strip()
            if aid in seen or not name:
                continue
            seen.add(aid)
            block = fhtml[m.start():m.end() + 900]
            mi = re.search(r'background-image:\s*url\(([^)]+)\)', block)
            items.append({"user_id": aid, "name": name,
                          "avatar": _fc2_abs_url(mi.group(1).strip()) if mi else ""})
            if len(items) >= 100:
                break
        _gs_emit({"view": "relations", "items": items, "loading": False,
                  "label": f"{label}列表（{len(items)}）"})
    except Exception as exc:
        _gs_emit({"view": "relations", "items": [], "loading": False,
                  "error": f"获取失败: {exc}"})


async def _cmd_play_url(command: dict) -> None:
    """播放/下载前的直链解析：{item_id} → gs_state {view:'play', url, quality}。"""
    vid = str(command.get("item_id") or "")
    try:
        info = fc2_download_info(vid)
        _gs_emit({"view": "play", "item_id": vid, "url": info["url"],
                  "quality": info["quality"], "media_type": "video",
                  "error": "" if info["type"] == "1" else "HLS 流（type 2）"})
    except Exception as exc:
        _gs_emit({"view": "play", "item_id": vid, "url": "", "error": str(exc)})


SITE_COMMANDS = {
    "fc2_home": _cmd_home,
    "fc2_search": _cmd_search,
    "fc2_categories": _cmd_categories,
    "fc2_list": _cmd_list,
    "fc2_load_more": _cmd_load_more,
    "fc2_open_detail": _cmd_open_detail,
    "fc2_detail": _cmd_detail,
    "fc2_user": _cmd_user,
    "fc2_user_relations": lambda command: fc2_user_relations(
        str(command.get("user_id") or ""), str(command.get("kind") or "followers")),
    "fc2_favorite": _cmd_favorite,
    "fc2_download_files": _cmd_download_files,
    "fc2_following": lambda command: fc2_following(),
    "fc2_batch_download": _cmd_batch_download,
    "fc2_play_url": _cmd_play_url,
}
