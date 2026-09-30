import base64
from email.mime.text import MIMEText

from .parsing import get_header


def send_reply(service, original_message: dict, reply_text: str) -> None:
    to_addr = get_header(original_message, "From")
    subject = get_header(original_message, "Subject") or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    mime_msg = MIMEText(reply_text)
    mime_msg["To"] = to_addr
    mime_msg["Subject"] = subject

    message_id_header = get_header(original_message, "Message-ID")
    if message_id_header:
        mime_msg["In-Reply-To"] = message_id_header
        mime_msg["References"] = message_id_header

    body = {"raw": base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()}
    thread_id = original_message.get("threadId")
    if thread_id:
        body["threadId"] = thread_id

    service.users().messages().send(userId="me", body=body).execute()
