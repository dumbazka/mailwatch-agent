import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str

    google_oauth_client_secrets_file: str
    google_oauth_token_file: str

    gemini_api_key: str
    gemini_model: str

    discord_bot_token: str
    discord_confirmation_channel_id: str
    discord_reminders_channel_id: str

    inngest_event_key: str
    inngest_signing_key: str

    poll_interval_minutes: int


def _load() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        google_oauth_client_secrets_file=os.environ.get(
            "GOOGLE_OAUTH_CLIENT_SECRETS_FILE", "credentials/gmail_oauth_client.json"
        ),
        google_oauth_token_file=os.environ.get(
            "GOOGLE_OAUTH_TOKEN_FILE", "credentials/gmail_token.json"
        ),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        discord_bot_token=os.environ.get("DISCORD_BOT_TOKEN", ""),
        discord_confirmation_channel_id=os.environ.get("DISCORD_CONFIRMATION_CHANNEL_ID", ""),
        discord_reminders_channel_id=os.environ.get("DISCORD_REMINDERS_CHANNEL_ID", ""),
        inngest_event_key=os.environ.get("INNGEST_EVENT_KEY", ""),
        inngest_signing_key=os.environ.get("INNGEST_SIGNING_KEY", ""),
        poll_interval_minutes=int(os.environ.get("POLL_INTERVAL_MINUTES", "5")),
    )


settings = _load()

# google-adk / google-genai read the API key from this env var by default.
if settings.gemini_api_key:
    os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
