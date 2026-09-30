import logging

import inngest

from config import settings
from db.poll_state import filter_unprocessed, get_last_history_id, mark_processed, set_last_history_id
from gmail import fetch_new_messages, get_gmail_service
from gmail.client import get_current_history_id

logger = logging.getLogger(__name__)

inngest_client = inngest.Inngest(
    app_id="mailwatch-agent",
    event_key=settings.inngest_event_key or None,
    signing_key=settings.inngest_signing_key or None,
)


@inngest_client.create_function(
    fn_id="poll-gmail",
    trigger=inngest.TriggerCron(cron=f"*/{settings.poll_interval_minutes} * * * *"),
)
async def poll_gmail(ctx: inngest.Context) -> dict:
    service = get_gmail_service()

    last_history_id = await ctx.step.run("get-last-history-id", get_last_history_id)

    if last_history_id is None:
        # First-ever run: record a baseline instead of backfilling the whole mailbox.
        history_id = await ctx.step.run(
            "set-initial-baseline", lambda: get_current_history_id(service)
        )
        await ctx.step.run("save-history-id", lambda: set_last_history_id(history_id))
        return {"status": "initialized", "history_id": history_id}

    def _fetch():
        return fetch_new_messages(service, last_history_id)

    message_ids, new_history_id = await ctx.step.run("fetch-new-messages", _fetch)

    unprocessed_ids = await ctx.step.run(
        "filter-already-processed", lambda: filter_unprocessed(message_ids)
    )

    # Phase 2+ hook: classify/filter, draft, and post to Discord for each
    # unprocessed message. For now, just record them as processed so the next
    # poll doesn't see them again.
    await ctx.step.run("mark-processed", lambda: mark_processed(unprocessed_ids))
    await ctx.step.run("save-history-id", lambda: set_last_history_id(new_history_id))

    return {
        "status": "ok",
        "new_messages": len(unprocessed_ids),
        "history_id": new_history_id,
    }
