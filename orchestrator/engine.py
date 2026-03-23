import subprocess


def ask_gemini(prompt: str) -> str:
    """
    Send a prompt to Gemini via the authenticated CLI.
    Uses `gemini ask "<prompt>"` — no API key required.
    Relies on the user being logged in via `gemini login`.
    """
    result = subprocess.run(
        ["gemini", "ask", prompt],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown error from Gemini CLI"
        raise RuntimeError(f"Gemini CLI error: {error}")

    return result.stdout.strip()


def run_claude_code(instruction: str) -> str:
    """
    Execute a coding instruction via the claude-code CLI.
    Uses `claude -p "<instruction>"` (print mode — non-interactive, returns output).
    Relies on `claude` being installed and authenticated.
    """
    result = subprocess.run(
        ["claude", "-p", instruction],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown error from Claude Code CLI"
        raise RuntimeError(f"Claude Code CLI error: {error}")

    return result.stdout.strip()
