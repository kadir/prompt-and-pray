"""
Dual-Bot Autonomous Orchestrator
---------------------------------
Two bots, one process, one asyncio event loop.

IMPORTANT — bot-to-bot communication:
  Telegram does NOT deliver messages from one bot to another via polling.
  All Architect ↔ Builder handoffs are therefore direct Python function calls,
  NOT Telegram send_message() calls. Only user-facing status messages go through
  Telegram so the human can follow along.

Message routing:
  User → @Architect handler (Telegram trigger)
           └─ gemini.ask()
           └─ _run_builder_task()  ← direct Python call, NOT Telegram
                └─ claude.run()
                └─ sends Builder report to Telegram (user visibility)
                └─ architect_critique()  ← direct Python call
                        └─ gemini.ask()
                        └─ sends verdict to Telegram (user visibility)
                        └─ [loop < 3] → _run_builder_task() again
                        └─ [loop >= 3] → alerts MY_TELEGRAM_ID, halts

Security:
  Both bots ONLY respond to Telegram messages from MY_TELEGRAM_ID.
  Bot-to-bot messages never travel through Telegram at all.
"""

import asyncio
import logging

from telegram import Bot
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
    """Increment counter. Returns True when the safety limit is reached."""
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


# ── Core loop (direct Python calls — no Telegram bot-to-bot messaging) ────────

async def _run_builder_task(
    directive: str,
    chat_id: int,
    architect_bot: Bot,
    builder_bot: Bot,
) -> None:
    """
    Run the Builder (claude -p), post the report to Telegram for the user,
    then hand the report directly to architect_critique().
    """
    await builder_bot.send_message(chat_id=chat_id, text="Builder running claude -p…")

    try:
        report = claude.run(directive)
    except RuntimeError as e:
        await builder_bot.send_message(chat_id=chat_id, text=f"Claude error: {e}")
        return

    await builder_bot.send_message(
        chat_id=chat_id,
        text=f"Builder report:\n\n{report}",
    )

    # Hand off directly — no Telegram round-trip
    await _architect_critique(
        report=report,
        chat_id=chat_id,
        architect_bot=architect_bot,
        builder_bot=builder_bot,
    )


async def _architect_critique(
    report: str,
    chat_id: int,
    architect_bot: Bot,
    builder_bot: Bot,
) -> None:
    """
    Run the Architect critique (gemini ask), post the verdict to Telegram,
    then either loop back to _run_builder_task or halt for human input.
    """
    await architect_bot.send_message(chat_id=chat_id, text="Architect reviewing…")

    try:
        verdict = gemini.ask(
            "You are a senior software architect doing a code review. "
            "Respond with EXACTLY one of:\n"
            "  'Fix: <specific issue>'  — if there is a problem\n"
            "  'Next Step: <next action>'  — if the work is acceptable\n\n"
            f"Builder report:\n{report}"
        )
    except RuntimeError as e:
        await architect_bot.send_message(chat_id=chat_id, text=f"Gemini error: {e}")
        return

    await architect_bot.send_message(
        chat_id=chat_id,
        text=f"Architect verdict:\n\n{verdict}",
    )

    if _increment_loop():
        await architect_bot.send_message(
            chat_id=MY_TELEGRAM_ID,
            text=(
                f"⚠️ Auto-loop limit ({MAX_AUTO_LOOPS}) reached.\n\n"
                f"Last verdict:\n{verdict}\n\n"
                "Reply to @Architect to approve and continue."
            ),
        )
        return

    # Loop: send verdict back through the Builder — direct Python call
    await _run_builder_task(
        directive=verdict,
        chat_id=chat_id,
        architect_bot=architect_bot,
        builder_bot=builder_bot,
    )


# ── Architect Telegram handlers (human → bot only) ────────────────────────────

async def architect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Architect online. Send me a task to begin."
    )


async def architect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Human-triggered entry point. Calls Gemini then kicks off the loop."""
    global awaiting_human

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if awaiting_human:
        _reset_loop()
        await update.message.reply_text("Resuming autonomous operation.")

    await update.message.reply_text("Consulting Gemini…")

    try:
        plan = gemini.ask(
            "You are a software architect. Given this task, write a concise "
            "step-by-step implementation plan for a developer.\n\n"
            f"Task: {text}"
        )
    except RuntimeError as e:
        await update.message.reply_text(f"Gemini error: {e}")
        return

    await update.message.reply_text(f"Architect plan:\n\n{plan}")

    builder_bot: Bot = context.bot_data["builder_bot"]
    # Kick off builder — direct Python call, not a Telegram message
    await _run_builder_task(
        directive=plan,
        chat_id=chat_id,
        architect_bot=context.bot,
        builder_bot=builder_bot,
    )


# ── Builder Telegram handlers (human → bot only) ──────────────────────────────

async def builder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Builder online. Send me a directive to execute."
    )


async def builder_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Human-triggered entry point (for direct Builder testing)."""
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    architect_bot: Bot = context.bot_data["architect_bot"]
    await _run_builder_task(
        directive=text,
        chat_id=chat_id,
        architect_bot=architect_bot,
        builder_bot=context.bot,
    )


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def _build_architect_app() -> Application:
    """Architect responds only to MY_TELEGRAM_ID messages."""
    app = Application.builder().token(ARCHITECT_TOKEN).build()
    app.add_handler(CommandHandler("start", architect_start))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(MY_TELEGRAM_ID),
            architect_message,
        )
    )
    return app


def _build_builder_app() -> Application:
    """Builder responds only to MY_TELEGRAM_ID messages (direct testing only)."""
    app = Application.builder().token(BUILDER_TOKEN).build()
    app.add_handler(CommandHandler("start", builder_start))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(MY_TELEGRAM_ID),
            builder_message,
        )
    )
    return app


async def main():
    architect_app = _build_architect_app()
    builder_app   = _build_builder_app()

    # Share Bot objects (not full Applications) for cross-bot messaging
    architect_app.bot_data["builder_bot"] = builder_app.bot
    builder_app.bot_data["architect_bot"] = architect_app.bot

    logger.info("Starting Architect and Builder bots…")

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
