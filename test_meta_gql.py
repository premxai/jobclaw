"""Try Meta GraphQL with LSD token and CPJobSearchQuery."""

import asyncio
import json
import re
import sys


async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        # 1. Get the page and extract tokens
        r = await s.get("https://www.metacareers.com/jobs", timeout=15)
        html = r.text

        # Extract LSD token
        lsd_match = re.search(r'"LSD"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"', html)
        lsd = lsd_match.group(1) if lsd_match else ""
        print(f"LSD token: {lsd}")

        # Extract fb_dtsg
        dtsg_match = re.search(r'"DTSGInitData"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"', html)
        if not dtsg_match:
            dtsg_match = re.search(r'"token"\s*:\s*"([^"]+)"[^}]*"__m"\s*:\s*"DTSGInitialData"', html)
        if not dtsg_match:
            dtsg_match = re.search(r'DTSG.*?"token"\s*:\s*"([^"]{10,})"', html)
        dtsg = dtsg_match.group(1) if dtsg_match else ""
        print(f"DTSG token: {dtsg[:30]}...")

        # Extract __rev, __a
        rev_match = re.search(r'"server_revision"\s*:\s*(\d+)', html)
        rev = rev_match.group(1) if rev_match else ""
        print(f"server_revision: {rev}")

        # Extract __user
        user_match = re.search(r'"USER_ID"\s*:\s*"(\d+)"', html)
        user = user_match.group(1) if user_match else "0"
        print(f"USER_ID: {user}")

        # Try with cookies from initial request
        cookies = dict(r.cookies)
        print(f"Cookies: {list(cookies.keys())}")

        # Attempt 1: form-encoded with just LSD + query name
        variables = {
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
                "results_per_page": 10,
            }
        }

        form_bodies = [
            # Attempt 1: minimal
            {
                "lsd": lsd,
                "fb_api_caller_class": "RelayModern",
                "fb_api_req_friendly_name": "CPJobSearchQuery",
                "variables": json.dumps(variables),
            },
            # Attempt 2: with dtsg
            {
                "lsd": lsd,
                "fb_dtsg": dtsg,
                "fb_api_caller_class": "RelayModern",
                "fb_api_req_friendly_name": "CPJobSearchQuery",
                "variables": json.dumps(variables),
                "__a": "1",
                "__user": user,
            },
            # Attempt 3: with server_revision
            {
                "lsd": lsd,
                "fb_dtsg": dtsg,
                "fb_api_caller_class": "RelayModern",
                "fb_api_req_friendly_name": "CPJobSearchQuery",
                "variables": json.dumps(variables),
                "__a": "1",
                "__user": user,
                "__rev": rev,
            },
        ]

        for i, body in enumerate(form_bodies):
            print(f"\n--- Attempt {i + 1} ---")
            try:
                r2 = await s.post(
                    "https://www.metacareers.com/api/graphql/",
                    data=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-FB-Friendly-Name": "CPJobSearchQuery",
                        "X-FB-LSD": lsd,
                    },
                    timeout=15,
                )
                ct = r2.headers.get("content-type", "?")
                text = r2.text
                print(f"  Status: {r2.status_code}, CT: {ct}")
                print(f"  Body[:300]: {text[:300]}")

                # Check if response starts with "for (;;);" which is Meta's JSON prefix
                if text.startswith("for (;;);"):
                    clean = text[len("for (;;);") :]
                    try:
                        data = json.loads(clean)
                        print(f"  JSON parsed! Keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                        if isinstance(data, dict) and "data" in data:
                            print(f"  data keys: {list(data['data'].keys())}")
                    except json.JSONDecodeError:
                        print("  JSON parse failed after stripping prefix")
            except Exception as e:
                print(f"  ERROR: {e}")


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
