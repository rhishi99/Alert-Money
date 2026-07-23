"""One-shot live check: prove real broker data flows (no dummy data).

Runs the exact same BrokerHub the bot uses, prints each broker's real snapshot.
ponytail: throwaway smoke check, not a unit test — delete after bootstrap if noisy.
"""
import asyncio
from brokers import BrokerHub
from config import settings


async def main() -> None:
    hub = BrokerHub(settings)
    if not hub.brokers:
        print("No brokers active — check .env (Dhan token / Zerodha daily token).")
        return
    snaps = await hub.snapshots()
    for s in snaps:
        if s.ok:
            print(f"[OK] {s.broker}: realized={s.realized:.2f} unrealized={s.unrealized:.2f} "
                  f"total={s.total:.2f} positions={s.positions_count} holdings={s.holdings_count}")
        else:
            print(f"[ERR] {s.broker}: {s.error[:200]}")
    print(f"Combined PnL: {BrokerHub.combined_total(snaps):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
