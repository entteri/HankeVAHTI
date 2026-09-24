import asyncio
import logging

from nicegui import ui

from app.db.session import SessionLocal
from app.services.imports import run_imports

logger = logging.getLogger(__name__)


def _run_imports_from_ui() -> dict[str, dict[str, int]]:
    with SessionLocal() as session:
        return run_imports(session)


async def _on_import_click() -> None:
    try:
        result = await asyncio.to_thread(_run_imports_from_ui)
    except Exception:
        logger.exception("Tietolähteiden tuonti epäonnistui")
        ui.notify("Tuonti epäonnistui. Tarkista loki.", type="negative")
        return
    created = sum(source["created"] for source in result.values())
    updated = sum(source["updated"] for source in result.values())
    ui.notify(f"Tuonti valmis: {created} uutta, {updated} päivitettyä.", type="positive")


@ui.page("/")
def dashboard() -> None:
    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-6"):
        ui.label("HankeVAHTI").classes("text-3xl font-bold")
        with ui.row().classes("gap-3 flex-wrap"):
            ui.button("Hae uudet hankkeet", on_click=_on_import_click)
            ui.button("Hakuehdot", on_click=lambda: ui.notify("Hakuehdot lisätään seuraavassa vaiheessa"))
            ui.button("Asetukset", on_click=lambda: ui.notify("Asetukset lisätään seuraavassa vaiheessa"))

        with ui.grid(columns=2).classes("w-full gap-4"):
            for title in (
                "Uusia hankkeita",
                "Arvioimattomia hankkeita",
                "Osallistuttavia hankkeita",
                "Hylättyjä hankkeita",
                "Käynnissä olevia hankkeita",
            ):
                with ui.card().classes("w-full"):
                    ui.label(title).classes("text-lg font-medium")
                    ui.label("—").classes("text-2xl text-gray-500")
