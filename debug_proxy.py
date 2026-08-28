# -*- coding: utf-8 -*-
"""临时调试：媒体代理启动 + 基本转发测试（测完即删）。"""
import sys, asyncio
sys.path.insert(0, ".")
import gui_bridge as gb
import aiohttp


async def main():
    port = await gb.start_media_proxy()
    print("代理端口:", port)
    async with aiohttp.ClientSession() as s:
        # 1. 非白名单域名应 403
        async with s.get(f"http://127.0.0.1:{port}/media?url=http://example.com/x.jpg") as r:
            print("非白名单状态码:", r.status, "(期望 403)")
        # 2. 无效协议应 403
        async with s.get(f"http://127.0.0.1:{port}/media?url=ftp://a/b") as r:
            print("无效协议状态码:", r.status, "(期望 403)")
        # 3. 真实媒体（Iwara 公开缩略图域名）
        url = "https://files.iwara.tv/image/thumbnail/6861a2a4-4a1f-49a6-9ca8-4d16d6a4b9af/thumbnail-00.jpg"
        try:
            async with s.get(f"http://127.0.0.1:{port}/media?url={url}", timeout=aiohttp.ClientTimeout(total=30)) as r:
                body = await r.read()
                print("Iwara 图片状态码:", r.status, "Content-Type:", r.headers.get("Content-Type"), "字节:", len(body))
                print("图片头:", body[:8].hex())
        except Exception as e:
            print("Iwara 图片测试异常:", e)
        # 4. Range 请求
        try:
            async with s.get(
                f"http://127.0.0.1:{port}/media?url={url}",
                headers={"Range": "bytes=0-99"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                body = await r.read()
                print("Range 状态码:", r.status, "Content-Range:", r.headers.get("Content-Range"), "字节:", len(body))
        except Exception as e:
            print("Range 测试异常:", e)


asyncio.run(main())
