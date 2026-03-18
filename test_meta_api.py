"""Try alternate Meta APIs for job listings."""

import asyncio
import json
import sys


async def test():
    from curl_cffi.requests import AsyncSession

    async with AsyncSession(impersonate="chrome") as s:
        # Try the API that Meta's frontend calls
        # 1. Check if there's a REST API
        apis = [
            ("GET", "https://www.metacareers.com/api/jobs", None),
            ("GET", "https://www.metacareers.com/api/v1/jobs", None),
            ("GET", "https://www.metacareers.com/jobs?format=json", None),
            # 2. Try GraphQL with different approaches
            (
                "POST",
                "https://www.metacareers.com/graphql",
                {
                    "fb_api_caller_class": "RelayModern",
                    "fb_api_req_friendly_name": "CareersJobSearchQuery",
                    "variables": json.dumps(
                        {
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
                        }
                    ),
                    "doc_id": "8870397466333847",  # guess
                },
            ),
            # 3. Try gql query by name
            (
                "POST",
                "https://www.metacareers.com/api/graphql",
                {
                    "query_name": "CareersJobSearchQuery",
                    "query_params": json.dumps(
                        {
                            "search_input": {
                                "q": "",
                                "page": 1,
                                "results_per_page": 20,
                            }
                        }
                    ),
                },
            ),
        ]

        for method, url, body in apis:
            try:
                if method == "GET":
                    r = await s.get(url, timeout=10)
                else:
                    r = await s.post(
                        url,
                        json=body if isinstance(body, dict) else None,
                        data=body if isinstance(body, str) else None,
                        timeout=10,
                    )

                ct = r.headers.get("content-type", "?")
                print(f"{method} {url[:60]:60s} -> {r.status_code} ct={ct[:30]}")
                if r.status_code == 200 and "json" in ct:
                    print(f"  Body[:200]: {r.text[:200]}")
            except Exception as e:
                print(f"{method} {url[:60]:60s} -> ERROR: {e}")


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(test())
