# -*- coding: utf-8 -*-
"""临时测试：EX 我的收藏 + 画廊详情。用完即删。"""
import asyncio
import json

import gui_bridge

gui_bridge.exhentai_set_proxy("http://127.0.0.1:10809")
events = []
gui_bridge.emit = events.append


async def main():
    # 1. 我的收藏
    await gui_bridge.exhentai_favorites(1)
    for e in events:
        if e.get("event") == "search_result":
            print("===== favorites =====")
            print("meta:", json.dumps({k: e.get(k) for k in ("page", "total_pages", "total_results", "has_more")}, ensure_ascii=False))
            print("items:", len(e["items"]))
            for it in e["items"][:3]:
                print("  ", (it.get("album_name") or "")[:50], "|", it.get("album_url"))
        elif e.get("event") == "search_error":
            print("search_error:", e)
    events.clear()

    # 2. 画廊详情（取收藏第一个；无收藏则搜索取第一个）
    url = None
    for e in events:
        pass
    await gui_bridge.exhentai_favorites(1)
    for e in events:
        if e.get("event") == "search_result" and e["items"]:
            url = e["items"][0]["album_url"]
    events.clear()
    if not url:
        await gui_bridge.exhentai_search("furry", 1)
        for e in events:
            if e.get("event") == "search_result" and e["items"]:
                url = e["items"][0]["album_url"]
    events.clear()
    print("detail url:", url)

    await gui_bridge.exhentai_gallery_info(url)
    for e in events:
        if e.get("event") == "ex_gallery_info":
            print("===== gallery info =====")
            for k in ("title", "title_jp", "uploader", "posted", "parent", "visible",
                      "language", "file_size", "length", "favorited", "rating", "rating_count"):
                print(f"  {k}: {e.get(k)}")
            print("  tags:", json.dumps(e.get("tags", {}), ensure_ascii=False)[:900])
        else:
            print(e)
    events.clear()

    # 3. 种子保存（先取种子列表）
    await gui_bridge.exhentai_get_torrents(url)
    torrents = []
    for e in events:
        if e.get("event") == "exhentai_torrents":
            torrents = e.get("torrents", [])
            print("===== torrents =====", len(torrents))
            for t in torrents[:3]:
                print("  ", t["name"][:40], t["size"], "seeds:", t["seeds"])
        elif e.get("event") == "exhentai_torrents_error":
            print("torrents_error:", e)
    events.clear()
    if torrents:
        await gui_bridge.exhentai_save_torrent(torrents[0]["url"], torrents[0]["name"])
        for e in events:
            print("save:", json.dumps(e, ensure_ascii=False)[:200])


asyncio.run(main())
