"""Check if Meta Careers has an API or SSR data."""
import asyncio
import sys
import re
import json

async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        # Try the main page
        r = await s.get("https://www.metacareers.com/jobs", timeout=15)
        print(f"Main page: {r.status_code} len={len(r.text)}")
        
        # Check for GraphQL data in HTML
        if "graphql" in r.text.lower():
            print("Found graphql reference")
        if "job_search" in r.text:
            print("Found job_search reference")
        
        # Look for __NEXT_DATA__ or similar SSR payloads
        for pattern_name, pattern in [
            ("__NEXT_DATA__", r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'),
            ("window.__data", r'window\.__data\s*=\s*(\{.*?\});'),
            ("__RELAY_STORE__", r'__RELAY_STORE__.*?(\{.*?\})</script>'),
        ]:
            match = re.search(pattern, r.text, re.DOTALL)
            if match:
                print(f"Found {pattern_name}: {len(match.group(1))} chars")

        # Try Meta's GraphQL API directly
        graphql_url = "https://www.metacareers.com/graphql"
        payload = {
            "variables": {
                "search_input": {
                    "q": "",
                    "divisions": [],
                    "offices": [],
                    "roles": [],
                    "leadership_levels": [],
                    "saved_jobs": [],
                    "saved_searches": [],
                    "sub_teams": [],
                    "teams": [],
                    "is_leadership": False,
                    "is_remote_only": False,
                    "sort_by_new": False,
                    "page": 1,
                    "results_per_page": 20,
                }
            },
            "doc_id": None,
        }
        # Try known doc_ids
        for doc_id in ["4524890100905506", "3753764674707649", None]:
            payload["doc_id"] = doc_id
            r2 = await s.post(
                graphql_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            print(f"GraphQL (doc_id={doc_id}): {r2.status_code} len={len(r2.text)}")
            if r2.status_code == 200:
                try:
                    data = r2.json()
                    print(f"  keys: {list(data.keys())[:5]}")
                    if "data" in data:
                        print(f"  data keys: {list(data['data'].keys())[:5]}")
                except Exception:
                    print(f"  body[:200]: {r2.text[:200]}")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
