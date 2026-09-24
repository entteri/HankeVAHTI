import asyncio
import logging

from nicegui import ui

from app.db.session import SessionLocal
from app.services.funding_calls import dashboard_counts
from app.services.imports import run_imports

logger = logging.getLogger(__name__)


def _run_imports_from_ui() -> dict[str, dict[str, int]]:
    with SessionLocal() as session:
        return run_imports(session)


def _import_feedback(result: dict[str, dict[str, int]]) -> tuple[str, str]:
    eura_created = result["eura"]["created"]
    hae_created = result["haeavustuksia"]["created"]
    created = eura_created + hae_created
    updated = sum(source["updated"] for source in result.values())
    if created == 0:
        return f"Uusia hankkeita ei löytynyt. Päivitettyjä: {updated}.", "info"
    return (
        f"Tuonti valmis: {created} uutta (EURA {eura_created}, "
        f"Haeavustuksia {hae_created}), {updated} päivitettyä.",
        "positive",
    )


async def _on_import_click() -> None:
    try:
        result = await asyncio.to_thread(_run_imports_from_ui)
    except Exception:
        logger.exception("Tietolähteiden tuonti epäonnistui")
        ui.notify("Tuonti epäonnistui. Tarkista loki.", type="negative")
        return
    dashboard_stats.refresh()
    message, level = _import_feedback(result)
    ui.notify(message, type=level)


@ui.refreshable
def dashboard_stats() -> None:
    with SessionLocal() as session:
        counts = dashboard_counts(session)
    cards = (
        ("Uusia hankkeita", counts["recent"], "/hankkeet"),
        ("Arvioimattomia hankkeita", counts["new"], "/arvioi"),
        ("Osallistuttavia hankkeita", counts["participating"], "/osallistuttavat"),
        ("Hylättyjä hankkeita", counts["rejected"], "/hylatyt"),
        ("Käynnissä olevia hankkeita", counts["ongoing"], "/kaynnissa"),
    )
    with ui.grid(columns=2).classes("w-full gap-4"):
        for title, count, path in cards:
            with ui.card().classes("w-full"):
                ui.label(title).classes("text-lg font-medium")
                ui.label(str(count)).classes("text-2xl")
                if title == "Uusia hankkeita":
                    ui.label("Tuotu viimeisen 7 päivän aikana").classes("text-xs text-gray-600")
                ui.button("Näytä hankkeet", on_click=lambda _, target=path: ui.navigate.to(target)).props("flat")


@ui.page("/")
def dashboard() -> None:
    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-6"):
        ui.label("HankeVAHTI").classes("text-3xl font-bold")
        with ui.row().classes("gap-3 flex-wrap"):
            ui.button("Hae uudet hankkeet", on_click=_on_import_click)
            ui.button("Kaikki hankkeet", on_click=lambda: ui.navigate.to("/hankkeet"))
            ui.button("Arvioi hankkeita", on_click=lambda: ui.navigate.to("/arvioi"))
            ui.button("Hakuehdot", on_click=lambda: ui.navigate.to("/hakuehdot"))
            ui.button("Asetukset", on_click=lambda: ui.navigate.to("/asetukset"))
        ui.label(
            "Hakuehdot rajaavat vain EURA-hakuja. Haeavustuksia-palvelusta tuodaan kaikki avoimet haut."
        ).classes("text-sm text-gray-600")
        dashboard_stats()
