import re
import subprocess


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences that CLIs emit (colours, spinners, etc.)."""
    return re.sub(r"\x1b\[[0-9;]*[mGKHF]", "", text).strip()


class GeminiEngine:
    """Wraps the local `gemini` CLI for non-interactive prompt/response use."""

    def ask(self, prompt: str) -> str:
        """
        Run `gemini ask "<prompt>"` and return clean stdout.
        Raises RuntimeError if the CLI exits non-zero.
        Relies on `gemini login` having been run beforehand.
        """
        try:
            output = subprocess.check_output(
                ["gemini", "ask", prompt],
                stderr=subprocess.PIPE,
                text=True,
            )
            return _strip_ansi(output)
        except subprocess.CalledProcessError as e:
            error = _strip_ansi(e.stderr) or "Unknown error from Gemini CLI"
            raise RuntimeError(f"Gemini CLI error: {error}") from e


BUILDER_CONTAINER = "prompt-and-pray-container"


class ClaudeEngine:
    """
    Runs `claude -p` inside the Builder Docker container.

    The container mounts the host project directory at /project so Claude Code
    can read and write local files directly. All execution is sandboxed inside
    the container; the Python process only calls `docker exec`.
    """

    def run(self, instruction: str) -> str:
        """
        Execute: docker exec -w /project <container> claude -p "<instruction>"
        Returns the captured stdout (Claude's terminal output).
        Raises RuntimeError if docker or claude exits non-zero.
        """
        try:
            output = subprocess.check_output(
                [
                    "docker", "exec",
                    "-w", "/project",
                    BUILDER_CONTAINER,
                    "claude", "-p", instruction,
                ],
                stderr=subprocess.PIPE,
                text=True,
            )
            return _strip_ansi(output)
        except subprocess.CalledProcessError as e:
            error = _strip_ansi(e.stderr) or "Unknown error from Builder container"
            raise RuntimeError(f"Builder container error: {error}") from e


# Module-level singletons
gemini = GeminiEngine()
claude = ClaudeEngine()
