import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import db
import groq_client
import sarvam_client
import scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _purge_community_forever() -> None:
    """Community messages and images last 24 hours; sweep expired ones every 10 minutes."""
    while True:
        try:
            messages, images = await db.purge_expired_community()
            if messages or images:
                logger.info("Purged %d expired community messages and %d images", messages, images)
        except Exception:
            logger.exception("Community purge failed")
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await db.init_db()
    except Exception:
        logger.exception("Database init failed")
    background = [
        asyncio.create_task(_purge_community_forever()),
        asyncio.create_task(scheduler.run_forever()),  # event reminder emails
    ]
    yield
    for task in background:
        task.cancel()
    await sarvam_client.close_client()
    await groq_client.close_client()
    await db.close_pool()


app = FastAPI(title="HealAura API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    try:
        await db.check_health()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


from routes.auth import router as auth_router  # noqa: E402
from routes.community import router as community_router  # noqa: E402
from routes.entries import router as entries_router  # noqa: E402
from routes.events import router as events_router  # noqa: E402
from routes.friends import router as friends_router  # noqa: E402
from routes.support import router as support_router  # noqa: E402

app.include_router(auth_router)
app.include_router(entries_router)
app.include_router(events_router)
app.include_router(support_router)
app.include_router(community_router)
app.include_router(friends_router)