"""Verification suite for the alert engine: latch, hysteresis, re-arm,
dual-side breach, and restart persistence."""
import asyncio, os, tempfile
from storage import Store
from alerts import AlertEngine

CHAT = 42

async def fresh():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    s = Store(path); await s.init()
    return s, path

async def test_latch_one_alert():
    s, path = await fresh(); e = AlertEngine(s)
    await s.set_profit(CHAT, 10000)
    a = await e.evaluate(CHAT, 12000)      # breach
    b = await e.evaluate(CHAT, 12500)      # still above -> should be silent
    assert len(a) == 1 and a[0].kind == "profit", a
    assert b == [], f"latch failed, re-fired: {b}"
    os.remove(path); print("PASS latch: one alert per breach episode")

async def test_hysteresis_no_flap():
    s, path = await fresh(); e = AlertEngine(s)
    await s.set_profit(CHAT, 10000)
    await e.evaluate(CHAT, 10001)          # trigger
    # oscillate just below threshold but above rearm (10000-5%=9500)
    assert await e.evaluate(CHAT, 9800) == []
    assert await e.evaluate(CHAT, 10050) == [], "re-fired without re-arm"
    os.remove(path); print("PASS hysteresis: no flapping in the band")

async def test_rearm_after_retreat():
    s, path = await fresh(); e = AlertEngine(s)
    await s.set_profit(CHAT, 10000)
    await e.evaluate(CHAT, 10001)          # trigger
    await e.evaluate(CHAT, 9400)           # below 9500 rearm level -> re-arms
    a = await e.evaluate(CHAT, 10001)      # genuine second breach
    assert len(a) == 1, f"did not re-fire after real recovery: {a}"
    os.remove(path); print("PASS re-arm: fires again after genuine retreat+breach")

async def test_dual_side():
    s, path = await fresh(); e = AlertEngine(s)
    await s.set_profit(CHAT, 10000); await s.set_loss(CHAT, -5000)
    prof = await e.evaluate(CHAT, 11000)
    loss = await e.evaluate(CHAT, -6000)
    assert len(prof) == 1 and prof[0].kind == "profit"
    assert len(loss) == 1 and loss[0].kind == "loss"
    os.remove(path); print("PASS dual-side: profit and loss latches independent")

async def test_persistence_across_restart():
    s, path = await fresh(); e = AlertEngine(s)
    await s.set_loss(CHAT, -5000)
    await e.evaluate(CHAT, -6000)          # trigger + latch persisted
    # simulate restart: brand new Store on same file
    s2 = Store(path); await s2.init(); e2 = AlertEngine(s2)
    cfg = await s2.get(CHAT)
    assert cfg.loss_threshold == -5000, cfg
    assert cfg.loss_triggered is True, "latch state lost across restart"
    assert await e2.evaluate(CHAT, -6500) == [], "re-fired after restart (latch not restored)"
    os.remove(path); print("PASS persistence: thresholds + latch survive restart")

async def main():
    for t in (test_latch_one_alert, test_hysteresis_no_flap, test_rearm_after_retreat,
              test_dual_side, test_persistence_across_restart):
        await t()
    print("\nALL 5 TESTS PASSED")

asyncio.run(main())
