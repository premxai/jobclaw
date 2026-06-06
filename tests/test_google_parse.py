"""Extract Google Careers job data from HTML SSR (no Playwright)."""

import asyncio
import json
import re
import sys


async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        r = await s.get(
            "https://www.google.com/about/careers/applications/jobs/results/",
            timeout=15,
        )
        if r.status_code != 200:
            print(f"Failed: {r.status_code}")
            return

        # Extract AF_initDataCallback data
        # Format: AF_initDataCallback({key: 'ds:1', hash: '2', data:[[...]]});
        pattern = r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(\[.*?\])\}\);"
        match = re.search(pattern, r.text, re.DOTALL)
        if not match:
            print("No ds:1 data found")
            return

        raw = match.group(1)
        print(f"Raw data length: {len(raw)}")

        # The data is JavaScript, not JSON — values use null, true, false which
        # are the same in JSON. Try parsing directly:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"JSON parse failed: {e}")
            # Try with some fixups
            raw_fixed = raw.replace("'", '"')
            try:
                data = json.loads(raw_fixed)
            except json.JSONDecodeError as e2:
                print(f"Still failed: {e2}")
                print(f"Raw sample: {raw[:500]}")
                return

        print(f"Data type: {type(data).__name__}")
        if isinstance(data, list) and data:
            entries = data[0] if isinstance(data[0], list) else data
            print(f"Entries: {len(entries)}")
            for i, entry in enumerate(entries[:3]):
                if isinstance(entry, list) and len(entry) > 2:
                    print(f"  [{i}] id={entry[0]} title={entry[1]}")
                    print(f"       url={entry[2]}")
                    if len(entry) > 9:
                        print(f"       locations={entry[9]}")


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
