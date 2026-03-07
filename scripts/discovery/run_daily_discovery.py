"""
Daily Company Discovery Script

Runs ATS company discovery using Brave Search API to find new companies
and add them to the registry. Designed to run once daily.
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log
from scripts.discovery import run_discovery


async def main():
    """Run discovery for all ATS platforms."""
    _log(">>> Starting Daily Company Discovery")
    
    # Run discovery for all supported platforms
    platforms = ["greenhouse", "lever", "workable", "ashby", "rippling"]
    
    result = await run_discovery(platforms=platforms)
    
    total = result.get("discovered", 0)
    by_ats = result.get("by_ats", {})
    
    if total > 0:
        _log(f">>> Discovery complete: {total} new companies found")
        for ats, count in by_ats.items():
            _log(f"    {ats}: +{count}")
    else:
        _log(">>> Discovery complete: No new companies found")
    
    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result.get("discovered", 0) >= 0 else 1)
