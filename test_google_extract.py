"""Extract Google Careers data with proper bounds."""
import asyncio
import sys
import re
import json

async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        r = await s.get(
            "https://www.google.com/about/careers/applications/jobs/results/",
            timeout=15,
        )

        # Find the ds:1 callback
        pattern = r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(\[.*?\]),\s*sideChannel:"
        match = re.search(pattern, r.text, re.DOTALL)
        if not match:
            # Try alternative: data ends before the closing });
            pattern2 = r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(\[.+?)\}\);"
            match = re.search(pattern2, r.text, re.DOTALL)
            if match:
                raw = match.group(1)
                # Strip trailing sideChannel if present
                sc_idx = raw.rfind(", sideChannel:")
                if sc_idx > 0:
                    raw = raw[:sc_idx]
            else:
                print("No match")
                return
        else:
            raw = match.group(1)

        print(f"Data length: {len(raw)}")
        
        data = json.loads(raw)
        entries = data[0] if isinstance(data, list) and isinstance(data[0], list) else data
        print(f"Total entries: {len(entries)}")

        for i, e in enumerate(entries[:5]):
            if isinstance(e, list) and len(e) > 2:
                title = e[1] if len(e) > 1 else "?"
                url = e[2] if len(e) > 2 else "?"
                company = e[7] if len(e) > 7 else "Google"
                locs = e[9] if len(e) > 9 else []
                print(f"  [{i}] {title}")
                print(f"       company={company}")
                print(f"       locations={locs}")

        print(f"\nTotal job entries extracted: {len([e for e in entries if isinstance(e, list) and len(e) > 2])}")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
