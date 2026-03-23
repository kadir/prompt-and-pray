"""
Dual-Bot Autonomous Orchestrator
---------------------------------
Two bots, one process, one asyncio event loop.

Message routing:
  User → @Architect bot  →  gemini ask  →  forwards plan → @Builder bot
                                                              └─ claude -p
                                                              └─ reports back → @Architect
                                                                                 └─ critiques
                                                                                 └─ Fix / Next Step → @Builder
                                                                                 └─ [loop >= 3] → alerts User, halts

Security:
  Both bots ONLY respond to messages from MY_TELEGRAM_ID or the other bot's ID.
  All other senders are silently ignored.

Trigger keywords:
  @Architect  — activates the Architect handler
  @Builder    — activates the Builder handler
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import ARCHITECT_TOKEN, BUILDER_TOKEN, MY_TELEGRAM_ID
from orchestrator.engine import gemini, claude

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Safety counter ────────────────────────────────────────────────────────────
MAX_AUTO_LOOPS = 3
loop_count: int = 0
awaiting_human: bool = False


def _increment_loop() -> bool:
    """Increment counter. Returns True when the limit is reached."""
    global loop_count, awaiting_human
    loop_count += 1
    logger.info("Auto-loop: %d / %d", loop_count, MAX_AUTO_LOOPS)
    if loop_count >= MAX_AUTO_LOOPS and not awaiting_human:
        awaiting_human = True
        return True
    return False


def _reset_loop() -> None:
    global loop_count, awaiting_human
    loop_count = 0
    awaiting_human = False


# ── Allowlist filter factory ──────────────────────────────────────────────────

def _make_allowlist_filter(own_id: int, peer_id: int) -> filters.BaseFilter:
    """
    Accept messages ONLY from:
      - the human owner (MY_TELEGRAM_ID)
      - the peer bot (so the autonomous loop works)
    Reject everyone else, including this bot itself.
    """
    return filters.User(user_id=[MY_TELEGRAM_ID, peer_id]) & ~filters.User(own_id)


# ── Architect handlers ────────────────────────────────────────────────────────

async def architect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Architect online. Mention @Architect in your message to activate me."
    )


async def architect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered when an allowed sender writes a message containing '@Architect'.
    Calls Gemini CLI, then forwards the plan to the Builder bot.
    """
    global awaiting_human

    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    # Human replied while paused — reset and resume
    if awaiting_human and sender_id == MY_TELEGRAM_ID:
        _reset_loop()
        await update.message.reply_text("Resuming autonomous operation.")

    if awaiting_human:
        return  # still paused, non-human message — ignore

    await update.message.reply_text("Consulting Gemini…")

    try:
        plan = gemini.ask(
            "You are a software architect. Given this task, write a concise "
            "step-by-step implementation plan for a developer. "
            "If the work is done, say 'Next Step: ...' to continue, or "
            "'Fix: ...' to request a correction.\n\n"
            f"Task: {text}"
        )
    except RuntimeError as e:
        await update.message.reply_text(f"Gemini error: {e}")
        return

    await update.message.reply_text(f"Architect plan:\n\n{plan}")

    builder_app: Application = context.bot_data["builder_app"]
    await builder_app.bot.send_message(
        chat_id=chat_id,
        text=f"@Builder {plan}",
    )


