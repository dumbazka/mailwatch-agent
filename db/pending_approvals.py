from datetime import datetime, timedelta, timezone

from .connection import get_connection

APPROVAL_WINDOW = timedelta(hours=24)
REMINDER_INTERVAL = timedelta(hours=6)

_COLUMNS = (
    "id, gmail_message_id, discord_message_id, sender, subject, excerpt, "
    "draft_text, status, created_at, expires_at, last_reminder_at"
)
_KEYS = [c.strip() for c in _COLUMNS.split(",")]


def _row_to_dict(row) -> dict:
    d = dict(zip(_KEYS, row))
    d["id"] = str(d["id"])  # psycopg returns uuid.UUID; callers (incl. Inngest
    # step outputs, which must be JSON-serializable) expect a plain string.
    return d


def create_pending_approval(
    gmail_message_id: str, sender: str, subject: str, excerpt: str, draft_text: str
) -> str:
    expires_at = datetime.now(timezone.utc) + APPROVAL_WINDOW
    with get_connection() as conn:
        row = conn.execute(
            """
            insert into pending_approvals
                (gmail_message_id, sender, subject, excerpt, draft_text, expires_at)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (gmail_message_id, sender, subject, excerpt, draft_text, expires_at),
        ).fetchone()
        conn.commit()
        return str(row[0])


def get_pending_by_gmail_message(gmail_message_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"select {_COLUMNS} from pending_approvals where gmail_message_id = %s",
            (gmail_message_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def reset_pending_approval(
    pending_id: str, sender: str, subject: str, excerpt: str, draft_text: str
) -> str:
    """Re-open an existing (expired) row for a Re-run, instead of inserting a
    duplicate — gmail_message_id is unique, so a fresh insert would conflict."""
    expires_at = datetime.now(timezone.utc) + APPROVAL_WINDOW
    with get_connection() as conn:
        row = conn.execute(
            """
            update pending_approvals
            set sender = %s, subject = %s, excerpt = %s, draft_text = %s,
                status = 'pending', expires_at = %s, discord_message_id = null,
                last_reminder_at = null
            where id = %s
            returning id
            """,
            (sender, subject, excerpt, draft_text, expires_at, pending_id),
        ).fetchone()
        conn.commit()
        return str(row[0])


def set_discord_message_id(pending_id: str, discord_message_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "update pending_approvals set discord_message_id = %s where id = %s",
            (discord_message_id, pending_id),
        )
        conn.commit()


def get_pending(pending_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"select {_COLUMNS} from pending_approvals where id = %s", (pending_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_pending_by_discord_message(discord_message_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"select {_COLUMNS} from pending_approvals where discord_message_id = %s",
            (discord_message_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_draft(pending_id: str, draft_text: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "update pending_approvals set draft_text = %s where id = %s",
            (draft_text, pending_id),
        )
        conn.commit()


def set_status(pending_id: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "update pending_approvals set status = %s where id = %s", (status, pending_id)
        )
        conn.commit()


def set_last_reminder(pending_id: str, when: datetime) -> None:
    with get_connection() as conn:
        conn.execute(
            "update pending_approvals set last_reminder_at = %s where id = %s",
            (when, pending_id),
        )
        conn.commit()


def get_due_reminders(now: datetime) -> list[dict]:
    """Pending items whose next 6h reminder is due, and that haven't expired yet."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            select {_COLUMNS} from pending_approvals
            where status = 'pending'
              and expires_at > %s
              and coalesce(last_reminder_at, created_at) <= %s
            """,
            (now, now - REMINDER_INTERVAL),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_expired(now: datetime) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"select {_COLUMNS} from pending_approvals where status = 'pending' and expires_at <= %s",
            (now,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
