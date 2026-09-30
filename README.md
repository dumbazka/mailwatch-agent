# mailwatch-agent

Watches a Gmail inbox, filters out newsletters/promotions, drafts replies with
Gemini, and posts them to Discord for approval before anything sends. See
[docs/PRD.md](docs/PRD.md) for the full spec.

All of Phases 1–4 (Gmail polling, filtering, drafting, Discord approval) are
implemented. What's left is dropping in your own credentials and testing
against a real inbox (Phase 5), then deploying to Railway (Phase 6).

## Setup

1. **Python env**

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Gmail OAuth**
   - In [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one) and enable the **Gmail API**.
   - **APIs & Services → OAuth consent screen**: User type **External** → app name → add scopes `https://www.googleapis.com/auth/gmail.readonly` and `https://www.googleapis.com/auth/gmail.send` (via *Add or Remove Scopes*) → add your own Gmail address under **Test users**.
   - **APIs & Services → Credentials → Create Credentials → OAuth client ID**, type **Desktop app**. Download the JSON.
   - Save it as `credentials/gmail_oauth_client.json`:
     ```
     mkdir -p credentials && mv ~/Downloads/client_secret_*.json credentials/gmail_oauth_client.json
     ```
   - First run opens a browser for the consent screen and caches the token at `credentials/gmail_token.json`. Since the app stays unverified (personal project), Google expires that token after 7 days — when that happens the logs will say so and you just re-run once to reauthorize.

3. **Neon (Postgres)**
   - Create a Neon project, copy the connection string into `DATABASE_URL` in `.env`.
   - Apply the schema:
     ```
     python -m db.connection
     ```

4. **Gemini**
   - Get an API key from [Google AI Studio](https://aistudio.google.com/apikey).
   - Set `GEMINI_API_KEY` in `.env`. `GEMINI_MODEL` defaults to `gemini-2.0-flash`.

5. **Discord bot**
   - [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application** → **Bot** tab → **Reset Token** → copy it into `DISCORD_BOT_TOKEN`.
   - No privileged gateway intents are needed (the bot only uses message components, not message content).
   - **OAuth2 → URL Generator**: scope `bot`, permissions `Send Messages`, `Embed Links`, `Read Message History` → open the generated URL to invite it to your server.
   - Create two text channels, e.g. `#confirmation` and `#reminders`. With Developer Mode on (User Settings → Advanced), right-click each → **Copy Channel ID** → set `DISCORD_CONFIRMATION_CHANNEL_ID` / `DISCORD_REMINDERS_CHANNEL_ID`.

6. **Env file**

   ```
   cp .env.example .env
   ```

   Fill in everything from steps 2–5.

7. **Run it locally**

   In one terminal, start the [Inngest dev server](https://www.inngest.com/docs/dev-server):

   ```
   npx inngest-cli@latest dev
   ```

   In another:

   ```
   uvicorn main:app --reload
   ```

   The Inngest dev UI (http://localhost:8288) shows `poll-gmail` running every
   `POLL_INTERVAL_MINUTES` (default 5). The first run just records a
   history-ID baseline (no backfill of old mail). From then on, new inbox
   messages that pass filtering get drafted and posted to `#confirmation`.

## How the pieces fit together

- `gmail/` — OAuth + Gmail History API polling, sending the final reply.
- `filters/rules.py` — `classify_message()`: category / `List-Unsubscribe` /
  block-list / no-reply / always-skip / always-draft logic.
- `drafting/agent.py` — `draft_reply()`: a Gemini-backed ADK agent that writes
  the reply text (and rewrites it on request).
- `pipeline.py` — `process_message()`: glues classify → draft → post-to-Discord
  together. Used by both the poll loop and the "Re-run" button on an expired item.
- `discord_bot/bot.py` — the five buttons (Approve, Rewrite, Reply with text,
  Always skip sender, Always draft sender), the modal for custom text, and the
  10-minute background loop that sends 6-hour reminders and expires items
  after 24 hours.
- `db/` — Neon schema + data access (`poll_state`, `processed_messages`,
  `pending_approvals`, `sent_replies`, `sender_rules`).
- `main.py` — runs the Discord bot and the FastAPI/Inngest server together in
  one process/event loop, matching the PRD's single-container design.

Assumption made where the PRD left it open: the "manual re-trigger after
expiry" is a **Re-run button** on the expired Discord message (PRD's own
example), not a slash command.

## Deploying (Phase 6)

Same Docker image everywhere. All secrets (Neon connection string, Discord
bot token, Gemini key, the two Gmail OAuth values below) go in as the host's
environment variables — never committed.

**Host needs to support an always-on background process**, not just
request-triggered serverless functions: this app holds a persistent Discord
Gateway connection and runs a 10-minute reminder/expiry loop in-process, so
it can't sleep between requests. Railway's standard service type works.
Render's **free** tier doesn't (only Background Workers stay always-on, and
those need a paid Render plan) — a free always-on VM (e.g. Oracle Cloud's
Always Free tier) running the same Docker image is the zero-cost option.

**Gmail credentials — no file on the deployed host, so pass JSON directly:**
1. Locally, you already have `credentials/gmail_oauth_client.json` and
   `credentials/gmail_token.json` (the latter only exists after you've done
   the one-time browser consent locally at least once).
2. On the host, set:
   ```
   GOOGLE_OAUTH_CLIENT_SECRETS_JSON=<paste contents of gmail_oauth_client.json>
   GOOGLE_OAUTH_TOKEN_JSON=<paste contents of gmail_token.json>
   ```
   (`cat credentials/gmail_oauth_client.json` / `cat credentials/gmail_token.json` to get the values.)
3. Leave `GOOGLE_OAUTH_CLIENT_SECRETS_FILE` / `GOOGLE_OAUTH_TOKEN_FILE` unset on the host — they're the local-dev fallback and are ignored once the `_JSON` versions are set.
4. Since the app stays unverified (personal project, "Testing" mode), Google
   expires the refresh token after ~7 days. When that happens, re-run the
   consent flow locally (deleting `credentials/gmail_token.json` first) and
   update `GOOGLE_OAUTH_TOKEN_JSON` on the host with the new contents.

**Inngest**: once deployed, point Inngest Cloud at the live URL and set
`INNGEST_EVENT_KEY` / `INNGEST_SIGNING_KEY` from its dashboard (these stay
blank for local dev against `inngest dev`).
