"""Deep search for Meta job listings in SSR HTML."""
import asyncio
import sys
import re
import json

async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        r = await s.get("https://www.metacareers.com/jobs", timeout=15)
        text = r.text

        # Script 34 has job_search data (93K chars). Find it and analyze.
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL)
        for i, script in enumerate(scripts):
            if "job_search" in script and len(script) > 50000:
                print(f"Script {i}: {len(script)} chars")
                
                # Look for JSON data embedded in the script
                # Meta uses require/define modules — look for preloaded data
                # Search for arrays of job objects
                job_data = re.findall(r'"title":"([^"]+)".*?"id":"(\d+)"', script[:20000])
                if job_data:
                    print(f"Found {len(job_data)} title/id pairs")
                    for title, jid in job_data[:5]:
                        print(f"  {title} (id={jid})")
                
                # Look for structured result arrays
                results = re.findall(r'"results":\[(\{.*?\}(?:,\{.*?\})*)\]', script[:100000])
                if results:
                    print(f"\nResults arrays found: {len(results)}")
                    for ri, r_str in enumerate(results[:2]):
                        print(f"  [{ri}]: {r_str[:300]}")
                
                # Look for job_search query result
                jsr = re.findall(r'"job_search[^"]*":\{([^}]{50,500})\}', script[:100000])
                if jsr:
                    print(f"\njob_search results: {len(jsr)}")
                    for ji, j_str in enumerate(jsr[:3]):
                        print(f"  [{ji}]: {j_str[:300]}")
                        
                # Show a sample of the script around "job_search"
                idx = script.find("job_search")
                sample = script[max(0,idx-100):idx+500]
                print(f"\nContext around job_search:\n{sample[:600]}")
                break

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
