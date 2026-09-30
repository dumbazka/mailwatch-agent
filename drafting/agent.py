from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from config import settings

INSTRUCTIONS = """You are drafting email replies on behalf of Azka, who will
review and approve every draft before it's sent — you are never sending mail
directly. Write a short, polite, professional reply to the email given to you.
Match the tone of the original message. Do not invent facts, commitments,
dates, or prices that aren't in the original email — if specifics are needed,
write a reply that acknowledges the message and says Azka will follow up with
details. Output only the reply body text: no subject line, no preamble, no
explanation of what you wrote."""


def _build_agent() -> Agent:
    return Agent(name="reply_drafter", model=settings.gemini_model, instruction=INSTRUCTIONS)


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


async def draft_reply(
    sender: str, subject: str, body: str, previous_draft: str | None = None
) -> str:
    runner = InMemoryRunner(agent=_build_agent())
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="mailwatch"
    )
    content = types.Content(
        role="user", parts=[types.Part(text=_prompt(sender, subject, body, previous_draft))]
    )

    draft = ""
    async for event in runner.run_async(
        user_id="mailwatch", session_id=session.id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            draft = "".join(p.text or "" for p in event.content.parts)

    return draft.strip()
