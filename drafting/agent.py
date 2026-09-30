import logging

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

INSTRUCTIONS = """You are drafting email replies on behalf of Azka, who will
review and approve every draft before it's sent — you are never sending mail
directly. Write a short, polite, professional reply to the email given to you.
Match the tone of the original message. Do not invent facts, commitments,
dates, or prices that aren't in the original email — if specifics are needed,
write a reply that acknowledges the message and says Azka will follow up with
details. Output only the reply body text: no subject line, no preamble, no
explanation of what you wrote."""


class DraftDecision(BaseModel):
    should_reply: bool
    reason: str
    suggested_keyword: str | None = None
    draft: str


DECISION_INSTRUCTIONS = """You triage and draft replies for Azka's personal
Gmail inbox. Azka reviews and approves every draft before anything sends —
you are never sending mail directly.

For the email given to you, decide whether it is genuine personal/business
correspondence that deserves a human-reviewed reply, or automated mail that
doesn't: newsletters, job alerts, social/platform notifications, receipts,
digests, marketing, or anything a bot sent that won't read a reply.

Always write `draft`: a short, polite, professional reply, even when
should_reply is false — Azka may choose to send it anyway. Match the tone of
the original message. Never invent facts, commitments, dates, or prices not
in the original email — if specifics are needed, acknowledge the message and
say Azka will follow up with details.

If should_reply is false because this looks like a recurring type of
automated mail, set suggested_keyword to one short, generic, lowercase
phrase from the subject or sender name that would catch similar future
emails (e.g. "job alert", "weekly digest") — this gets added to a blocklist,
so keep it specific enough that it won't also match real correspondence.
Otherwise leave suggested_keyword null.

Set reason to one short sentence explaining the should_reply decision."""


def _build_agent() -> Agent:
    return Agent(name="reply_drafter", model=settings.gemini_model, instruction=INSTRUCTIONS)


def _build_decision_agent() -> Agent:
    return Agent(
        name="reply_triage_and_drafter",
        model=settings.gemini_model,
        instruction=DECISION_INSTRUCTIONS,
        output_schema=DraftDecision,
    )


def _email_prompt(sender: str, subject: str, body: str) -> str:
    return f"From: {sender}\nSubject: {subject}\n\n{body}"


def _prompt(sender: str, subject: str, body: str, previous_draft: str | None) -> str:
    parts = [f"From: {sender}", f"Subject: {subject}", "", body]
    if previous_draft:
        parts += [
            "",
            "---",
            "A previous draft reply was rejected as unsatisfactory. Write a "
            "meaningfully different reply, not a small rewording of it:",
            previous_draft,
        ]
    return "\n".join(parts)


async def _run_once(agent: Agent, prompt: str) -> str:
    runner = InMemoryRunner(agent=agent)
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="mailwatch"
    )
    content = types.Content(role="user", parts=[types.Part(text=prompt)])

    text = ""
    async for event in runner.run_async(
        user_id="mailwatch", session_id=session.id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts)

    return text.strip()


async def draft_reply(
    sender: str, subject: str, body: str, previous_draft: str | None = None
) -> str:
    return await _run_once(_build_agent(), _prompt(sender, subject, body, previous_draft))


async def decide_and_draft(sender: str, subject: str, body: str) -> DraftDecision:
    """One LLM call that both drafts a reply and judges whether one is even
    warranted — a safety net for automated mail the cheap heuristic filters
    (category/header/keyword checks in filters/rules.py) didn't catch."""
    raw = await _run_once(_build_decision_agent(), _email_prompt(sender, subject, body))
    try:
        return DraftDecision.model_validate_json(raw)
    except Exception:
        # Fail open: an unparseable response still gets drafted and shown to
        # Azka for approval, rather than silently dropping a possibly-real email.
        logger.warning("Could not parse structured triage output, failing open: %r", raw)
        return DraftDecision(
            should_reply=True, reason="fallback: unparseable model output", draft=raw
        )
