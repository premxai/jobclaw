import asyncio
import aiohttp
from scripts.ingestion.aggregator_adapters import HiringCafeAdapter

async def main():
    async with aiohttp.ClientSession() as session:
        # Just manually hit the endpoint
        payload = {
            "query": "software engineer",
            "location": "United States",
            "limit": 50,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "JobClaw/2.0",
        }
        async with session.post("https://hiring.cafe/api/search", json=payload, headers=headers) as resp:
            print(f"Status: {resp.status}")
            print(f"Body: {await resp.text()}")

if __name__ == "__main__":
    if __import__("sys").platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
