import functools
import json
import logging
import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from config import settings

logger = logging.getLogger(__name__)

# readonly: poll + read message content for classification/drafting
# send: send the approved reply
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _load_token() -> Credentials | None:
    if settings.google_oauth_token_json:
        return Credentials.from_authorized_user_info(
            json.loads(settings.google_oauth_token_json), SCOPES
        )
    token_file = settings.google_oauth_token_file
    if os.path.exists(token_file):
        return Credentials.from_authorized_user_file(token_file, SCOPES)
    return None


def _save_token(creds: Credentials) -> None:
    if settings.google_oauth_token_json:
        # Env-var-based (production): nothing to write back to. A refreshed
        # access_token just lives for this process's lifetime; if the
        # refresh_token itself ever needs replacing (e.g. the 7-day expiry
        # on an unverified app), redo the local consent flow and update the
        # GOOGLE_OAUTH_TOKEN_JSON env var on the host.
        return
    token_file = settings.google_oauth_token_file
    os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
    with open(token_file, "w") as f:
        f.write(creds.to_json())


def _load_credentials() -> Credentials:
    creds = _load_token()

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Common on an unverified ("Testing") OAuth app: Google expires the
            # refresh token after 7 days. Drop the stale token and fall through
            # to a fresh interactive consent below.
            logger.warning(
                "Gmail OAuth token was rejected on refresh (expired/revoked). "
                "Re-running the interactive consent flow — a browser window will open."
            )
            if not settings.google_oauth_token_json and os.path.exists(
                settings.google_oauth_token_file
            ):
                os.remove(settings.google_oauth_token_file)
            creds = None

    if not creds or not creds.valid:
        # First-time setup: opens a browser for the interactive OAuth consent
        # screen. Only works where a browser is reachable (local dev) — a
        # deployed server has no browser, which is why GOOGLE_OAUTH_TOKEN_JSON
        # exists: do this step locally once, then paste the result there.
        if settings.google_oauth_client_secrets_json:
            flow = InstalledAppFlow.from_client_config(
                json.loads(settings.google_oauth_client_secrets_json), SCOPES
            )
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.google_oauth_client_secrets_file, SCOPES
            )
        creds = flow.run_local_server(port=0)
        _save_token(creds)

    return creds


@functools.lru_cache(maxsize=1)
def get_gmail_service() -> Resource:
    creds = _load_credentials()
    return build("gmail", "v1", credentials=creds)
