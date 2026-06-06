"""Test Google Careers pagination via HTTP."""

import asyncio
import json
import re
import sys


async def extract_page(s, page_num):
    """Fetch a page of Google jobs results."""
    # Google uses q= and page= params
    url = f"https://www.google.com/about/careers/applications/jobs/results/?page={page_num}"
    r = await s.get(url, timeout=15)
    if r.status_code != 200:
        return None, 0

    pattern = r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(\[.+?),\s*sideChannel:"
    match = re.search(pattern, r.text, re.DOTALL)
    if not match:
        return None, 0

    raw = match.group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, 0

    entries = data[0] if isinstance(data, list) and isinstance(data[0], list) else data

    # Also extract total count from ds:1 — it's usually at the end of the data
    total = 0
    if isinstance(data, list) and len(data) > 3:
        # data structure: [[entries], null, total_count, page_size]
        for item in data[1:]:
            if isinstance(item, int) and item > 100:
                total = item
                break

    return entries, total


async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        for page in [1, 2, 3]:
            entries, total = await extract_page(s, page)
            if entries:
                titles = [e[1] for e in entries if isinstance(e, list) and len(e) > 1]
                print(f"Page {page}: {len(entries)} entries, total={total}")
                if titles:
                    print(f"  First: {titles[0]}")
                    print(f"  Last:  {titles[-1]}")
            else:
                print(f"Page {page}: no data")


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
