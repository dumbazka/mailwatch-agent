import asyncio
import functools
import logging

import inngest

from config import settings
from db.poll_state import filter_unprocessed, get_last_history_id, mark_processed, set_last_history_id
from gmail.auth import get_gmail_service
from gmail.client import fetch_new_messages, get_current_history_id
from pipeline import process_message

logger = logging.getLogger(__name__)

inngest_client = inngest.Inngest(
    app_id="mailwatch-agent",
    event_key=settings.inngest_event_key or None,
    signing_key=settings.inngest_signing_key or None,
    # Without this, the SDK defaults to Cloud mode and rejects the local
    # `inngest dev` server's unsigned requests. Cloud mode kicks in once
    # INNGEST_SIGNING_KEY is set (Railway/production).
    is_production=bool(settings.inngest_signing_key),
)


async def _to_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)


@inngest_client.create_function(
    fn_id="poll-gmail",
    trigger=inngest.TriggerCron(cron=f"*/{settings.poll_interval_minutes} * * * *"),
)
async def poll_gmail(ctx: inngest.Context) -> dict:
    service = await asyncio.to_thread(get_gmail_service)

    last_history_id = await ctx.step.run(
        "get-last-history-id", functools.partial(_to_thread, get_last_history_id)
    )

    if last_history_id is None:
        # First-ever run: record a baseline instead of backfilling the whole mailbox.
        history_id = await ctx.step.run(
            "set-initial-baseline", functools.partial(_to_thread, get_current_history_id, service)
        )
        await ctx.step.run(
            "save-history-id", functools.partial(_to_thread, set_last_history_id, history_id)
        )
        return {"status": "initialized", "history_id": history_id}

    message_ids, new_history_id = await ctx.step.run(
        "fetch-new-messages", functools.partial(_to_thread, fetch_new_messages, service, last_history_id)
    )

    unprocessed_ids = await ctx.step.run(
        "filter-already-processed", functools.partial(_to_thread, filter_unprocessed, message_ids)
    )

    for message_id in unprocessed_ids:
        await ctx.step.run(f"process-{message_id}", functools.partial(process_message, message_id))

    await ctx.step.run(
        "mark-processed", functools.partial(_to_thread, mark_processed, unprocessed_ids)
    )
    await ctx.step.run(
        "save-history-id", functools.partial(_to_thread, set_last_history_id, new_history_id)
    )

    return {
        "status": "ok",
        "new_messages": len(unprocessed_ids),
        "history_id": new_history_id,
    }
