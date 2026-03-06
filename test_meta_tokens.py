"""Extract the real GraphQL doc_id and tokens from Meta Careers page."""
import asyncio
import sys
import re
import json

async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        r = await s.get("https://www.metacareers.com/jobs", timeout=15)
        html = r.text
        print(f"Page size: {len(html)}")
        
        # Extract all doc_id patterns
        doc_ids = re.findall(r'"doc_id"\s*:\s*"(\d+)"', html)
        print(f"\ndoc_ids found: {doc_ids[:20]}")
        
        # Extract DTSGs (CSRF tokens)
        dtsgs = re.findall(r'"DTSGInitialData"\s*,\s*\[\]\s*,\s*\{[^}]*"token"\s*:\s*"([^"]+)"', html)
        print(f"DTSGs: {dtsgs[:5]}")
        
        # Alternative DTSG patterns
        dtsgs2 = re.findall(r'dtsg.*?"token"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
        print(f"DTSG alt: {dtsgs2[:5]}")
        
        # Look for fb_dtsg hidden inputs
        dtsg_input = re.findall(r'name="fb_dtsg"[^>]*value="([^"]*)"', html)
        print(f"fb_dtsg input: {dtsg_input[:5]}")
        
        # LSD token
        lsd = re.findall(r'"LSD"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"', html)
        print(f"LSD: {lsd[:5]}")
        
        # Alternative LSD
        lsd2 = re.findall(r'name="lsd"[^>]*value="([^"]*)"', html)
        print(f"LSD input: {lsd2[:5]}")
        
        # Haste session  
        haste = re.findall(r'"haste_session"\s*:\s*"([^"]+)"', html)
        print(f"haste_session: {haste[:3]}")
        
        # __spin_r, __spin_b, __spin_t
        spin_r = re.findall(r'__spin_r\s*[:=]\s*(\d+)', html)
        spin_b = re.findall(r'__spin_b\s*[:=]\s*"([^"]+)"', html)
        spin_t = re.findall(r'__spin_t\s*[:=]\s*(\d+)', html)
        print(f"spin_r: {spin_r[:3]}, spin_b: {spin_b[:3]}, spin_t: {spin_t[:3]}")
        
        # __comet_req
        comet = re.findall(r'"__comet_req"\s*:\s*"?(\d+)"?', html)
        print(f"__comet_req: {comet[:3]}")
        
        # Search for job data patterns
        # Look for "job_id" or actual jobs embedded
        job_id_matches = re.findall(r'"job_id"\s*:\s*"(\d+)"', html)
        print(f"\njob_id values: {job_id_matches[:10]}")
        
        # Look for any JSON blob with "title" and "location" near each other
        results_pattern = re.findall(r'"results"\s*:\s*\[', html)
        print(f"'results': [ occurrences: {len(results_pattern)}")
        
        # Search for data embedded in __d or preloaded data
        preloaded = re.findall(r'__d\s*=\s*"([^"]{0,200})"', html)
        print(f"__d patterns: {len(preloaded)}")
        
        # Look for require("ServerJS") with data payloads
        serverjs = re.findall(r'ServerJS.*?handle\((\{[^)]{0,500})', html[:50000])
        print(f"ServerJS handle: {len(serverjs)}")
        
        # Check for preloaded queries / relay store
        relay_store = re.findall(r'"__relay_internal__pv__', html)
        print(f"Relay internal PV: {len(relay_store)}")
        
        # Find the actual fetch URL pattern
        fetch_url = re.findall(r'fetch\s*\(\s*["\']([^"\']*job[^"\']*)', html, re.IGNORECASE)
        print(f"fetch URL with job: {fetch_url[:5]}")
        
        # Look for result count or "showing X jobs"
        counts = re.findall(r'(\d+)\s*(?:jobs?|results?|positions?)\s*(?:found|available|matching)', html, re.IGNORECASE)
        print(f"Job counts: {counts[:5]}")
        
        # **NEW**: Look for CareersSearch or similar query names
        query_names = re.findall(r'"(?:CareersSearch|CareersJobSearch|JobSearch|CPJobSearch)[^"]*"', html)
        print(f"\nQuery names: {query_names[:10]}")
        
        # Find __d variable with large data   
        d_var = re.findall(r'window\.__d\s*=\s*', html)
        print(f"window.__d: {d_var}")
        
        # Try to find the actual graphql doc_id for job search
        # Pattern: something like CareersJobSearch...Query
        all_names = re.findall(r'"([A-Z][a-zA-Z]*(?:Job|Career|Search)[a-zA-Z]*(?:Query|Mutation))"', html)
        print(f"\nGraphQL operation names: {all_names[:20]}")
        
        # Now let's try each doc_id with our search params 
        if doc_ids:
            print(f"\n--- Testing {min(len(doc_ids), 5)} doc_ids ---")
            lsd_token = lsd[0] if lsd else lsd2[0] if lsd2 else ""
            
            for did in doc_ids[:5]:
                body = {
                    "lsd": lsd_token,
                    "fb_api_caller_class": "RelayModern",
                    "fb_api_req_friendly_name": "CareersJobSearchRelayQuery",
                    "variables": json.dumps({
                        "search_input": {
                            "q": "",
                            "page": 1,
                            "results_per_page": 10,
                        }
                    }),
                    "doc_id": did,
                }
                try:
                    r2 = await s.post("https://www.metacareers.com/api/graphql/", data=body, timeout=10,
                                      headers={"Content-Type": "application/x-www-form-urlencoded"})
                    ct = r2.headers.get("content-type", "?")
                    print(f"  doc_id={did} -> {r2.status_code} ct={ct[:30]} body[:100]={r2.text[:100]}")
                except Exception as e:
                    print(f"  doc_id={did} -> ERROR: {e}")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
