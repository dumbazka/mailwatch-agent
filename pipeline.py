import asyncio
import logging

from db.keyword_rules import add_keyword
from db.pending_approvals import (
    create_pending_approval,
    get_pending_by_gmail_message,
    reset_pending_approval,
)
from db.skipped_messages import record_skip
from drafting.agent import decide_and_draft
from filters.rules import classify_message
from gmail.auth import get_gmail_service
from gmail.client import get_message
from gmail.parsing import get_excerpt, get_plain_text_body, get_sender, get_subject

logger = logging.getLogger(__name__)


async def process_message(message_id: str, force: bool = False) -> str | None:
    """Classify, draft, and post one Gmail message to Discord for approval.

    Returns the new pending_approval id, or None if the message was skipped.
    `force=True` (used by the Discord "Re-run" button) skips both the
    heuristic filter and the LLM's reject option below.
    """
    # gmail_message_id is unique in pending_approvals. Inngest retries a step
    # that didn't report success in time even if it actually completed, so
    # this can be a second call for a message already fully handled — avoid
    # re-drafting/crashing on the resulting duplicate-key error. Re-run
    # (force=True) is the one case that's expected to hit an existing
    # (expired) row on purpose, and resets it instead of inserting.
    existing = await asyncio.to_thread(get_pending_by_gmail_message, message_id)
    if existing and existing["status"] == "sent" and not force:
        # Already approved and sent — never reopen it.
        return existing["id"]
    if existing and existing["status"] == "pending" and not force:
        # Already drafted; the crash (if any) may have happened before it got
        # posted, so still ensure it's posted — post_pending_approval is
        # itself a no-op if it already has a discord_message_id.
        from discord_bot.bot import post_pending_approval

        await post_pending_approval(existing["id"])
        return existing["id"]

    # This process shares one event loop with the Discord bot (see main.py),
    # so every blocking network/DB call here has to run off-thread or it
    # freezes the Discord gateway heartbeat.
    service = await asyncio.to_thread(get_gmail_service)
    message = await asyncio.to_thread(get_message, service, message_id)

    sender, _ = get_sender(message)
    subject = get_subject(message)

    # Cheap heuristic pass first (free) — also the reason a sender already on
    # the block list, or matching a known category/header/keyword, never
    # reaches the LLM call below at all.
    classification = await asyncio.to_thread(classify_message, message)
    if not classification.should_draft and not force:
        logger.info("Skipping %s: %s", message_id, classification.reason)
        await asyncio.to_thread(
            record_skip, message_id, sender, subject, classification.reason, "heuristic"
        )
        return None

    body = get_plain_text_body(message)
    excerpt = get_excerpt(message)

    # LLM-level safety net: heuristics can't enumerate every bulk sender, so
    # the same call that drafts the reply also judges whether one's
    # warranted. No extra cost — this replaces the old draft-only call.
    decision = await decide_and_draft(sender, subject, body)

    if not decision.should_reply and not force:
        logger.info("LLM skip for %s: %s", message_id, decision.reason)
        await asyncio.to_thread(record_skip, message_id, sender, subject, decision.reason, "llm")
        if decision.suggested_keyword:
            await asyncio.to_thread(add_keyword, decision.suggested_keyword)
        return None

    draft = decision.draft

    if existing:
        pending_id = await asyncio.to_thread(
            reset_pending_approval, existing["id"], sender, subject, excerpt, draft
        )
    else:
        pending_id = await asyncio.to_thread(
            create_pending_approval, message_id, sender, subject, excerpt, draft
        )

    # Local import: discord_bot.bot also imports this module (for Re-run), so
    # importing it at module load time here would create a circular import.
    from discord_bot.bot import post_pending_approval

    await post_pending_approval(pending_id)
    return pending_id
