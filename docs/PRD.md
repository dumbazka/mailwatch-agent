# Gmail Auto-Reply Agent — PRD

Sep 30, 2026 · @Azka

## Overview

Azka currently checks Gmail manually and replies to every real message by hand, mixed in with newsletters and promotional mail that don't need a response. This project builds a Python service that watches a Gmail inbox, filters out newsletters/promotions automatically, drafts a reply for anything that looks like a real message, and sends that draft to Discord for a human decision before anything goes out — nothing is auto-sent.

Primary user: Azka. This is a personal project — used for Azka's own personal Gmail inbox, not a business/company account.

Repo name: `mailwatch-agent`.

## Goals and non-goals

**v1 goals**

- Poll Gmail on a schedule and classify each new message as a real email or newsletter/promo
- Draft a reply for real emails using Gemini
- Post the draft to a Discord channel with Approve, Rewrite, and custom-text-reply buttons
- Send the email only after Azka approves it in Discord
- Never touch newsletters/promotions — they're skipped entirely, no draft, no Discord message

**Non-goals for v1**

- No auto-send without human approval
- No outbound/cold-email or campaign sending
- No multi-account support (single Gmail inbox to start)
- No mobile app — Discord is the only control surface

## How it works end-to-end

&#91;embedded content: email pipeline · poll, classify, draft, approve\]

A scheduled poll pulls new Gmail messages, filters out newsletters/promotions, drafts a reply for anything real, and posts it to Discord — nothing sends until Azka approves it there.

## Discord approval spec

Each real email produces one Discord message, posted to a #confirmation channel: sender, subject, a short excerpt of the original email, and the drafted reply, followed by five buttons.

| Button | Action |
| --- | --- |
| Approve | Sends the drafted reply as-is via Gmail, marks the item done, edits the Discord message to show it was sent |
| Rewrite | Regenerates a new draft for the same email (asks Gemini to try again) and replaces the draft shown in the Discord message — buttons stay active for another round |
| Reply with text | Opens a text input (Discord modal) where Azka types a custom reply; on submit, that exact text is sent via Gmail instead of the drafted one |
| Always skip sender | Marks this sender (or its whole domain, Azka's choice) as always-skip going forward; future emails are filtered out automatically, no draft or Discord post |
| Always draft sender | Marks this sender (or its whole domain, Azka's choice) as always-draft; future emails always get a draft and a Discord post, even if a filter signal would otherwise skip them |

Only one action can be taken per item; once Approve or a custom text send completes, the buttons are disabled on that message.

If no action is taken within 24 hours, the item expires — no reply is sent automatically, and there's no automatic re-processing afterward. Azka has to manually re-trigger it (e.g. a Re-run command on the expired message in #confirmation) for the pipeline to draft and post it again. Starting 6 hours after posting, a reminder ping is sent every 6 hours (at 6h, 12h, and 18h) to a separate #reminders channel — pointing back at the item in #confirmation — until it's actioned or the 24-hour window closes.

## Email filtering rules

An incoming message is skipped (no draft, no Discord post) if any of these hold:

| Signal | How it's detected |
| --- | --- |
| Gmail category | Message is in `CATEGORY_PROMOTIONS` or `CATEGORY_SOCIAL` |
| Bulk-mail header | Message has a `List-Unsubscribe` header |
| Sender on block list | Sender domain/address is in a configurable block list (e.g. known newsletter senders) |
| No-reply sender | Sender address matches `no-reply@`, `noreply@`, `donotreply@` patterns |
| Sender marked always-skip (set from Discord) | Overrides everything else — always skipped, regardless of other signals; can be set at the sender-address or whole-domain level |

Everything else is treated as a real email and goes through the draft + Discord approval flow. The block list and category rules are configurable, so Azka can add/remove senders over time as false positives/negatives show up.

A sender marked always-draft from Discord is the one exception: it always gets a draft and a Discord post, even if it would otherwise match a skip signal above.

## Architecture and tech stack

&#91;embedded content: architecture · one Python service, four components, SQLite state\]

One Python process handles everything: Inngest triggers a poll every 5 minutes, which calls the Gmail API directly (no MCP server involved), using Gmail's History API to fetch every new message since the last successful poll — paginated, so no message is ever missed even when far more than 10 arrive in one window. Each qualifying message is classified/filtered, then drafted with the Gemini API through a small agent built on Google's Agent Development Kit (ADK) — no heavier multi-agent framework is needed for a single classify-then-draft task — and posted through the Discord bot, including the 6-hour reminder pings and 24-hour expiry, also scheduled through Inngest. Neon (serverless Postgres) holds processed message IDs, pending approvals, reminder/expiry timestamps, and the always-skip/always-draft sender list. The whole service runs in one Docker container locally and on Railway in production, both connecting to the same Neon database over one connection string.

## Data storage

| Data | Why it's needed |
| --- | --- |
| Processed Gmail message IDs | Avoid re-processing the same email on the next poll |
| Pending-approval items (Gmail message ID, Discord message ID, current draft text) | Links a Discord button click back to the right email and draft |
| Sent-reply log | Record of what was actually sent and when, for review |
| Sender block/allow list (incl. always-skip / always-draft overrides, at the sender-address or domain level) | Filtering rule configuration Azka can edit over time |
| Reminder/expiry timestamps per pending item | Know when the next 6-hour reminder is due and when the 24-hour window expires |

Neon (serverless Postgres) is used instead of a local file-based database so Railway doesn't need a persistent volume mount, and so the exact same database is reachable from both the local Docker container during development and the Railway deployment, via one connection string.

## Deployment plan

1. **Local development**: run the Python service in Docker on Azka's laptop, using a `.env` file for Gmail OAuth credentials, Discord bot token, Gemini API key, and Neon connection string
2. **Local testing**: verify polling, filtering, drafting, and the full Discord approve/rewrite/reply-with-text loop against a real Gmail inbox
3. **Production deployment**: push the same Docker image to Railway; Railway runs it continuously; state lives in Neon, so no persistent volume is needed
4. **Secrets**: Gmail OAuth tokens, Discord bot token, Gemini API key, and the Neon connection string are stored as Railway environment variables, not committed to the repo
5. **Monitoring**: basic logging (poll runs, classification decisions, send results) to Railway's log viewer for now; no separate monitoring service in v1

## Build phases

| Phase | Scope |
| --- | --- |
| 1. Gmail connection | OAuth setup; Inngest cron triggers a poll every 5 minutes using Gmail's History API to fetch all new messages since the last poll; store processed message IDs in Neon |
| 2. Filtering | Implement category/header/block-list rules, test against real inbox traffic |
| 3. Drafting | Gemini-generated reply drafts (via Google ADK) for messages that pass the filter |
| 4. Discord bot | Post drafts with Approve / Rewrite / Reply-with-text / Always-skip / Always-draft buttons; 24-hour timeout with 6-hour reminders in #reminders; wire button actions back to sending |
| 5. Dockerize + local test | Full loop running in Docker on Azka's laptop against the real inbox |
| 6. Railway deployment | Ship the same image to Railway, connect it to Neon, verify it runs unattended |

## Open questions

- [ ] Neon setup: one project with separate dev/prod branches, or two separate Neon projects?
- [ ] Manual re-trigger after expiry: a Discord slash command, a button on the expired message, or both?
