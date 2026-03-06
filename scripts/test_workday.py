import asyncio
from curl_cffi.requests import AsyncSession
import json
import re

async def test_workday():
    url = "https://amazon.wd5.myworkdayjobs.com/wday/cxs/amazon/AmazonNew/jobs"
    home_url = "https://amazon.wd5.myworkdayjobs.com/AmazonNew"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://amazon.wd5.myworkdayjobs.com",
    }
    
    payload = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": ""
    }
    
    async with AsyncSession(impersonate="chrome120") as session:
        print("1. Fetching home page to establish session & get CSRF token...")
        resp_home = await session.get(home_url, headers={"User-Agent": headers["User-Agent"]})
        print(f"Home page status: {resp_home.status_code}")
        
        # Look for CSRF token in cookies
        cookies = session.cookies.get_dict()
        csrf_token = None
        
        # Look for CSRF token in the HTML (often embedded in a script tag)
        html = resp_home.text
        match = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', html)
        if match:
            csrf_token = match.group(1)
            print(f"Found CSRF embedded in HTML: {csrf_token[:10]}...")
            headers["X-CALYPSO-CSRF-TOKEN"] = csrf_token
            
        print("\nCookies obtained:")
        for k, v in cookies.items():
            print(f"  {k}: {v[:10]}...")
            if k == "PLAY_SESSION":
                headers["X-CALYPSO-CSRF-TOKEN"] = v.split("-")[0] # Sometimes it's the first part of the session
            
        print("\n2. Making POST request...")
        resp = await session.post(url, headers=headers, json=payload)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            print("SUCCESS!")
            print(json.dumps(resp.json(), indent=2)[:200] + "...")
        else:
            print(f"Failed with {resp.status_code}")
            print(resp.text[:200])

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_workday())
