import asyncio
import sys

sys.path.insert(0, '.')
import gui_bridge

events = []
def capture(event):
    events.append(event)
gui_bridge.emit = capture

async def main():
    await gui_bridge.coomer_inspect(
        'https://xxxcoomer.com/post/12186827/209196/onlyfans/freeasianonlyfans', {}
    )
    for e in events:
        print('事件:', e['event'], '|', str(e.get('message', ''))[:80])
        if e['event'] == 'inspect_complete':
            for it in e['items']:
                print('  文件名 repr:', repr(it['filename']))

asyncio.run(main())
