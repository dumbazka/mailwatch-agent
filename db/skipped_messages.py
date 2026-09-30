from .connection import get_connection


def record_skip(
    gmail_message_id: str, sender: str, subject: str, reason: str, skipped_by: str
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            insert into skipped_messages (gmail_message_id, sender, subject, reason, skipped_by)
            values (%s, %s, %s, %s, %s)
            """,
            (gmail_message_id, sender, subject, reason, skipped_by),
        )
        conn.commit()
