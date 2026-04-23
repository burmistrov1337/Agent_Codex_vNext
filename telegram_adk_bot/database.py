from __future__ import annotations

from pathlib import Path
from time import time

import aiosqlite


USER_MODE_IDLE = "idle"
USER_MODE_AWAITING_INSTRUCTION_QUERY = "awaiting_instruction_query"
ALLOWED_USER_MODES = {
    USER_MODE_IDLE,
    USER_MODE_AWAITING_INSTRUCTION_QUERY,
}


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS user_state (
                  user_id INTEGER NOT NULL,
                  required_chat TEXT NOT NULL,
                  subscribed INTEGER NOT NULL DEFAULT 0,
                  mode TEXT NOT NULL DEFAULT 'idle',
                  updated_at_ts INTEGER NOT NULL,
                  PRIMARY KEY (user_id, required_chat)
                );
                CREATE TABLE IF NOT EXISTS user_welcome_state (
                  user_id INTEGER PRIMARY KEY,
                  last_welcome_ts INTEGER NOT NULL
                );
                """
            )
            await self._ensure_user_state_columns(db)
            await db.commit()

    async def _ensure_user_state_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(user_state)") as cur:
            columns = {str(row[1]) for row in await cur.fetchall()}
        if "mode" not in columns:
            await db.execute(
                "ALTER TABLE user_state ADD COLUMN mode TEXT NOT NULL DEFAULT 'idle'"
            )

    async def should_send_welcome(self, user_id: int, dedupe_seconds: int = 6) -> bool:
        now_ts = int(time())
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT last_welcome_ts FROM user_welcome_state WHERE user_id=?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
            if row and (now_ts - int(row[0])) < dedupe_seconds:
                return False
            await db.execute(
                """
                INSERT INTO user_welcome_state(user_id, last_welcome_ts)
                VALUES(?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  last_welcome_ts=excluded.last_welcome_ts
                """,
                (user_id, now_ts),
            )
            await db.commit()
            return True

    async def set_subscribed(self, user_id: int, required_chat: str, subscribed: bool) -> None:
        now_ts = int(time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_state(user_id, required_chat, subscribed, mode, updated_at_ts)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(user_id, required_chat) DO UPDATE SET
                  subscribed=excluded.subscribed,
                  updated_at_ts=excluded.updated_at_ts
                """,
                (user_id, required_chat, 1 if subscribed else 0, USER_MODE_IDLE, now_ts),
            )
            await db.commit()

    async def get_subscribed(self, user_id: int, required_chat: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT subscribed FROM user_state WHERE user_id=? AND required_chat=?",
                (user_id, required_chat),
            ) as cur:
                row = await cur.fetchone()
                return bool(row[0]) if row else False

    async def get_user_mode(self, user_id: int, required_chat: str) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT mode FROM user_state WHERE user_id=? AND required_chat=?",
                (user_id, required_chat),
            ) as cur:
                row = await cur.fetchone()
        mode = str(row[0]) if row and row[0] else USER_MODE_IDLE
        return mode if mode in ALLOWED_USER_MODES else USER_MODE_IDLE

    async def set_user_mode(self, user_id: int, required_chat: str, mode: str) -> None:
        normalized_mode = mode if mode in ALLOWED_USER_MODES else USER_MODE_IDLE
        now_ts = int(time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_state(user_id, required_chat, subscribed, mode, updated_at_ts)
                VALUES(?, ?, COALESCE(
                    (SELECT subscribed FROM user_state WHERE user_id=? AND required_chat=?),
                    0
                ), ?, ?)
                ON CONFLICT(user_id, required_chat) DO UPDATE SET
                  mode=excluded.mode,
                  updated_at_ts=excluded.updated_at_ts
                """,
                (user_id, required_chat, user_id, required_chat, normalized_mode, now_ts),
            )
            await db.commit()
