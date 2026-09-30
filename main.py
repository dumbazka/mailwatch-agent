import inngest.fast_api
from fastapi import FastAPI

from inngest_app import inngest_client, poll_gmail

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [poll_gmail])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
