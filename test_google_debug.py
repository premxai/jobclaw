"""Debug Google SSR data extraction."""
import asyncio
import sys
import re

async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        r = await s.get(
            "https://www.google.com/about/careers/applications/jobs/results/",
            timeout=15,
        )
        # Find all AF_initDataCallback calls
        callbacks = re.findall(r"AF_initDataCallback\(\{(.*?)\}\);", r.text, re.DOTALL)
        print(f"AF_initDataCallback calls: {len(callbacks)}")
        for i, cb in enumerate(callbacks):
            key_match = re.search(r"key:\s*'([^']+)'", cb)
            key = key_match.group(1) if key_match else "?"
            print(f"  [{i}] key={key} len={len(cb)}")
            
            if key == "ds:1":
                # Find the data part
                data_match = re.search(r"data:(\[.+)", cb, re.DOTALL)
                if data_match:
                    raw = data_match.group(1)
                    print(f"    data[0:300]: {raw[:300]}")
                    # Try JSON parse
                    import json
                    try:
                        data = json.loads(raw)
                        entries = data[0] if isinstance(data, list) and isinstance(data[0], list) else data
                        if isinstance(entries, list):
                            print(f"    entries: {len(entries)}")
                            if entries and isinstance(entries[0], list):
                                print(f"    first entry: id={entries[0][0]} title={entries[0][1]}")
                    except json.JSONDecodeError as e:
                        print(f"    JSON fail: {e}")
                        print(f"    raw[-50:]: {raw[-50:]}")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
