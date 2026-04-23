from __future__ import annotations

from pathlib import Path
from time import time

import aiosqlite


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
                  chat_id INTEGER NOT NULL,
                  subscribed INTEGER NOT NULL DEFAULT 0,
                  mode TEXT NOT NULL DEFAULT 'idle',
                  updated_at_ts INTEGER NOT NULL,
                  PRIMARY KEY (user_id, chat_id)
                );
                CREATE TABLE IF NOT EXISTS user_welcome_state (
                  user_id INTEGER PRIMARY KEY,
                  last_welcome_ts INTEGER NOT NULL
                );
                """
            )
            try:
                await db.execute(
                    """
                    ALTER TABLE user_state
                    ADD COLUMN mode TEXT NOT NULL DEFAULT 'idle'
                    """
                )
            except aiosqlite.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
            await db.commit()

    async def get_subscribed(self, user_id: int, chat_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT subscribed FROM user_state WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ) as cur:
                row = await cur.fetchone()
                return bool(row[0]) if row else False

    async def set_subscribed(self, user_id: int, chat_id: int, subscribed: bool) -> None:
        now_ts = int(time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_state(user_id, chat_id, subscribed, mode, updated_at_ts)
                VALUES(?, ?, ?, 'idle', ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                  subscribed=excluded.subscribed,
                  updated_at_ts=excluded.updated_at_ts
                """,
                (user_id, chat_id, 1 if subscribed else 0, now_ts),
            )
            await db.commit()

    async def get_mode(self, user_id: int, chat_id: int) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT mode FROM user_state WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ) as cur:
                row = await cur.fetchone()
                return str(row[0]) if row and row[0] else "idle"

    async def set_mode(self, user_id: int, chat_id: int, mode: str) -> None:
        now_ts = int(time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_state(user_id, chat_id, subscribed, mode, updated_at_ts)
                VALUES(?, ?, 0, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                  mode=excluded.mode,
                  updated_at_ts=excluded.updated_at_ts
                """,
                (user_id, chat_id, mode, now_ts),
            )
            await db.commit()

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
