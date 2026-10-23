"""Read the local webhook without exposing it through the desktop API."""
from pathlib import Path
from dotenv import dotenv_values


def local_webhook(root: Path) -> str:
    for name in ('.env.discord', '.env.automation', '.env'):
        value = dotenv_values(root / name).get('DISCORD_WEBHOOK_URL')
        if value:
            return value
    return ''
