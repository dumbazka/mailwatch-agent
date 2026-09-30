import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from config import settings

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
        creds.refresh(Request())

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


def get_gmail_service() -> Resource:
    creds = _load_credentials()
    return build("gmail", "v1", credentials=creds)
