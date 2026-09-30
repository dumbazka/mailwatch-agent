import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from config import settings
from db.pending_approvals import (
    get_due_reminders,
    get_expired,
    get_pending,
    get_pending_by_discord_message,
    set_discord_message_id,
    set_last_reminder,
    set_status,
    update_draft,
)
from db.sender_rules import add_sender_rule
from db.sent_replies import record_sent
from drafting.agent import draft_reply
from gmail.auth import get_gmail_service
from gmail.client import get_message
from gmail.parsing import get_plain_text_body
from gmail.send import send_reply

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def _build_embed(pending: dict, status_note: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=pending["subject"] or "(no subject)",
        description=pending["draft_text"],
        color=discord.Color.blurple(),
    )
    embed.add_field(name="From", value=pending["sender"], inline=False)
    embed.add_field(name="Original excerpt", value=pending["excerpt"] or "—", inline=False)
    if status_note:
        embed.set_footer(text=status_note)
    else:
        embed.set_footer(text=f"Expires {pending['expires_at']:%Y-%m-%d %H:%M UTC}")
    return embed


async def _send_and_finalize(
    interaction: discord.Interaction,
    pending: dict,
    message: discord.Message,
    text: str,
    sent_via: str,
) -> None:
    service = await asyncio.to_thread(get_gmail_service)
    original = await asyncio.to_thread(get_message, service, pending["gmail_message_id"])
    await asyncio.to_thread(send_reply, service, original, text)

    await asyncio.to_thread(record_sent, pending["gmail_message_id"], text, sent_via)
    await asyncio.to_thread(set_status, pending["id"], "sent")

    updated = await asyncio.to_thread(get_pending, pending["id"])
    await message.edit(embed=_build_embed(updated, status_note=f"Sent by Azka ({sent_via})"), view=None)

    if interaction.response.is_done():
        await interaction.followup.send("Sent.", ephemeral=True)
    else:
        await interaction.response.send_message("Sent.", ephemeral=True)


