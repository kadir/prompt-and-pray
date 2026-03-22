# Prompt-and-Pray
### The Dual-Agent Orchestrator

> *From chaos to structured multi-AI collaboration — controlled entirely from your phone.*

---

## Mission Statement

**Prompt-and-Pray** is an experiment in autonomous AI collaboration. Instead of talking to one AI, you talk to two — and they talk to each other.

The **Architect** (powered by Gemini CLI) designs. The **Builder** (powered by Claude Code) implements. You are the human in the loop: you give the Architect a goal, watch them work, and step in only when the system asks for your judgment. The entire workflow runs inside Telegram — no IDE, no terminal, no context switching. Just a prompt, a prayer, and a result.

---

## How It Works

```
You
 └─ send task → @Architect (Gemini CLI)
                  └─ produces implementation plan
                  └─ forwards plan → @Builder (Claude Code CLI)
                                      └─ executes changes via subprocess
                                      └─ reports back → @Architect
                                                         └─ critiques output
                                                         └─ issues "Fix:" or "Next Step:"
                                                         └─ [after 3 loops] pauses → asks You
```

The two bots run in a single Python process using `asyncio`. They are wired together directly — no message queue, no broker. When the autonomous loop exceeds **3 exchanges** without human input, the Architect stops and sends you a message asking for permission to continue.

---

## Technical Stack

| Layer | Technology |
|-------|-----------|
| Interface | Telegram (two bots via `python-telegram-bot`) |
| Architect | Gemini CLI (`gemini ask`) — free tier, authenticated via `gemini login` |
| Builder | Claude Code CLI (`claude`) — authenticated locally |
| Runtime | Python 3.11+, `asyncio` |
| Config | `python-dotenv`, `pyyaml` |
| Deployment | Docker (planned) |

---

## Directory Structure

```
prompt-and-pray/
├── bot/
│   ├── main.py           # Dual-bot orchestrator — asyncio.gather entry point
│   ├── __init__.py
│   └── handlers/
│       └── __init__.py
├── orchestrator/
│   ├── engine.py         # ask_gemini() + run_claude_code() via subprocess
│   └── __init__.py
├── agents/
│   └── __init__.py
├── config/
│   ├── settings.py       # Loads env vars: ARCHITECT_TOKEN, BUILDER_TOKEN, MY_TELEGRAM_ID
│   └── __init__.py
├── utils/
│   └── __init__.py
├── tests/
│   └── __init__.py
├── .env.template         # Required environment variable definitions
├── .gitignore
├── CLAUDE.md             # Roles, architecture, and contributor guide
├── requirements.txt
└── README.md
```

---

## Milestones

### Completed
- [x] Project scaffolded — full Python package structure
- [x] `.gitignore` configured (`.env`, `venv/`, `node_modules/`, `IMPLEMENTATION_CHECK.md`)
- [x] `CLAUDE.md` — role definitions for Architect and Builder
- [x] `.env.template` — `ARCHITECT_TOKEN`, `BUILDER_TOKEN`, `MY_TELEGRAM_ID`, `ANTHROPIC_API_KEY`
- [x] `config/settings.py` — environment loading with validation
- [x] `orchestrator/engine.py` — `ask_gemini()` and `run_claude_code()` via subprocess
- [x] `bot/main.py` — dual-bot asyncio orchestrator with Architect/Builder handlers
- [x] Safety circuit breaker — loop counter, human-permission gate at 3 exchanges
- [x] Dependencies installed — `python-telegram-bot[ext]`, `python-dotenv`, `pyyaml`

### Pending
- [ ] `bot/handlers/` — extract handlers into dedicated modules
- [ ] `config/settings.py` — YAML-based config support (pyyaml wired in)
- [ ] `tests/` — unit tests for engine and bot handlers
- [ ] Docker — `Dockerfile` and `docker-compose.yml` for self-hosted deployment
- [ ] `utils/` — shared logging and formatting helpers
- [ ] End-to-end test with real Telegram bot tokens

---

## Setup

```bash
# 1. Clone and enter
git clone https://github.com/your-org/prompt-and-pray.git
cd prompt-and-pray

# 2. Create virtualenv and install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.template .env
# Edit .env with your ARCHITECT_TOKEN, BUILDER_TOKEN, MY_TELEGRAM_ID

# 4. Authenticate CLIs
gemini login
# claude auth handled by Claude Code installation

# 5. Run
python -m bot.main
```

---

## Roles

See [CLAUDE.md](CLAUDE.md) for the full contributor guide.

| Role | Agent | Responsibility |
|------|-------|---------------|
| Architect | @Gemini | System design, planning, critique |
| Builder | @Claude | Implementation, code execution |
| Human | You | Goal-setting, approval, course correction |
