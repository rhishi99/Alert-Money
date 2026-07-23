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
from collections.abc import Callable
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

    def __init__(self, client_id: str, access_token: str,
                 token_provider: Callable[[], str] | None = None):
        # token_provider re-resolves a fresh token (e.g. from SSM) so a mid-day
        # token eviction (DH-906, when another app re-mints the shared Dhan
        # session) can self-heal without restarting the bot.
        self.client_id = client_id
        self.token = access_token
        self.token_provider = token_provider
        self._build(access_token)

    def _build(self, access_token: str) -> None:
        from dhanhq import dhanhq  # lazy import
        self.dhan = dhanhq(self.client_id, access_token)

    @staticmethod
    def _is_token_error(err: Exception) -> bool:
        s = str(err).lower()
        return "dh-906" in s or "invalid token" in s

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
            if self._is_token_error(e) and self.token_provider is not None:
                try:
                    fresh = await asyncio.to_thread(self.token_provider)
                    if fresh and fresh != self.token:
                        log.warning("Dhan token invalid — refreshed from source, retrying")
                        self.token = fresh
                        self._build(fresh)
                        return await asyncio.to_thread(self._fetch)  # one retry
                except Exception:  # noqa: BLE001
                    log.exception("Dhan token refresh failed")
            log.exception("Dhan fetch failed")
            return PnLSnapshot(broker=self.name, ok=False, error=str(e))


# ───────────────────────────── Aggregate ────────────────────────────
class BrokerHub:
    """Owns all enabled brokers; fetches snapshots concurrently."""

    def __init__(self, settings):
        import os
        from config import resolve_dhan_token

        self.brokers = []
        if settings.enable_zerodha and settings.kite_api_key and settings.kite_access_token:
            self.brokers.append(ZerodhaBroker(settings.kite_api_key, settings.kite_access_token))
        if settings.enable_dhan and settings.dhan_client_id and settings.dhan_access_token:
            self.brokers.append(DhanBroker(
                settings.dhan_client_id, settings.dhan_access_token,
                token_provider=lambda: resolve_dhan_token(os.environ)))

    @classmethod
    async def for_user(cls, uid: int, store, settings) -> "BrokerHub":
        """Build a hub from a user's OWN encrypted broker connections (Phase 3).

        Decrypts each `enc_token` only here; the plaintext lives on the adapter
        instance for this hub's lifetime and is never stored or logged. Zerodha
        uses OUR global Kite app key + the user's access_token; Dhan uses the
        user's own client_id (from `extra`) + token.
        """
        import json

        from crypto import decrypt

        hub = cls.__new__(cls)  # bypass __init__'s global-owner build
        hub.brokers = []
        for conn in await store.get_broker_conns(uid):
            try:
                token = decrypt(conn["enc_token"])
            except Exception:  # noqa: BLE001 — a bad/rotated token must not kill the tick
                log.warning("Could not decrypt %s token for a user — skipping", conn["broker"])
                continue
            extra = json.loads(conn["extra"]) if conn.get("extra") else {}
            broker = conn["broker"]
            if broker == "zerodha" and settings.kite_api_key:
                hub.brokers.append(ZerodhaBroker(settings.kite_api_key, token))
            elif broker == "dhan" and extra.get("client_id"):
                hub.brokers.append(DhanBroker(extra["client_id"], token))
        return hub

    async def snapshots(self) -> list[PnLSnapshot]:
        if not self.brokers:
            return []
        return list(await asyncio.gather(*(b.snapshot() for b in self.brokers)))

    @staticmethod
    def combined_total(snaps: list[PnLSnapshot]) -> float:
        return sum(s.total for s in snaps if s.ok)
