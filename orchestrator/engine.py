import subprocess


class GeminiEngine:
    """Wraps the local `gemini` CLI for non-interactive prompt/response use."""

    def ask(self, prompt: str) -> str:
        """
        Run `gemini ask "<prompt>"` and return stdout.
        Raises RuntimeError if the CLI exits non-zero.
        Relies on `gemini login` having been run beforehand.
        """
        try:
            output = subprocess.check_output(
                ["gemini", "ask", prompt],
                stderr=subprocess.PIPE,
                text=True,
            )
            return output.strip()
        except subprocess.CalledProcessError as e:
            error = e.stderr.strip() or "Unknown error from Gemini CLI"
            raise RuntimeError(f"Gemini CLI error: {error}") from e


class ClaudeEngine:
    """Wraps the local `claude` CLI for non-interactive prompt/response use."""

    def run(self, instruction: str) -> str:
        """
        Run `claude -p "<instruction>"` and return stdout.
        -p = print mode: non-interactive, exits after one response.
        Raises RuntimeError if the CLI exits non-zero.
        """
        try:
            output = subprocess.check_output(
                ["claude", "-p", instruction],
                stderr=subprocess.PIPE,
                text=True,
            )
            return output.strip()
        except subprocess.CalledProcessError as e:
            error = e.stderr.strip() or "Unknown error from Claude CLI"
            raise RuntimeError(f"Claude CLI error: {error}") from e


# Module-level singletons — import these in bot/main.py
gemini = GeminiEngine()
claude = ClaudeEngine()
