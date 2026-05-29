"""
Worker entrypoint — now routes directly to the standalone worker
to bypass Redis and prevent Upstash requests quota issues.
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.worker.standalone_worker import main as standalone_main


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(standalone_main())


if __name__ == "__main__":
    main()
