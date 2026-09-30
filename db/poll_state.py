from .connection import get_connection


def get_last_history_id() -> str | None:
    with get_connection() as conn:
        row = conn.execute("select last_history_id from poll_state where id = 1").fetchone()
        return row[0] if row else None


def set_last_history_id(history_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            insert into poll_state (id, last_history_id, updated_at)
            values (1, %s, now())
            on conflict (id) do update
                set last_history_id = excluded.last_history_id,
                    updated_at = now()
            """,
            (history_id,),
        )
        conn.commit()


def mark_processed(message_ids: list[str]) -> None:
    if not message_ids:
        return
    with get_connection() as conn:
        conn.executemany(
            "insert into processed_messages (gmail_message_id) values (%s) "
            "on conflict (gmail_message_id) do nothing",
            [(mid,) for mid in message_ids],
        )
        conn.commit()


def filter_unprocessed(message_ids: list[str]) -> list[str]:
    if not message_ids:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "select gmail_message_id from processed_messages where gmail_message_id = any(%s)",
            (message_ids,),
        ).fetchall()
        already_processed = {row[0] for row in rows}
    return [mid for mid in message_ids if mid not in already_processed]
