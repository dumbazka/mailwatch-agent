from .connection import get_connection


def record_sent(gmail_message_id: str, sent_text: str, sent_via: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "insert into sent_replies (gmail_message_id, sent_text, sent_via) values (%s, %s, %s)",
            (gmail_message_id, sent_text, sent_via),
        )
        conn.commit()
