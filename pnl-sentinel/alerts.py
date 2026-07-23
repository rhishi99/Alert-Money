"""Alerting engine.

State machine per threshold (latch + hysteresis):

    ARMED ──(PnL crosses threshold)──▶ TRIGGERED  → send ONE alert
    TRIGGERED ──(PnL re-enters band by ≥ HYSTERESIS_PCT of threshold)──▶ ARMED

This guarantees exactly one message per breach episode: no spam while PnL
hovers around the line, and automatic re-arming if PnL genuinely recovers
and breaches again later. /resetalerts or /setalert also re-arm manually.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from storage import Store

log = logging.getLogger(__name__)

HYSTERESIS_PCT = 0.05  # must retreat 5% of the threshold value to re-arm


@dataclass
class AlertEvent:
    kind: str      # "profit" | "loss"
    message: str


class AlertEngine:
    def __init__(self, store: Store):
        self.store = store

    async def evaluate(self, chat_id: int, total_pnl: float) -> list[AlertEvent]:
        cfg = await self.store.get(chat_id)
        events: list[AlertEvent] = []

        # ── Profit side ──
        if cfg.profit_threshold is not None:
            t = cfg.profit_threshold
            rearm_level = t - abs(t) * HYSTERESIS_PCT
            if not cfg.profit_triggered and total_pnl >= t:
                await self.store.set_triggered(chat_id, profit=True)
                events.append(AlertEvent(
                    "profit",
                    f"🎯 *Profit target hit!*\n"
                    f"PnL ₹{total_pnl:,.2f} ≥ target ₹{t:,.2f}\n"
                    f"_Alert latched — re-arms if PnL drops below ₹{rearm_level:,.2f}, "
                    f"or use /resetalerts._",
                ))
            elif cfg.profit_triggered and total_pnl < rearm_level:
                await self.store.set_triggered(chat_id, profit=False)
                log.info("Profit alert re-armed for %s (PnL %.2f)", chat_id, total_pnl)

        # ── Loss side (threshold stored as a negative number) ──
        if cfg.loss_threshold is not None:
            t = cfg.loss_threshold
            rearm_level = t + abs(t) * HYSTERESIS_PCT
            if not cfg.loss_triggered and total_pnl <= t:
                await self.store.set_triggered(chat_id, loss=True)
                events.append(AlertEvent(
                    "loss",
                    f"🛑 *Loss limit breached!*\n"
                    f"PnL ₹{total_pnl:,.2f} ≤ limit ₹{t:,.2f}\n"
                    f"_Consider reducing exposure. Re-arms above ₹{rearm_level:,.2f}, "
                    f"or use /resetalerts._",
                ))
            elif cfg.loss_triggered and total_pnl > rearm_level:
                await self.store.set_triggered(chat_id, loss=False)
                log.info("Loss alert re-armed for %s (PnL %.2f)", chat_id, total_pnl)

        return events
