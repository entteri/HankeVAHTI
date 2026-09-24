from fastapi import FastAPI
from nicegui import ui

from app.api.health import router as health_router
from app.api.imports import router as imports_router
from app.ui import dashboard  # noqa: F401 - rekisteröi NiceGUI-sivun

app = FastAPI(title="HankeVAHTI")
app.include_router(health_router)
app.include_router(imports_router)
ui.run_with(app)
