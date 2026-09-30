# mailwatch-agent

Watches a Gmail inbox, filters out newsletters/promotions, drafts replies with
Gemini, and posts them to Discord for approval before anything sends. See
[docs/PRD.md](docs/PRD.md) for the full spec.

## Phase 1 setup (Gmail connection)

1. **Python env**

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Gmail OAuth**
   - In [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one) and enable the **Gmail API**.
   - Under *APIs & Services > Credentials*, create an **OAuth client ID** of type **Desktop app**.
   - Download the JSON and save it as `credentials/gmail_oauth_client.json` (path is configurable via `GOOGLE_OAUTH_CLIENT_SECRETS_FILE`).
   - First run will open a browser for the consent screen and cache the resulting token at `credentials/gmail_token.json`.

3. **Neon (Postgres)**
   - Create a Neon project and copy the connection string.
   - Set it as `DATABASE_URL` in `.env`.
   - Apply the schema:

     ```
     python -m db.connection
     ```

4. **Env file**

   ```
   cp .env.example .env
   ```

   Fill in `DATABASE_URL`, `GEMINI_API_KEY` (drafting comes in Phase 3), and
   leave Discord vars blank for now (Phase 4).

5. **Run the poll function locally**

   In one terminal, start the [Inngest dev server](https://www.inngest.com/docs/dev-server):

   ```
   npx inngest-cli@latest dev
   ```

   In another, run the app:

   ```
   uvicorn main:app --reload
   ```

   The Inngest dev UI (http://localhost:8288) will show `poll-gmail` running
   every `POLL_INTERVAL_MINUTES` (default 5). The first run just records a
   history-ID baseline; subsequent runs fetch and record any new message IDs.

## Project layout

```
gmail/          OAuth + Gmail API client (History API polling)
filters/        Phase 2 — newsletter/promo filtering rules
drafting/       Phase 3 — Gemini/ADK reply drafting
discord_bot/    Phase 4 — approval buttons, reminders, expiry
db/             Neon schema + data access
inngest_app.py  Scheduled poll function
main.py         FastAPI entrypoint serving Inngest functions
```

## Build phases

See [docs/PRD.md](docs/PRD.md#build-phases) — currently on **Phase 1: Gmail
connection**.
