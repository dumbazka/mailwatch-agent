import base64
from email.utils import parseaddr


def get_header(message: dict, name: str) -> str | None:
    headers = message.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return None


def get_sender(message: dict) -> tuple[str, str]:
    """Returns (address, domain), both lowercased."""
    _, address = parseaddr(get_header(message, "From") or "")
    address = address.lower()
    domain = address.split("@")[-1] if "@" in address else ""
    return address, domain


def get_subject(message: dict) -> str:
    return get_header(message, "Subject") or "(no subject)"


def get_excerpt(message: dict, max_len: int = 300) -> str:
    return message.get("snippet", "")[:max_len]


def has_list_unsubscribe(message: dict) -> bool:
    return get_header(message, "List-Unsubscribe") is not None


def get_categories(message: dict) -> set[str]:
    return set(message.get("labelIds", []))


def _leaf_parts(payload: dict):
    if payload.get("parts"):
        for part in payload["parts"]:
            yield from _leaf_parts(part)
    else:
        yield payload


def get_plain_text_body(message: dict, max_len: int = 6000) -> str:
    payload = message.get("payload", {})
    for part in _leaf_parts(payload):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                return text[:max_len]
    # No plain-text part (e.g. HTML-only mail) — fall back to Gmail's own snippet.
    return message.get("snippet", "")[:max_len]
