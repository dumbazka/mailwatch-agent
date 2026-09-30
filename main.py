import asyncio
import logging
from contextlib import asynccontextmanager

import inngest.fast_api
from fastapi import FastAPI

from config import settings
from discord_bot.bot import bot
from inngest_app import inngest_client, poll_gmail

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    discord_task = None
    if settings.discord_bot_token:
        discord_task = asyncio.create_task(bot.start(settings.discord_bot_token))
    else:
        logging.getLogger(__name__).warning(
            "DISCORD_BOT_TOKEN not set — Discord bot not started. "
            "Drafts will fail to post until it's configured."
        )

    yield

    if discord_task:
        await bot.close()
        discord_task.cancel()


app = FastAPI(lifespan=lifespan)

inngest.fast_api.serve(app, inngest_client, [poll_gmail])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
