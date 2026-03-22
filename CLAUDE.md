# Project Roles

## Architect: @Gemini
Responsible for high-level design, system architecture, and technical decisions.
Runs via the **Gemini CLI** (`gemini ask`) — authenticated through `gemini login`, no API key required.

## Builder: @Claude
Responsible for implementation, writing code, and executing on the architecture defined by @Gemini.
Runs via the **Claude Code CLI** (`claude`) — authenticated locally.

---

# Project Overview

A Python-based **Dual-Bot Autonomous Orchestrator** running on Telegram.
Two separate bots (Architect + Builder) run in a single process using `asyncio.gather`.
They collaborate autonomously, with a safety circuit breaker that halts after 3 exchanges and asks the human for permission to continue.

## Architecture

### Bot Flow
```
User → @Architect bot
         └─ gemini ask "<task>"  (Gemini CLI, free tier)
         └─ forwards plan → @Builder bot
                              └─ claude "<instruction>"  (Claude Code CLI)
                              └─ reports back → @Architect bot
                                                 └─ gemini ask "<critique>"
                                                 └─ issues "Fix:" or "Next Step:" → @Builder
                                                 └─ [loop_counter >= 3] → pauses, asks @User
```

### Safety Circuit Breaker
- `loop_counter` tracks autonomous bot-to-bot exchanges
- Limit: **3 exchanges** without human input
- On limit: Architect messages `MY_TELEGRAM_ID` directly and halts until the user replies

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ARCHITECT_TOKEN` | Telegram bot token for the Architect bot (@BotFather) |
| `BUILDER_TOKEN` | Telegram bot token for the Builder bot (@BotFather) |
| `MY_TELEGRAM_ID` | Your personal Telegram user ID (get from @userinfobot) |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude operations |

Copy `.env.template` → `.env` and populate before running.

## Directory Structure

```
prompt-and-pray/
├── bot/
│   ├── __init__.py
│   ├── main.py           # Dual-bot orchestrator (asyncio.gather)
│   └── handlers/
│       └── __init__.py
├── orchestrator/
│   ├── __init__.py
│   └── engine.py         # ask_gemini() + run_claude_code() via subprocess
├── agents/
│   └── __init__.py
├── config/
│   ├── __init__.py
│   └── settings.py       # Loads ARCHITECT_TOKEN, BUILDER_TOKEN, MY_TELEGRAM_ID
├── utils/
│   └── __init__.py
├── tests/
│   └── __init__.py
├── venv/                 # Local Python virtualenv (not committed)
├── .env                  # Secrets (not committed)
├── .env.template         # Template for required env vars
├── .gitignore
├── CLAUDE.md
├── requirements.txt
└── README.md
```

## Dependencies

```
python-telegram-bot[ext]
python-dotenv
pyyaml
```

Install: `pip install -r requirements.txt`

## Running

```bash
cp .env.template .env
# fill in .env values
python -m bot.main
```
