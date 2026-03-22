"""
Dual-Bot Autonomous Orchestrator
---------------------------------
Architect bot  →  runs `gemini ask` via CLI, critiques Builder output,
                  issues Fix / Next Step commands.
Builder bot    →  runs `claude` via CLI, executes tasks, reports back.

Safety rule: if the two bots exchange more than MAX_AUTO_LOOPS messages
without a human reply, the Architect pauses and asks the user for permission
to continue.
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
from orchestrator.engine import ask_gemini, run_claude_code

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Safety counter ────────────────────────────────────────────────────────────
MAX_AUTO_LOOPS = 3
loop_counter = 0          # incremented on every bot-to-bot exchange
awaiting_human = False    # True while paused waiting for user permission


def _increment_loop(builder_app: Application) -> bool:
    """
    Increment the autonomous loop counter.
    Returns True if the safety limit has been reached.
    """
    global loop_counter, awaiting_human
    loop_counter += 1
    logger.info("Auto-loop count: %d / %d", loop_counter, MAX_AUTO_LOOPS)
    if loop_counter >= MAX_AUTO_LOOPS and not awaiting_human:
        awaiting_human = True
        return True
    return False


def _reset_loop():
    global loop_counter, awaiting_human
    loop_counter = 0
    awaiting_human = False


# ── Architect handlers ────────────────────────────────────────────────────────

async def architect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Architect online. Send me a task and I will coordinate with the Builder."
    )


async def architect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point for user → Architect messages.
    The Architect consults Gemini and forwards a task to the Builder.
    """
    global awaiting_human, loop_counter

    user_prompt = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Human has replied — reset the safety counter
    if awaiting_human:
        _reset_loop()
        await update.message.reply_text(
            "Thank you. Resuming autonomous operation."
        )

    await update.message.reply_text("Consulting Gemini CLI…")

    try:
        architect_plan = ask_gemini(
            f"You are a software architect. Given this task, produce a concise, "
            f"step-by-step implementation plan for a developer:\n\n{user_prompt}"
        )
    except RuntimeError as e:
        await update.message.reply_text(f"Gemini error: {e}")
        return

    await update.message.reply_text(f"Architect plan:\n\n{architect_plan}")

    # Forward task to the Builder bot via stored reference
    builder_app: Application = context.bot_data["builder_app"]
    await builder_app.bot.send_message(
        chat_id=chat_id,
        text=f"[TASK FROM ARCHITECT]\n\n{architect_plan}",
    )
    context.bot_data["last_chat_id"] = chat_id


async def architect_critique(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    builder_report: str,
    chat_id: int,
):
    """
    Called programmatically when the Builder finishes a task.
    Architect critiques the work and issues Fix or Next Step.
    """
    await context.bot.send_message(
        chat_id=chat_id,
        text="Architect reviewing Builder output…",
    )

    try:
        critique = ask_gemini(
            f"You are a senior software architect performing a code review. "
            f"Assess this implementation report and respond with EITHER:\n"
            f"  'Fix: <specific issue>' if there is a problem\n"
            f"  'Next Step: <what to do next>' if the work is acceptable.\n\n"
            f"Builder report:\n{builder_report}"
        )
    except RuntimeError as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Gemini error: {e}")
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Architect verdict:\n\n{critique}",
    )

    # Safety check before issuing the next autonomous command
    limit_reached = _increment_loop(context.application)
    if limit_reached:
        await context.bot.send_message(
            chat_id=MY_TELEGRAM_ID,
            text=(
                f"⚠️ Auto-loop limit ({MAX_AUTO_LOOPS}) reached.\n\n"
                f"Last Architect verdict:\n{critique}\n\n"
                "Reply to the Architect bot to approve and continue."
            ),
        )
        return

    # Forward the verdict to the Builder
    builder_app: Application = context.bot_data["builder_app"]
    await builder_app.bot.send_message(
        chat_id=chat_id,
        text=f"[ARCHITECT DIRECTIVE]\n\n{critique}",
    )


# ── Builder handlers ──────────────────────────────────────────────────────────

async def builder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Builder online. Awaiting tasks from the Architect.")


async def builder_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receives directives from the Architect (or user) and executes them
    via the claude-code CLI.
    """
    directive = update.message.text.strip()
    chat_id = update.effective_chat.id

    await update.message.reply_text("Running claude-code CLI…")

    try:
        report = run_claude_code(directive)
    except RuntimeError as e:
        await update.message.reply_text(f"Claude Code error: {e}")
        return

    await update.message.reply_text(f"Builder report:\n\n{report}")

    # Hand report back to the Architect for critique
    architect_app: Application = context.bot_data["architect_app"]
    await architect_critique(
        update=update,
        context=architect_app,  # use architect app context for Gemini calls
        builder_report=report,
        chat_id=chat_id,
    )


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def build_architect_app() -> Application:
    app = Application.builder().token(ARCHITECT_TOKEN).build()
    app.add_handler(CommandHandler("start", architect_start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, architect_message)
    )
    return app


def build_builder_app() -> Application:
    app = Application.builder().token(BUILDER_TOKEN).build()
    app.add_handler(CommandHandler("start", builder_start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, builder_message)
    )
    return app


async def main():
    architect_app = build_architect_app()
    builder_app = build_builder_app()

    # Cross-wire the apps so each can send messages through the other
    architect_app.bot_data["builder_app"] = builder_app
    builder_app.bot_data["architect_app"] = architect_app

    logger.info("Starting Architect and Builder bots…")

    async with architect_app, builder_app:
        await architect_app.start()
        await builder_app.start()

        await asyncio.gather(
            architect_app.updater.start_polling(drop_pending_updates=True),
            builder_app.updater.start_polling(drop_pending_updates=True),
        )

        # Run until interrupted
        await asyncio.Event().wait()

        await architect_app.updater.stop()
        await builder_app.updater.stop()
        await architect_app.stop()
        await builder_app.stop()


if __name__ == "__main__":
    asyncio.run(main())
