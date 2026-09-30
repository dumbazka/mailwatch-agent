import logging

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


def get_current_history_id(service) -> str:
    """Baseline history ID for the mailbox right now (used on first-ever poll)."""
    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]


def fetch_new_messages(service, start_history_id: str) -> tuple[list[str], str]:
    """Return (new_message_ids, new_history_id) for everything added since start_history_id.

    Paginates through history.list so nothing is missed even when far more than
    one page's worth of messages arrived between polls.
    """
    new_message_ids: list[str] = []
    seen = set()
    page_token = None
    latest_history_id = start_history_id

    while True:
        try:
            # labelId="INBOX" keeps this to incoming mail only — otherwise
            # messageAdded also fires for our own outgoing replies (Sent).
            resp = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as e:
            if e.resp.status == 404:
                # startHistoryId too old / expired. Reset the baseline; anything
                # added between the last successful poll and now is missed once,
                # but polling resumes cleanly from here.
                logger.warning(
                    "Gmail history ID %s expired; resetting baseline.", start_history_id
                )
                new_history_id = get_current_history_id(service)
                return [], new_history_id
            raise

        for record in resp.get("history", []):
            for added in record.get("messagesAdded", []):
                message_id = added["message"]["id"]
                if message_id not in seen:
                    seen.add(message_id)
                    new_message_ids.append(message_id)

        latest_history_id = resp.get("historyId", latest_history_id)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return new_message_ids, latest_history_id


def get_message(service, message_id: str) -> dict:
    """Full message resource, used for classification + drafting in later phases."""
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()
