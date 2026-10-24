from fastapi import FastAPI

from app.api import health

app = FastAPI(title="Skjald", docs_url=None, redoc_url=None)
app.include_router(health.router, prefix="/api")
