"""PnL Sentinel — Telegram bot entrypoint (local long-polling).

Run:  python bot.py
"""
from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
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
# The bot is public: /start, /plans, /help, /disclaimer, /howitworks (and their
# buttons) work for anyone. Broker/PnL data commands stay owner-only — guarded
# per-handler below rather than a blanket gate, since public commands must
# reach non-owner chats too.

def is_owner(chat_id: int, owner_id: int) -> bool:
    """Pure check — no Update object needed, so it's trivially testable."""
    return chat_id == owner_id


def _update_is_owner(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and is_owner(chat.id, settings.telegram_chat_id)


OWNER_ONLY_MSG = "🔒 This is a personal command — per-user broker connect is coming soon."


def owner_only(func):
    """Guard a data command/callback: non-owners get a polite refusal, never data."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _update_is_owner(update):
            chat = update.effective_chat
            if chat:
                log.warning("Rejected data command from non-owner chat %s", chat.id)
            if update.callback_query:
                await update.callback_query.answer(OWNER_ONLY_MSG, show_alert=True)
            elif update.message:
                await update.message.reply_text(OWNER_ONLY_MSG)
            return
        return await func(update, context)
    return wrapper


# ───────────────────── onboarding screens ───────────────────
# Public — reachable from any chat. Text + keyboard builders are shared by the
# CommandHandlers (send a new message) and the CallbackQueryHandler (edit the
# existing message in place), so the two navigation paths never drift apart.

TEXT_MAIN = (
    "👋 *Welcome to StockPulse!*\n\n"
    "Real-time PnL alerts for your broker accounts — straight to Telegram, "
    "the moment you hit your profit or loss target.\n\n"
    "No more refreshing a terminal. Set a threshold, get on with your day, "
    "get pinged when it matters.\n\n"
    "What would you like to do?"
)

TEXT_GETSTARTED = (
    "🚀 *Getting Started with StockPulse*\n\n"
    "Here's how it works, in 3 steps:\n\n"
    "1️⃣ *Connect your broker* — Zerodha or Dhan, securely.\n"
    "2️⃣ *Set your alert* — a profit target, a loss limit, or both.\n"
    "3️⃣ *Get pinged* — the moment your combined PnL crosses the line, "
    "right here on Telegram.\n\n"
    "That's it — no dashboards to babysit.\n\n"
    "Before we go further, please take a moment to read our disclaimer 👇"
)

TEXT_DISCLAIMER = (
    "⚠️ *Disclaimer (DRAFT — pending legal review)*\n\n"
    "StockPulse is an *informational tool only*. Nothing here is investment "
    "advice, and nothing should be treated as a recommendation to buy, sell, "
    "or hold any security.\n\n"
    "• We are *not SEBI-registered* investment advisors.\n"
    "• Past performance is *no guarantee* of future results.\n"
    "• PnL figures come from broker APIs and may lag or differ — *always "
    "verify against your broker's own statements* before deciding anything.\n"
    "• You use StockPulse entirely *at your own risk*.\n\n"
    "By tapping \"I Understand\" below, you acknowledge you've read this."
)

TEXT_ACCEPTED = (
    "✅ *Got it — thanks!*\n\n"
    "You're all set to explore StockPulse. Broker connect and live alerts "
    "are coming very soon."
)

TEXT_HOWITWORKS = (
    "❓ *How StockPulse Works*\n\n"
    "```\n"
    "🔌 Connect Broker\n"
    "      ↓\n"
    "🎯 Set Alert Threshold\n"
    "      ↓\n"
    "📡 We Monitor Continuously\n"
    "      ↓\n"
    "🔔 Telegram Ping The Moment You Hit It\n"
    "```\n"
    "• Works across Zerodha & Dhan (more brokers coming)\n"
    "• Combined PnL across all your connected accounts\n"
    "• Alerts latch — one ping per breach, never spam"
)


def text_plans() -> str:
    return (
        "💎 *StockPulse Plans*\n\n"
        "Choose what works for you:\n\n"
        f"• *Monthly* — ₹{settings.plan_monthly_inr}/month\n"
        f"• *Yearly* — ₹{settings.plan_yearly_inr}/year (best value)\n\n"
        "Tap a plan to subscribe."
    )


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Get Started", callback_data="nav:getstarted"),
         InlineKeyboardButton("💎 Plans", callback_data="nav:plans")],
        [InlineKeyboardButton("❓ How it works", callback_data="nav:howitworks"),
         InlineKeyboardButton("📜 Disclaimer", callback_data="nav:disclaimer")],
    ])


def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="nav:main")]])


def kb_getstarted() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Read Disclaimer", callback_data="nav:disclaimer"),
         InlineKeyboardButton("✅ I Understand", callback_data="nav:accept")],
        [InlineKeyboardButton("⬅ Back", callback_data="nav:main")],
    ])


def kb_disclaimer() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Understand", callback_data="nav:accept")],
        [InlineKeyboardButton("⬅ Back", callback_data="nav:main")],
    ])


def kb_plans() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"₹{settings.plan_monthly_inr}/month", callback_data="plan:monthly"),
         InlineKeyboardButton(f"₹{settings.plan_yearly_inr}/year", callback_data="plan:yearly")],
        [InlineKeyboardButton("⬅ Back", callback_data="nav:main")],
    ])


# ─────────────────────── commands ──────────────────────────
def _onboarding_img(name: str) -> Path | None:
    """Return the onboarding image path if it exists, else None (text-only fallback)."""
    p = Path(settings.onboarding_img_dir) / name
    return p if p.is_file() else None


async def _send_banner(message) -> None:
    """Send the hero banner above the menu when the image is present; never fatal."""
    hero = _onboarding_img("hero.jpg")
    if hero is None:
        return
    try:
        await message.reply_photo(hero)
    except Exception:  # noqa: BLE001 — a bad/missing image must not break onboarding
        log.warning("hero banner send failed", exc_info=True)


async def render_screen(context, q, text, kb, photo: Path | None = None) -> None:
    """Render a callback screen, handling text<->photo message transitions.

    Telegram can't edit a text message into a photo (or vice-versa), so when the
    media type of the screen changes we delete the old message and send a new one.
    Same media type = edit in place (keeps the smooth single-message feel).
    """
    msg = q.message
    is_photo_msg = bool(msg.photo)
    try:
        if photo is not None:
            if is_photo_msg:
                await q.edit_message_media(
                    InputMediaPhoto(photo, caption=text, parse_mode=ParseMode.MARKDOWN),
                    reply_markup=kb)
            else:
                await msg.delete()
                await context.bot.send_photo(msg.chat_id, photo, caption=text,
                                             reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        else:
            if is_photo_msg:
                await msg.delete()
                await context.bot.send_message(msg.chat_id, text, reply_markup=kb,
                                               parse_mode=ParseMode.MARKDOWN)
            else:
                await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:  # noqa: BLE001 — a render hiccup must not kill the handler
        log.warning("render_screen failed for a screen transition", exc_info=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await store.mark_started(update.effective_user.id)
    await _send_banner(update.message)
    await update.message.reply_text(TEXT_MAIN, reply_markup=kb_main(),
                                    parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TEXT_MAIN, reply_markup=kb_main(),
                                    parse_mode=ParseMode.MARKDOWN)


async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    img = _onboarding_img("plans.jpg")
    if img is not None:
        await update.message.reply_photo(img, caption=text_plans(),
                                         reply_markup=kb_plans(), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text_plans(), reply_markup=kb_plans(),
                                        parse_mode=ParseMode.MARKDOWN)


async def cmd_disclaimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TEXT_DISCLAIMER, reply_markup=kb_disclaimer(),
                                    parse_mode=ParseMode.MARKDOWN)


async def cmd_howitworks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TEXT_HOWITWORKS, reply_markup=kb_back(),
                                    parse_mode=ParseMode.MARKDOWN)


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Public — every button here is reachable from any chat, no owner check."""
    q = update.callback_query
    data = q.data

    if data in ("plan:monthly", "plan:yearly"):
        await q.answer("💳 Payments launching soon — you'll subscribe right here.",
                       show_alert=True)
        return

    await q.answer()
    if data == "nav:main":
        await render_screen(context, q, TEXT_MAIN, kb_main())
    elif data == "nav:getstarted":
        await render_screen(context, q, TEXT_GETSTARTED, kb_getstarted())
    elif data == "nav:plans":
        await render_screen(context, q, text_plans(), kb_plans(),
                            _onboarding_img("plans.jpg"))
    elif data == "nav:howitworks":
        await render_screen(context, q, TEXT_HOWITWORKS, kb_back())
    elif data == "nav:disclaimer":
        await render_screen(context, q, TEXT_DISCLAIMER, kb_disclaimer())
    elif data == "nav:accept":
        await store.accept_tnc(update.effective_user.id)
        await render_screen(context, q, TEXT_ACCEPTED, kb_back())


@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⏳ Fetching PnL…")
    snaps = await hub.snapshots()
    cfg = await store.get(update.effective_chat.id)
    await msg.edit_text(render_status(snaps, cfg), parse_mode=ParseMode.MARKDOWN)


@owner_only
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


@owner_only
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


@owner_only
async def cmd_clearalerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await store.clear_thresholds(update.effective_chat.id)
    await update.message.reply_text("🧹 All alert thresholds cleared.")


@owner_only
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

    # Public onboarding — any chat.
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("plans", cmd_plans))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("disclaimer", cmd_disclaimer))
    app.add_handler(CommandHandler("howitworks", cmd_howitworks))
    app.add_handler(CallbackQueryHandler(on_menu_callback))

    # Broker/PnL data — owner-only, guarded per-handler by @owner_only.
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
