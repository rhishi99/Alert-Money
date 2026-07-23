"""Broker adapters.

Each adapter exposes one async method, `snapshot()`, returning a PnLSnapshot.
Both the kiteconnect and dhanhq SDKs are synchronous, so we push their blocking
HTTP calls onto a thread with asyncio.to_thread — the Telegram event loop is
never blocked.

PnL semantics
-------------
realized   : booked PnL on positions closed today (day sell/buy legs)
unrealized : mark-to-market PnL on open positions + holdings vs avg cost
total      : realized + unrealized
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class PnLSnapshot:
    broker: str
    realized: float = 0.0
    unrealized: float = 0.0
    positions_count: int = 0
    holdings_count: int = 0
    ok: bool = True
    error: str = ""
    lines: list[str] = field(default_factory=list)  # per-instrument detail

    @property
    def total(self) -> float:
        return self.realized + self.unrealized


# ───────────────────────────── Zerodha ──────────────────────────────
class ZerodhaBroker:
    name = "Zerodha"

    def __init__(self, api_key: str, access_token: str):
        from kiteconnect import KiteConnect  # lazy import
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def _fetch(self) -> PnLSnapshot:
        snap = PnLSnapshot(broker=self.name)

        # Positions: kite gives per-position `pnl` (total), `m2m`, and split
        # realized/unrealized via day buy/sell values. `pnl` on the "net" book
        # is realized + unrealized for the day.
        positions = self.kite.positions().get("net", [])
        for p in positions:
            if p["quantity"] == 0 and p["overnight_quantity"] == 0:
                # fully closed today → its pnl is realized
                snap.realized += p["pnl"]
            else:
                snap.unrealized += p["unrealised"]
                snap.realized += p["realised"]
            if p["quantity"] != 0 or abs(p["pnl"]) > 0.005:
                snap.lines.append(
                    f"{p['tradingsymbol']}: qty {p['quantity']}, PnL ₹{p['pnl']:,.2f}"
                )
        snap.positions_count = sum(1 for p in positions if p["quantity"] != 0)

        # Holdings: unrealized = (ltp - avg_price) * qty, kite provides `pnl`.
        holdings = self.kite.holdings()
        for h in holdings:
            qty = h["quantity"] + h.get("t1_quantity", 0)
            if qty:
                snap.unrealized += h["pnl"]
                snap.holdings_count += 1
        return snap

    async def snapshot(self) -> PnLSnapshot:
        try:
            return await asyncio.to_thread(self._fetch)
        except Exception as e:  # noqa: BLE001 — surface any SDK/API failure
            log.exception("Zerodha fetch failed")
            return PnLSnapshot(broker=self.name, ok=False, error=str(e))


# ─────────────────────────────── Dhan ───────────────────────────────
class DhanBroker:
    name = "Dhan"

    def __init__(self, client_id: str, access_token: str):
        from dhanhq import dhanhq  # lazy import
        self.dhan = dhanhq(client_id, access_token)

    @staticmethod
    def _data(resp) -> list[dict]:
        """dhanhq wraps responses as {'status':..., 'data': [...]}. Normalize."""
        if isinstance(resp, dict):
            if str(resp.get("status", "")).lower() in {"failure", "error"}:
                raise RuntimeError(resp.get("remarks") or resp.get("data") or "Dhan API error")
            data = resp.get("data", [])
            return data if isinstance(data, list) else []
        return resp or []

    def _fetch(self) -> PnLSnapshot:
        snap = PnLSnapshot(broker=self.name)

        for p in self._data(self.dhan.get_positions()):
            realized = float(p.get("realizedProfit", 0) or 0)
            unrealized = float(p.get("unrealizedProfit", 0) or 0)
            snap.realized += realized
            snap.unrealized += unrealized
            net_qty = int(p.get("netQty", 0) or 0)
            if net_qty != 0:
                snap.positions_count += 1
            if net_qty != 0 or abs(realized) + abs(unrealized) > 0.005:
                snap.lines.append(
                    f"{p.get('tradingSymbol', '?')}: qty {net_qty}, "
                    f"PnL ₹{realized + unrealized:,.2f}"
                )

        # Holdings endpoint has no LTP → avg-cost basis only; Dhan does not
        # return holding MTM here, so holdings contribute count, not PnL.
        # (Positions cover all intraday + F&O PnL, which is what alerting needs.)
        try:
            snap.holdings_count = len(self._data(self.dhan.get_holdings()))
        except Exception:  # holdings may 404 for accounts with none
            pass
        return snap

    async def snapshot(self) -> PnLSnapshot:
        try:
            return await asyncio.to_thread(self._fetch)
        except Exception as e:  # noqa: BLE001
            log.exception("Dhan fetch failed")
            return PnLSnapshot(broker=self.name, ok=False, error=str(e))


# ───────────────────────────── Aggregate ────────────────────────────
class BrokerHub:
    """Owns all enabled brokers; fetches snapshots concurrently."""

    def __init__(self, settings):
        self.brokers = []
        if settings.enable_zerodha and settings.kite_api_key and settings.kite_access_token:
            self.brokers.append(ZerodhaBroker(settings.kite_api_key, settings.kite_access_token))
        if settings.enable_dhan and settings.dhan_client_id and settings.dhan_access_token:
            self.brokers.append(DhanBroker(settings.dhan_client_id, settings.dhan_access_token))

    async def snapshots(self) -> list[PnLSnapshot]:
        if not self.brokers:
            return []
        return list(await asyncio.gather(*(b.snapshot() for b in self.brokers)))

    @staticmethod
    def combined_total(snaps: list[PnLSnapshot]) -> float:
        return sum(s.total for s in snaps if s.ok)
