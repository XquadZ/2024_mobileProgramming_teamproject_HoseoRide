import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import location, routes, ws
from app.config import settings
from app.core.database import engine
from app.models.base import Base
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await start_scheduler()
    yield
    # Shutdown
    await stop_scheduler()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(routes.router, prefix="/api")
app.include_router(location.router, prefix="/api")
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
