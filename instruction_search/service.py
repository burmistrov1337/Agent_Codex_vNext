from __future__ import annotations

from .models import SearchResult
from .storage import search


class InstructionSearchService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def search(self, platform: str, query: str, limit: int = 3) -> list[SearchResult]:
        return await search(self.db_path, platform=platform, query=query, limit=limit)
