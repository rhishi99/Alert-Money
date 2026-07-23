"""SQLite persistence for alert thresholds and anti-spam state.

Schema (single row per chat):
    alerts(chat_id PK, profit_threshold, loss_threshold,
           profit_triggered, loss_triggered, updated_at)

`*_triggered` implements the alert latch: once fired, an alert stays silent
until PnL re-crosses back inside the threshold (with hysteresis) or the user
runs /resetalerts or changes the threshold.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    chat_id           INTEGER PRIMARY KEY,
    profit_threshold  REAL,
    loss_threshold    REAL,
    profit_triggered  INTEGER NOT NULL DEFAULT 0,
    loss_triggered    INTEGER NOT NULL DEFAULT 0,
    updated_at        REAL NOT NULL
);
"""

# Onboarding: one row per Telegram user who has touched /start. No PII beyond
# the Telegram user id.
_SCHEMA_ONBOARDING = """
CREATE TABLE IF NOT EXISTS onboarding (
    telegram_user_id INTEGER PRIMARY KEY,
    tnc_accepted_at   TEXT,
    started_at        TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AlertConfig:
    chat_id: int
    profit_threshold: float | None
    loss_threshold: float | None
    profit_triggered: bool
    loss_triggered: bool


class Store:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(_SCHEMA)
            await db.execute(_SCHEMA_ONBOARDING)
            await db.commit()

    async def get(self, chat_id: int) -> AlertConfig:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM alerts WHERE chat_id=?", (chat_id,))
            row = await cur.fetchone()
        if row is None:
            return AlertConfig(chat_id, None, None, False, False)
        return AlertConfig(
            chat_id=chat_id,
            profit_threshold=row["profit_threshold"],
            loss_threshold=row["loss_threshold"],
            profit_triggered=bool(row["profit_triggered"]),
            loss_triggered=bool(row["loss_triggered"]),
        )

    async def _upsert(self, chat_id: int, **cols) -> None:
        cfg = await self.get(chat_id)
        merged = {
            "profit_threshold": cfg.profit_threshold,
            "loss_threshold": cfg.loss_threshold,
            "profit_triggered": int(cfg.profit_triggered),
            "loss_triggered": int(cfg.loss_triggered),
        }
        merged.update(cols)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO alerts
                   (chat_id, profit_threshold, loss_threshold,
                    profit_triggered, loss_triggered, updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                     profit_threshold=excluded.profit_threshold,
                     loss_threshold=excluded.loss_threshold,
                     profit_triggered=excluded.profit_triggered,
                     loss_triggered=excluded.loss_triggered,
                     updated_at=excluded.updated_at""",
                (chat_id, merged["profit_threshold"], merged["loss_threshold"],
                 merged["profit_triggered"], merged["loss_triggered"], time.time()),
            )
            await db.commit()

    # Setting a threshold re-arms its latch.
    async def set_profit(self, chat_id: int, value: float) -> None:
        await self._upsert(chat_id, profit_threshold=value, profit_triggered=0)

    async def set_loss(self, chat_id: int, value: float) -> None:
        await self._upsert(chat_id, loss_threshold=value, loss_triggered=0)

    async def clear_thresholds(self, chat_id: int) -> None:
        await self._upsert(chat_id, profit_threshold=None, loss_threshold=None,
                           profit_triggered=0, loss_triggered=0)

    async def set_triggered(self, chat_id: int, *, profit: bool | None = None,
                            loss: bool | None = None) -> None:
        cols = {}
        if profit is not None:
            cols["profit_triggered"] = int(profit)
        if loss is not None:
            cols["loss_triggered"] = int(loss)
        if cols:
            await self._upsert(chat_id, **cols)

    async def reset_latches(self, chat_id: int) -> None:
        await self._upsert(chat_id, profit_triggered=0, loss_triggered=0)

    # ─────────────────────── onboarding ────────────────────────
    async def mark_started(self, uid: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO onboarding (telegram_user_id, started_at) "
                "VALUES (?, ?)",
                (uid, _now_iso()),
            )
            await db.commit()

    async def accept_tnc(self, uid: int) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO onboarding (telegram_user_id, started_at, tnc_accepted_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(telegram_user_id) DO UPDATE SET
                     tnc_accepted_at=excluded.tnc_accepted_at""",
                (uid, now, now),
            )
            await db.commit()

    async def has_accepted(self, uid: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT tnc_accepted_at FROM onboarding WHERE telegram_user_id=?", (uid,)
            )
            row = await cur.fetchone()
        return row is not None and row[0] is not None
