# -*- coding: utf-8 -*-
"""gui_bridge 拆分模块：翻译 API。

2026-09-14 重设：
1. 单条核心 _translate_once：Google 免费端点（3 域名 × 代理/直连链）→ MyMemory 兜底
2. 批量 translate_batch：弃用旧"多 q 单请求"方案（Google 返回段与输入不按序对应，
   曾导致译文错位张冠李戴）→ 改为去重后逐条并发翻译（线程池 4）+ 进程内缓存 +
   进度事件；译文与输入严格按序对位
3. 翻译缓存：cache/translate_cache.json（站点标题高度重复，命中即秒回）

由 gui_bridge.py 按物理顺序拆出，跨段名字由包加载器注入（见 bridge/__init__.py），
勿在本文件内新增对其他子模块的 import。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path

import requests

from . import _state as _state  # noqa: F401  扁平命名空间：注入此前已加载模块的全部名字
_state.apply_prev(globals())

# ============================
# 端点与配置
# ============================
YOUDAO_API_URL = "https://openapi.youdao.com/api"
MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
# Google 翻译免费端点（多域名轮换：googleapis 国内多数网络可直连，translate.google.com 必须代理）。
# 端点以名称枚举，请求函数内使用字面量 URL（SSRF 防护：不拼动态地址）。
GOOGLE_ENDPOINTS = ("googleapis", "translate_google", "clients5")
# 兼容旧引用（单数常量）
GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
YOUDAO_API = "https://openapi.youdao.com/api"

_TRANSLATE_CACHE_FILE = "cache/translate_cache.json"
_TRANSLATE_CACHE_MAX = 3000
_translate_cache: dict = {}
_translate_cache_loaded = False
_translate_gate_lock = threading.Lock()
_translate_gate_last = 0.0


def _translate_proxy_attempts() -> list:
    """翻译请求的代理尝试列表：先走设置的代理，再尝试直连。

    国内网络访问 Google 翻译必须走代理；海外用户代理不通时自动回退直连。
    """
    s = _load_settings()
    proxy = (s.get("translate_proxy") or "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks5://")):
        proxy = "http://" + proxy
    if proxy:
        return [{"http": proxy, "https": proxy}, None]
    return [None]


def _map_lang_code(lang: str) -> str:
    """统一语言代码：zh-CHS / zh-CHT → zh；其他原样返回。"""
    if not lang or lang == "auto":
        return "auto"
    if lang.lower().startswith("zh"):
        return "zh-CN"
    return lang


def _translate_gate(min_interval: float = 0.12) -> None:
    """全局节流（跨线程）：防并发打爆 Google 端点触发限流。"""
    global _translate_gate_last
    with _translate_gate_lock:
        now = time.time()
        wait = _translate_gate_last + min_interval - now
        if wait > 0:
            time.sleep(wait)
        _translate_gate_last = time.time()


def _translate_cache_load() -> None:
    global _translate_cache, _translate_cache_loaded
    if _translate_cache_loaded:
        return
    _translate_cache_loaded = True
    try:
        data = json.loads(Path(_TRANSLATE_CACHE_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _translate_cache = data
    except (OSError, json.JSONDecodeError):
        pass


def _translate_cache_put(key: str, value: str) -> None:
    _translate_cache_load()
    _translate_cache[key] = value
    if len(_translate_cache) > _TRANSLATE_CACHE_MAX:
        items = list(_translate_cache.items())[-_TRANSLATE_CACHE_MAX // 2:]
        _translate_cache.clear()
        _translate_cache.update(dict(items))
    try:
        Path("cache").mkdir(exist_ok=True)
        Path(_TRANSLATE_CACHE_FILE).write_text(
            json.dumps(_translate_cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


def _needs_translation(text: str, tl: str) -> bool:
    """无需翻译的文本：空 / 纯数字符号 / 目标语为中文且已基本是中文。"""
    t = (text or "").strip()
    if not t:
        return False
    if len(t) <= 6 and not re.search(r"[A-Za-z\u3040-\u30ff\uac00-\ud7af]", t):
        return False  # 纯数字/极短符号串
    if tl.startswith("zh"):
        if _KANA_RE.search(t):
            return True  # 含日文假名 → 一定是日文，需要翻译
        han_count = len(re.findall(r"[一-鿿]", t))
        if han_count * 5 >= len(t) * 3:
            return False  # 全汉字且占比高 → 已是中文
    return True


def _google_get(endpoint: str, params: dict, proxies, timeout: int = 8):
    """Google 免费翻译端点 GET（字面量 URL 分发；端点名白名单校验）。"""
    if endpoint == "googleapis":
        return requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params=params, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }, proxies=proxies, timeout=timeout)
    if endpoint == "translate_google":
        return requests.get(
            "https://translate.google.com/translate_a/single",
            params=params, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }, proxies=proxies, timeout=timeout)
    if endpoint == "clients5":
        return requests.get(
            "https://clients5.google.com/translate_a/single",
            params=params, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }, proxies=proxies, timeout=timeout)
    return None


def _mymemory_get(params: dict, timeout: int = 8):
    """MyMemory 免费翻译接口 GET（字面量 URL）。"""
    return requests.get(
        "https://api.mymemory.translated.net/get",
        params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)


def _translate_once(text: str, sl: str, tl: str) -> tuple:
    """单条翻译核心：Google 端点（3 域名 × 代理链）→ MyMemory 兜底。

    返回 (译文, engine)；全部失败抛 RuntimeError（调用方决定如何呈现）。"""
    last_err = ""
    for endpoint in GOOGLE_ENDPOINTS:
        for proxies in _translate_proxy_attempts():
            try:
                # dt=t 必须保留（返回翻译片段）；历史踩坑：dict 重复键让 dt=bd 覆盖 dt=t
                params = {
                    "client": "at",
                    "dt": "t",
                    "sl": sl,
                    "tl": tl,
                    "q": text,
                }
                resp = _google_get(endpoint, params, proxies)
                if resp is None:
                    continue
                data = resp.json()
                # 响应结构：[[["译文","原文",None,None,1],...], null, "检测到的源语言", ...]
                if isinstance(data, list) and data and isinstance(data[0], list):
                    translation = "".join(seg[0] for seg in data[0] if seg and seg[0])
                    if translation:
                        detected = data[2] if len(data) > 2 and data[2] else sl
                        return translation, f"google_free({detected})"
                    last_err = "Google 返回空结果"
                    continue
                last_err = "Google 返回格式异常"
                continue
            except Exception as exc:
                last_err = f"Google 失败：{exc}"
                continue
    # MyMemory 兜底（不支持 auto 源，按 en）
    try:
        src = "en" if sl == "auto" else sl
        resp = _mymemory_get({"q": text[:500], "langpair": f"{src}|{tl}"})
        data = resp.json()
        tr = (data.get("responseData") or {}).get("translatedText") or ""
        if tr and "MYMEMORY WARNING" not in tr:
            return tr, "mymemory"
        last_err = f"{last_err}；MyMemory 未返回结果"
    except Exception as exc:
        last_err = f"{last_err}；MyMemory 失败：{exc}"
    raise RuntimeError(last_err)


def translate_free(text: str, from_lang: str = "auto", to_lang: str = "zh-CN") -> None:
    """手动翻译（左侧翻译面板）：单条，emit 'translate_result'。"""
    text = text or ""
    if not text.strip():
        emit({"event": "translate_result", "ok": False, "error": "请输入要翻译的文本"})
        return
    sl = _map_lang_code(from_lang)
    tl = _map_lang_code(to_lang)
    if sl != "auto" and sl == tl:
        tl = "en" if sl == "zh-CN" else "zh-CN"
    try:
        translation, engine = _translate_once(text, sl, tl)
    except RuntimeError as exc:
        emit({"event": "translate_result", "ok": False, "error": str(exc)})
        return
    emit({
        "event": "translate_result",
        "ok": True,
        "translation": translation,
        "query": text,
        "detected_source": sl,
        "engine": engine,
    })


def translate_batch(texts: list, from_lang: str = "auto", to_lang: str = "zh-CN",
                    batch_id: str = "") -> None:
    """批量翻译（自动翻译搜索结果标题）：去重 + 缓存 + 线程池并发逐条翻译。

    契约：emit 'translate_batch_result'，translations 与 texts 严格按序对位，
    失败条目保留原文；仅当全部待翻条目都失败时 ok=False。
    进度：每完成 5 条 emit 'translate_batch_progress' {done,total,batch_id}。"""
    texts = [str(t or "") for t in (texts or [])]
    if not texts:
        emit({"event": "translate_batch_result", "ok": False, "error": "未提供要翻译的文本",
              "batch_id": batch_id, "translations": []})
        return
    sl = _map_lang_code(from_lang)
    tl = _map_lang_code(to_lang)
    if sl != "auto" and sl == tl:
        tl = "en" if sl == "zh-CN" else "zh-CN"

    _translate_cache_load()
    translations = list(texts)
    cache_hits = 0
    groups: dict = {}   # 文本 → [出现位置]（重复文本只发一次请求，结果回填全部位置）
    for i, t in enumerate(texts):
        if not _needs_translation(t, tl):
            continue
        key = f"{t}|{sl}>{tl}"
        hit = _translate_cache.get(key)
        if hit:
            translations[i] = hit
            cache_hits += 1
            continue
        groups.setdefault(t, []).append(i)
    pending = [(t, idxs) for t, idxs in groups.items()]

    total = len(pending)
    if total == 0:
        emit({"event": "translate_batch_result", "ok": True,
              "translations": translations, "batch_id": batch_id,
              "engine": "cache"})
        logging.info("translate_batch %s: 全部命中缓存", batch_id)
        return

    done_count = 0
    fail_count = 0
    progress_lock = threading.Lock()

    def _worker(item):
        nonlocal done_count, fail_count
        text, idxs = item
        _translate_gate()
        try:
            tr, _engine = _translate_once(text, sl, tl)
            for idx in idxs:
                translations[idx] = tr
            _translate_cache_put(f"{text}|{sl}>{tl}", tr)
        except Exception as exc:
            logging.warning("translate_batch 条目失败: %s (%s)", text[:40], exc)
            fail_count += 1
        finally:
            with progress_lock:
                done_count += 1
                if done_count % 5 == 0 or done_count == total:
                    emit({"event": "translate_batch_progress",
                          "done": done_count, "total": total, "batch_id": batch_id})

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_worker, it) for it in pending]
        for f in as_completed(futures):
            f.result()

    all_failed = fail_count >= total
    result = {"event": "translate_batch_result", "ok": not all_failed,
              "translations": translations, "batch_id": batch_id,
              "engine": "google_free"}
    if all_failed:
        result["error"] = "翻译失败：全部条目均失败（端点不可达或被限流），请检查翻译代理设置"
    emit(result)
    logging.info("translate_batch %s: 待翻 %d 条（失败 %d，缓存命中 %d）",
                 batch_id, total, fail_count, cache_hits)


def translate_youdao(text: str, from_lang: str = "auto", to_lang: str = "zh") -> None:
    """调用有道智云翻译 API（需用户在设置里填 app_id/app_secret）。

    成功 emit 'translate_result' 事件。未配置 key / 网络失败 / 错误码 均回 ok=False。
    """
    text = text or ""
    if not text.strip():
        emit({"event": "translate_result", "ok": False, "error": "请输入要翻译的文本"})
        return
    s = _load_settings()
    app_id = (s.get("youdao_app_id") or "").strip()
    app_secret = (s.get("youdao_app_secret") or "").strip()
    if not app_id or not app_secret:
        emit({
            "event": "translate_result",
            "ok": False,
            "error": "未配置有道 API，请在下方填写应用 ID 和密钥后保存设置",
        })
        return
    import uuid
    salt = uuid.uuid4().hex
    curtime = str(int(time.time()))
    # 签名输入：文本 ≤10 全量；>10 取首3+长度+末3
    input_str = text if len(text) <= 10 else text[:3] + str(len(text)) + text[-3:]
    sign_str = app_id + input_str + salt + curtime + app_secret
    sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest()
    params = {
        "q": text,
        "from": from_lang,
        "to": to_lang,
        "appKey": app_id,
        "salt": salt,
        "sign": sign,
        "signType": "v3",
        "curtime": curtime,
    }
    try:
        resp = requests.post("https://openapi.youdao.com/api", data=params, timeout=20)
        data = resp.json()
    except Exception as exc:
        emit({"event": "translate_result", "ok": False, "error": f"网络请求失败：{exc}"})
        return
    err = str(data.get("errorCode") or "")
    translation = data.get("translation") or []
    if err not in ("", "0") and not translation:
        emit({"event": "translate_result", "ok": False, "error": f"有道返回错误码 {err}"})
        return
    if not translation:
        emit({"event": "translate_result", "ok": False, "error": "未获得翻译结果"})
        return
    emit({
        "event": "translate_result",
        "ok": True,
        "translation": translation[0] if len(translation) == 1 else "；".join(translation),
        "query": data.get("query") or text,
        "raw": data,
    })
