import os
from dotenv import load_dotenv

load_dotenv()

ARCHITECT_TOKEN = os.getenv("ARCHITECT_TOKEN")
BUILDER_TOKEN = os.getenv("BUILDER_TOKEN")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID", "0"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

for name, val in [
    ("ARCHITECT_TOKEN", ARCHITECT_TOKEN),
    ("BUILDER_TOKEN", BUILDER_TOKEN),
    ("MY_TELEGRAM_ID", MY_TELEGRAM_ID),
]:
    if not val:
        raise ValueError(f"{name} is not set in the environment.")
