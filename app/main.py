from fastapi import FastAPI
import os
import sentry_sdk
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.routers import auth, chat
from app.db.session import engine, get_db
from app.db.base import Base
from app.config.settings import settings
from app.routers import chat
import logging

sentry_sdk.init(
    dsn=settings.GLITCHTIP_DSN,
    traces_sample_rate=0.01,
    auto_session_tracking=False,
)
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(auth.router)
app.include_router(chat.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://devrayco.name.ng"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def root():
    return {"message": "Hello, World!"}


@app.get("/debug-sentry")
async def trigger_error():
    return 1/0