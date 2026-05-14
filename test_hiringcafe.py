"""Test HiringCafe aggregator fetch."""

import asyncio

from scripts.ingestion.aggregator_adapters import HiringCafeAdapter


async def main():
    import aiohttp
    async with aiohttp.ClientSession() as session:
        jobs = await HiringCafeAdapter.fetch(session)
        print(f"Fetched {len(jobs)} jobs from HiringCafe.")
        for j in jobs[:5]:
            print(f"  {j.title} at {j.company}")

if __name__ == "__main__":
    if __import__("sys").platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
