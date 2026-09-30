import functools
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


def _load_credentials() -> Credentials:
    token_file = settings.google_oauth_token_file
    creds: Credentials | None = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

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
            os.remove(token_file)
            creds = None

    if not creds or not creds.valid:
        # First-time setup: opens a browser for the interactive OAuth consent screen.
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.google_oauth_client_secrets_file, SCOPES
        )
        creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds


@functools.lru_cache(maxsize=1)
def get_gmail_service() -> Resource:
    creds = _load_credentials()
    return build("gmail", "v1", credentials=creds)
