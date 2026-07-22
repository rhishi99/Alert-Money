"""PnL Sentinel — Telegram bot entrypoint (local long-polling).

Run:  python bot.py
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationHandlerStop, CommandHandler, ContextTypes, TypeHandler,
)

from alerts import AlertEngine
from brokers import BrokerHub, PnLSnapshot
from config import settings
from storage import Store

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("pnl-sentinel")

store = Store(settings.db_path)
hub = BrokerHub(settings)
engine = AlertEngine(store)


# ───────────────────────── helpers ─────────────────────────
def fmt_money(x: float) -> str:
    sign = "🟢" if x >= 0 else "🔴"
    return f"{sign} ₹{x:,.2f}"


def render_status(snaps: list[PnLSnapshot], cfg) -> str:
    if not snaps:
        return ("⚠️ No brokers are configured/enabled.\n"
                "Check your `.env` (KITE_ACCESS_TOKEN / DHAN_ACCESS_TOKEN).")
    lines = ["📊 *PnL Status*", ""]
    for s in snaps:
        if not s.ok:
            lines.append(f"*{s.broker}*: ❌ error — `{s.error[:120]}`")
            continue
        lines.append(
            f"*{s.broker}*  (pos: {s.positions_count}, holdings: {s.holdings_count})\n"
            f"  Realized: {fmt_money(s.realized)}\n"
            f"  Unrealized: {fmt_money(s.unrealized)}\n"
            f"  Total: {fmt_money(s.total)}"
        )
    combined = BrokerHub.combined_total(snaps)
    lines += ["", f"Σ *Combined PnL: {fmt_money(combined)}*", ""]
    pt = f"₹{cfg.profit_threshold:,.0f}" + (" (fired)" if cfg.profit_triggered else " (armed)") \
        if cfg.profit_threshold is not None else "—"
    lt = f"₹{cfg.loss_threshold:,.0f}" + (" (fired)" if cfg.loss_triggered else " (armed)") \
        if cfg.loss_threshold is not None else "—"
    lines.append(f"🎯 Profit alert: {pt}\n🛑 Loss alert: {lt}")
    return "\n".join(lines)


# ─────────────────────── auth gate ─────────────────────────
async def gatekeeper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Drop every update that is not from the owner chat."""
    chat = update.effective_chat
    if chat is None or chat.id != settings.telegram_chat_id:
        if chat:
            log.warning("Rejected update from unauthorized chat %s", chat.id)
        raise ApplicationHandlerStop


# ─────────────────────── commands ──────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *PnL Sentinel online.*\n\n"
        "Commands:\n"
        "/status — live PnL across brokers\n"
        "/positions — per-instrument breakdown\n"
        "/setalert profit 10000 — alert when combined PnL ≥ +10,000\n"
        "/setalert loss -5000 — alert when combined PnL ≤ −5,000\n"
        "/clearalerts — remove both thresholds\n"
        "/resetalerts — re-arm fired alerts\n"
        f"\nMonitoring every {settings.poll_interval}s during the trading day.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⏳ Fetching PnL…")
    snaps = await hub.snapshots()
    cfg = await store.get(update.effective_chat.id)
    await msg.edit_text(render_status(snaps, cfg), parse_mode=ParseMode.MARKDOWN)


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⏳ Fetching positions…")
    snaps = await hub.snapshots()
    parts = []
    for s in snaps:
        if not s.ok:
            parts.append(f"*{s.broker}*: ❌ {s.error[:120]}")
        elif s.lines:
            parts.append(f"*{s.broker}*\n" + "\n".join(f"• {l}" for l in s.lines[:30]))
        else:
            parts.append(f"*{s.broker}*: no active positions today.")
    await msg.edit_text("\n\n".join(parts) or "No brokers configured.",
                        parse_mode=ParseMode.MARKDOWN)


async def cmd_setalert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    usage = ("Usage:\n`/setalert profit 10000`\n`/setalert loss -5000`\n"
             "(loss value may be given as -5000 or 5000; it is stored as negative)")
    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(usage, parse_mode=ParseMode.MARKDOWN)
        return
    kind, raw = args[0].lower(), args[1].replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        await update.message.reply_text(usage, parse_mode=ParseMode.MARKDOWN)
        return

    if kind == "profit":
        if value <= 0:
            await update.message.reply_text("Profit threshold must be positive.")
            return
        await store.set_profit(chat_id, value)
        await update.message.reply_text(
            f"✅ Profit alert set: fire when combined PnL ≥ ₹{value:,.2f}")
    elif kind == "loss":
        value = -abs(value)  # normalize: losses are negative
        await store.set_loss(chat_id, value)
        await update.message.reply_text(
            f"✅ Loss alert set: fire when combined PnL ≤ ₹{value:,.2f}")
    else:
        await update.message.reply_text(usage, parse_mode=ParseMode.MARKDOWN)


async def cmd_clearalerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await store.clear_thresholds(update.effective_chat.id)
    await update.message.reply_text("🧹 All alert thresholds cleared.")


async def cmd_resetalerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await store.reset_latches(update.effective_chat.id)
    await update.message.reply_text("🔄 Alerts re-armed. They can fire again.")


# ───────────────────── monitoring job ──────────────────────
async def monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = settings.telegram_chat_id
    cfg = await store.get(chat_id)
    if cfg.profit_threshold is None and cfg.loss_threshold is None:
        return  # nothing to watch — skip API calls entirely

    snaps = await hub.snapshots()
    failures = [s for s in snaps if not s.ok]
    ok_snaps = [s for s in snaps if s.ok]

    # Notify (once) if a broker starts erroring, e.g. Kite token expired.
    bad = context.bot_data.setdefault("broker_down", set())
    for s in failures:
        if s.broker not in bad:
            bad.add(s.broker)
            await context.bot.send_message(
                chat_id, f"⚠️ {s.broker} API error — excluded from PnL until it "
                         f"recovers:\n`{s.error[:200]}`", parse_mode=ParseMode.MARKDOWN)
    for s in ok_snaps:
        bad.discard(s.broker)

    if not ok_snaps:
        return

    total = BrokerHub.combined_total(ok_snaps)
    for event in await engine.evaluate(chat_id, total):
        await context.bot.send_message(chat_id, event.message,
                                       parse_mode=ParseMode.MARKDOWN)
        log.info("Fired %s alert at PnL %.2f", event.kind, total)


async def post_init(app: Application) -> None:
    await store.init()
    names = [b.name for b in hub.brokers] or ["none — check .env"]
    log.info("Brokers active: %s", ", ".join(names))
    try:
        await app.bot.send_message(
            settings.telegram_chat_id,
            f"🚀 PnL Sentinel started. Brokers: {', '.join(names)}. "
            f"Polling every {settings.poll_interval}s.")
    except Exception:
        log.exception("Could not message owner chat — check TELEGRAM_CHAT_ID")


def main() -> None:
    app = Application.builder().token(settings.telegram_token).post_init(post_init).build()

    app.add_handler(TypeHandler(Update, gatekeeper), group=-1)  # auth first
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("setalert", cmd_setalert))
    app.add_handler(CommandHandler("clearalerts", cmd_clearalerts))
    app.add_handler(CommandHandler("resetalerts", cmd_resetalerts))

    app.job_queue.run_repeating(monitor, interval=settings.poll_interval, first=5,
                                name="pnl-monitor")

    log.info("Starting long-polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
