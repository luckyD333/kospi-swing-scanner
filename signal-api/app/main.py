import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.signals import router as signals_router
from .api.market import router as market_router

app = FastAPI(title="Signal API", version="1.0.0")

_origins = os.getenv("SIGNAL_API_CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(signals_router, prefix="/api")
app.include_router(market_router, prefix="/api")
