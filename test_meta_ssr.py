"""Check Meta Careers SSR data in HTML."""
import asyncio
import sys
import re
import json

async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        r = await s.get("https://www.metacareers.com/jobs", timeout=15)
        text = r.text

        # Search for job_search data in scripts
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL)
        print(f"Script tags: {len(scripts)}")
        
        for i, script in enumerate(scripts):
            if "job_search" in script or "jobSearch" in script:
                print(f"\n  Script {i} has job_search ({len(script)} chars)")
                # Find JSON-like structures
                json_matches = re.findall(r'(\{"[^"]*job[^"]*":.*?\})\s*[;,]', script[:5000])
                if json_matches:
                    print(f"    JSON-like: {json_matches[0][:200]}")
                # Show context around job_search
                idx = script.find("job_search")
                if idx >= 0:
                    print(f"    Context: ...{script[max(0,idx-50):idx+200]}...")

        # Also search for relay store
        relay = re.findall(r'__relay_store\s*=\s*(.*?);', text, re.DOTALL | re.IGNORECASE)
        if relay:
            print(f"\nRelay store found: {len(relay[0])} chars")

        # Search for any structured data with jobs
        json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.DOTALL)
        for j in json_ld:
            print(f"\nJSON-LD: {j[:300]}")

        # Check for data embedded in div elements
        data_attrs = re.findall(r'data-(?:jobs|results|content)="([^"]*)"', text[:50000])
        if data_attrs:
            print(f"\nData attrs: {len(data_attrs)}")

        # Look for __RELAY_INTERNAL__
        for needle in ["__RELAY_INTERNAL__", "require_cond", "define(", "__d("]:
            if needle in text:
                idx = text.find(needle)
                print(f"\nFound '{needle}' at index {idx}")
                print(f"  Context: ...{text[max(0,idx-20):idx+100]}...")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
