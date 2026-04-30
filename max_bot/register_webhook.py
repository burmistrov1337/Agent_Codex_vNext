from __future__ import annotations

import asyncio

from .webhook import register_subscription


def main() -> None:
    asyncio.run(register_subscription())


if __name__ == "__main__":
    main()
