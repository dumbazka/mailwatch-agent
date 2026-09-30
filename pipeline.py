import asyncio
import logging

from db.pending_approvals import create_pending_approval
from drafting.agent import draft_reply
from filters.rules import classify_message
from gmail.auth import get_gmail_service
from gmail.client import get_message
from gmail.parsing import get_excerpt, get_plain_text_body, get_sender, get_subject

logger = logging.getLogger(__name__)


async def process_message(message_id: str, force: bool = False) -> str | None:
    """Classify, draft, and post one Gmail message to Discord for approval.

    Returns the new pending_approval id, or None if the message was filtered
    out. `force=True` (used by the Discord "Re-run" button) skips filtering.
    """
    # This process shares one event loop with the Discord bot (see main.py),
    # so every blocking network/DB call here has to run off-thread or it
    # freezes the Discord gateway heartbeat.
    service = await asyncio.to_thread(get_gmail_service)
    message = await asyncio.to_thread(get_message, service, message_id)

    classification = await asyncio.to_thread(classify_message, message)
    if not classification.should_draft and not force:
        logger.info("Skipping %s: %s", message_id, classification.reason)
        return None

    sender, _ = get_sender(message)
    subject = get_subject(message)
    body = get_plain_text_body(message)
    excerpt = get_excerpt(message)

    draft = await draft_reply(sender, subject, body)
    pending_id = await asyncio.to_thread(
        create_pending_approval, message_id, sender, subject, excerpt, draft
    )

    # Local import: discord_bot.bot also imports this module (for Re-run), so
    # importing it at module load time here would create a circular import.
    from discord_bot.bot import post_pending_approval

    await post_pending_approval(pending_id)
    return pending_id
