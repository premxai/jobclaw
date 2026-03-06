"""Test Google Careers without Playwright - check if SSR data is in HTML."""
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
        print(f"Status: {r.status_code}")
        print(f"URL: {r.url}")
        print(f"Content-Type: {r.headers.get('content-type', '?')}")
        print(f"Body length: {len(r.text)}")

        # Check for AF_initDataChunkQueue in the HTML
        if "AF_initDataChunkQueue" in r.text:
            print("FOUND AF_initDataChunkQueue in HTML!")
            # Extract the data
            matches = re.findall(r'AF_initDataChunkQueue\.push\((\[.*?\])\);', r.text, re.DOTALL)
            print(f"  Chunks found: {len(matches)}")
            for i, m in enumerate(matches[:3]):
                print(f"  Chunk {i}: {m[:200]}...")
        else:
            print("AF_initDataChunkQueue NOT found in HTML")

        # Check for any JSON-like data patterns
        if "ds:1" in r.text:
            print("Found ds:1 reference")
        if "jobResults" in r.text.lower():
            print("Found jobResults reference")

        # Look for script tags with data
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
        print(f"Total script tags: {len(scripts)}")
        for i, s_content in enumerate(scripts):
            if "job" in s_content.lower()[:200]:
                print(f"  Script {i} might have jobs data (len={len(s_content)}): {s_content[:150]}...")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