class ScopeChoiceView(discord.ui.View):
    """Ephemeral follow-up asking whether a sender rule applies to the address or the whole domain."""

    def __init__(self, pending: dict, rule_type: str):
        super().__init__(timeout=60)
        self.pending = pending
        self.rule_type = rule_type

    @discord.ui.button(label="This address only", style=discord.ButtonStyle.secondary)
    async def address_scope(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._apply(interaction, "address")

    @discord.ui.button(label="Whole domain", style=discord.ButtonStyle.secondary)
    async def domain_scope(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._apply(interaction, "domain")

    async def _apply(self, interaction: discord.Interaction, scope: str) -> None:
        value = self.pending["sender"]
        if scope == "domain":
            value = value.split("@")[-1]
        await asyncio.to_thread(add_sender_rule, scope, value, self.rule_type)
        label = "always-skip" if self.rule_type == "always_skip" else "always-draft"
        await interaction.response.edit_message(
            content=f"Marked `{value}` as {label} ({scope}-level).", view=None
        )


class ReplyTextModal(discord.ui.Modal, title="Reply with custom text"):
    reply_text = discord.ui.TextInput(
        label="Reply text", style=discord.TextStyle.paragraph, max_length=4000
    )

    def __init__(self, pending: dict, message: discord.Message):
        super().__init__()
        self.pending = pending
        self.message = message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await _send_and_finalize(
            interaction, self.pending, self.message, str(self.reply_text), sent_via="custom_text"
        )


class ApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="mailwatch:approve")
    async def approve(self, interaction: discord.Interaction, _button: discord.ui.Button):
        pending = await asyncio.to_thread(get_pending_by_discord_message, str(interaction.message.id))
        if not pending or pending["status"] != "pending":
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return
        await interaction.response.defer()
        await _send_and_finalize(
            interaction, pending, interaction.message, pending["draft_text"], sent_via="approved_draft"
        )

    @discord.ui.button(label="Rewrite", style=discord.ButtonStyle.primary, custom_id="mailwatch:rewrite")
    async def rewrite(self, interaction: discord.Interaction, _button: discord.ui.Button):
        pending = await asyncio.to_thread(get_pending_by_discord_message, str(interaction.message.id))
        if not pending or pending["status"] != "pending":
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return
        await interaction.response.defer()

        service = await asyncio.to_thread(get_gmail_service)
        original = await asyncio.to_thread(get_message, service, pending["gmail_message_id"])
        body = get_plain_text_body(original)
        new_draft = await draft_reply(
            pending["sender"], pending["subject"], body, previous_draft=pending["draft_text"]
        )
        await asyncio.to_thread(update_draft, pending["id"], new_draft)

        updated = await asyncio.to_thread(get_pending, pending["id"])
        await interaction.message.edit(embed=_build_embed(updated), view=self)

    @discord.ui.button(
        label="Reply with text", style=discord.ButtonStyle.secondary, custom_id="mailwatch:reply_text"
    )
    async def reply_with_text(self, interaction: discord.Interaction, _button: discord.ui.Button):
        pending = await asyncio.to_thread(get_pending_by_discord_message, str(interaction.message.id))
        if not pending or pending["status"] != "pending":
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return
        await interaction.response.send_modal(ReplyTextModal(pending, interaction.message))

    @discord.ui.button(
        label="Always skip sender", style=discord.ButtonStyle.danger, custom_id="mailwatch:skip_sender"
    )
    async def always_skip(self, interaction: discord.Interaction, _button: discord.ui.Button):
        pending = await asyncio.to_thread(get_pending_by_discord_message, str(interaction.message.id))
        if not pending:
            await interaction.response.send_message("Couldn't find this item.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Always-skip `{pending['sender']}` — apply to just this address, or the whole domain?",
            view=ScopeChoiceView(pending, "always_skip"),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Always draft sender", style=discord.ButtonStyle.secondary, custom_id="mailwatch:draft_sender"
    )
    async def always_draft(self, interaction: discord.Interaction, _button: discord.ui.Button):
        pending = await asyncio.to_thread(get_pending_by_discord_message, str(interaction.message.id))
        if not pending:
            await interaction.response.send_message("Couldn't find this item.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Always-draft `{pending['sender']}` — apply to just this address, or the whole domain?",
            view=ScopeChoiceView(pending, "always_draft"),
            ephemeral=True,
        )


class ExpiredView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Re-run", style=discord.ButtonStyle.primary, custom_id="mailwatch:rerun")
    async def rerun(self, interaction: discord.Interaction, _button: discord.ui.Button):
        pending = await asyncio.to_thread(get_pending_by_discord_message, str(interaction.message.id))
        if not pending:
            await interaction.response.send_message("Couldn't find this item.", ephemeral=True)
            return
        await interaction.response.defer()

        import pipeline  # local import: pipeline imports this module too

        await pipeline.process_message(pending["gmail_message_id"], force=True)
        await interaction.message.edit(
            content="Re-run — a new item was posted above.", embed=None, view=None
        )


async def post_pending_approval(pending_id: str) -> None:
    await bot.wait_until_ready()
    pending = await asyncio.to_thread(get_pending, pending_id)
    channel_id = int(settings.discord_confirmation_channel_id)
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)

    message = await channel.send(embed=_build_embed(pending), view=ApprovalView())
    await asyncio.to_thread(set_discord_message_id, pending_id, str(message.id))


@tasks.loop(minutes=10)
async def reminder_and_expiry_loop():
    now = datetime.now(timezone.utc)

    confirmation_id = int(settings.discord_confirmation_channel_id)
    reminders_id = int(settings.discord_reminders_channel_id)
    confirmation_channel = bot.get_channel(confirmation_id) or await bot.fetch_channel(confirmation_id)
    reminders_channel = bot.get_channel(reminders_id) or await bot.fetch_channel(reminders_id)

    due_reminders = await asyncio.to_thread(get_due_reminders, now)
    for pending in due_reminders:
        await asyncio.to_thread(set_last_reminder, pending["id"], now)
        if pending["discord_message_id"]:
            link = (
                f"https://discord.com/channels/{confirmation_channel.guild.id}/"
                f"{confirmation_channel.id}/{pending['discord_message_id']}"
            )
            await reminders_channel.send(
                f"Reminder: **{pending['subject'] or '(no subject)'}** from {pending['sender']} "
                f"is still waiting for a decision. {link}"
            )

    expired = await asyncio.to_thread(get_expired, now)
    for pending in expired:
        await asyncio.to_thread(set_status, pending["id"], "expired")
        if not pending["discord_message_id"]:
            continue
        try:
            message = await confirmation_channel.fetch_message(int(pending["discord_message_id"]))
        except discord.NotFound:
            logger.warning("Expired item's Discord message %s not found", pending["discord_message_id"])
            continue
        await message.edit(
            embed=_build_embed(pending, status_note="Expired — no reply sent"), view=ExpiredView()
        )


@bot.event
async def on_ready():
    bot.add_view(ApprovalView())
    bot.add_view(ExpiredView())
    if not reminder_and_expiry_loop.is_running():
        reminder_and_expiry_loop.start()
    logger.info("Discord bot ready as %s", bot.user)
