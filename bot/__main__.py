from __future__ import annotations

import asyncio
import sys

sys.stderr.write("starting bot...\n")
sys.stderr.flush()

from bot.main import main

try:
    asyncio.run(main())
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
