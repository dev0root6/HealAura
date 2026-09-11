import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import db
import sarvam_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await db.init_db()
    except Exception:
        logger.exception("Database init failed")
    yield
    await sarvam_client.close_client()
    await db.close_pool()


app = FastAPI(title="HealAura API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    try:
        await db.check_health()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


from routes.entries import router as entries_router  # noqa: E402
from routes.events import router as events_router  # noqa: E402

app.include_router(entries_router)
app.include_router(events_router)