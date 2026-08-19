"""
main.py

Single entry point. Running `python main.py` starts one process that serves
both the FastAPI JSON API and the NiceGUI dashboard - no separate frontend
server, no npm, nothing else to run.
"""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from nicegui import ui

from api import router as api_router
from config import settings
from database import init_db
from ui import register_pages

app = FastAPI(title="DRIFTLY", description="Resilient job-data ingestion platform.")
app.include_router(api_router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# Register NiceGUI pages, then attach NiceGUI (including its Socket.IO app)
# onto our FastAPI app so one process serves both the dashboard and the API.
register_pages()
ui.run_with(app, title="DRIFTLY", storage_secret="driftly-local-dev-secret")


if __name__ in {"__main__", "__mp_main__"}:
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)