async def architect_critique(
    bot_context: ContextTypes.DEFAULT_TYPE,
    builder_report: str,
    chat_id: int,
) -> None:
    """
    Called programmatically after the Builder finishes.
    Critiques the report and issues Fix or Next Step — or halts for human input.
    """
    await bot_context.bot.send_message(chat_id=chat_id, text="Architect reviewing…")

    try:
        verdict = gemini.ask(
            "You are a senior software architect doing a code review. "
            "Respond with EXACTLY one of:\n"
            "  'Fix: <specific issue>'  — if there is a problem\n"
            "  'Next Step: <next action>'  — if the work is acceptable\n\n"
            f"Builder report:\n{builder_report}"
        )
    except RuntimeError as e:
        await bot_context.bot.send_message(chat_id=chat_id, text=f"Gemini error: {e}")
        return

    await bot_context.bot.send_message(
        chat_id=chat_id,
        text=f"Architect verdict:\n\n{verdict}",
    )

    limit_reached = _increment_loop()
    if limit_reached:
        await bot_context.bot.send_message(
            chat_id=MY_TELEGRAM_ID,
            text=(
                f"⚠️ Auto-loop limit ({MAX_AUTO_LOOPS}) reached.\n\n"
                f"Last verdict:\n{verdict}\n\n"
                "Reply to @Architect to approve and continue."
            ),
        )
        return

    builder_app: Application = bot_context.bot_data["builder_app"]
    await builder_app.bot.send_message(
        chat_id=chat_id,
        text=f"@Builder {verdict}",
    )


# ── Builder handlers ──────────────────────────────────────────────────────────

async def builder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Builder online. Mention @Builder in your message to activate me."
    )


async def builder_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered when an allowed sender writes a message containing '@Builder'.
    Runs `claude -p` with the directive and reports back to the Architect.
    """
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    await update.message.reply_text("Running claude -p…")

    try:
        report = claude.run(text)
    except RuntimeError as e:
        await update.message.reply_text(f"Claude error: {e}")
        return

    await update.message.reply_text(f"Builder report:\n\n{report}")

    # Pass report back to Architect for critique
    architect_app: Application = context.bot_data["architect_app"]
    await architect_critique(
        bot_context=architect_app,
        builder_report=report,
        chat_id=chat_id,
    )


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def _build_architect_app(architect_id: int, builder_id: int) -> Application:
    allowlist = _make_allowlist_filter(own_id=architect_id, peer_id=builder_id)
    app = Application.builder().token(ARCHITECT_TOKEN).build()
    app.add_handler(CommandHandler("start", architect_start))
    app.add_handler(
        MessageHandler(
            allowlist & filters.TEXT & ~filters.COMMAND & filters.Regex(r"@Architect"),
            architect_message,
        )
    )
    return app


def _build_builder_app(builder_id: int, architect_id: int) -> Application:
    allowlist = _make_allowlist_filter(own_id=builder_id, peer_id=architect_id)
    app = Application.builder().token(BUILDER_TOKEN).build()
    app.add_handler(CommandHandler("start", builder_start))
    app.add_handler(
        MessageHandler(
            allowlist & filters.TEXT & ~filters.COMMAND & filters.Regex(r"@Builder"),
            builder_message,
        )
    )
    return app


async def main():
    # Phase 1: resolve real bot IDs from Telegram before wiring filters.
    probe_arch = Application.builder().token(ARCHITECT_TOKEN).build()
    probe_build = Application.builder().token(BUILDER_TOKEN).build()
    async with probe_arch, probe_build:
        architect_id = probe_arch.bot.id
        builder_id   = probe_build.bot.id
    logger.info("Architect bot ID: %d | Builder bot ID: %d", architect_id, builder_id)

    # Phase 2: build real apps with correct allowlist filters.
    architect_app = _build_architect_app(architect_id, builder_id)
    builder_app   = _build_builder_app(builder_id, architect_id)

    # Cross-wire so handlers can reach the peer bot.
    architect_app.bot_data["builder_app"]   = builder_app
    builder_app.bot_data["architect_app"]   = architect_app

    logger.info("Starting both bots…")

    async with architect_app, builder_app:
        await architect_app.start()
        await builder_app.start()

        await asyncio.gather(
            architect_app.updater.start_polling(drop_pending_updates=True),
            builder_app.updater.start_polling(drop_pending_updates=True),
        )

        await asyncio.Event().wait()  # block until Ctrl+C

        await architect_app.updater.stop()
        await builder_app.updater.stop()
        await architect_app.stop()
        await builder_app.stop()


if __name__ == "__main__":
    asyncio.run(main())
