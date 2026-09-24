"""EURA 2021 -hakuilmoitusten hakuehdot."""

import logging

import httpx
from nicegui import ui

from app.db.session import SessionLocal
from app.importers.eura import fetch_eura_options
from app.services.eura_criteria import EuraCriteria, get_eura_criteria, save_eura_criteria

logger = logging.getLogger(__name__)


def _select_options(options: dict[str, str], all_label: str) -> dict[str, str]:
    return {"": all_label, **dict(sorted(options.items(), key=lambda item: item[1].casefold()))}


@ui.page("/hakuehdot")
def search_criteria_page() -> None:
    with ui.column().classes("w-full max-w-3xl mx-auto p-6 gap-5"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Hakuehdot").classes("text-3xl font-bold")
            ui.button("Etusivulle", on_click=lambda: ui.navigate.to("/")).props("outline")
        ui.label("EURA 2021 -hakuilmoitukset").classes("text-xl font-semibold")
        ui.label(
            "Valinnat haetaan EURA-sivuston koodistosta. Tallennetut ehdot vaikuttavat seuraaviin "
            "EURA-tuonteihin; aiemmin tuotuja hankkeita ei poisteta."
        ).classes("text-sm text-gray-600")

        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                options = fetch_eura_options(client)
        except (httpx.HTTPError, ValueError, KeyError):
            logger.exception("EURA-hakuehtojen vaihtoehtoja ei voitu hakea")
            ui.label("EURA-valintoja ei voitu hakea. Tarkista verkkoyhteys ja yritä uudelleen.")
            ui.button("Yritä uudelleen", on_click=ui.navigate.reload)
            return

        with SessionLocal() as session:
            criteria = get_eura_criteria(session)

        with ui.card().classes("w-full p-5 gap-4"):
            fund = ui.select(
                _select_options(options["fund"], "Kaikki rahastot"),
                label="Rahasto",
                value=criteria.fund or "",
            ).classes("w-full")
            area = ui.select(
                _select_options(options["area"], "Kaikki kohdealueet"),
                label="Haun kohdealue",
                value=criteria.area or "",
            ).classes("w-full")
            authority = ui.select(
                _select_options(options["authority"], "Kaikki viranomaiset"),
                label="Viranomainen",
                value=criteria.authority or "",
                with_input=True,
            ).classes("w-full")
            regions = ui.select(
                dict(sorted(options["regions"].items(), key=lambda item: item[1].casefold())),
                label="Maakunnat",
                value=criteria.regions,
                multiple=True,
                with_input=True,
                clearable=True,
            ).classes("w-full")
            identifier = ui.input(
                "Hakutunnus",
                value=criteria.call_identifier or "",
                placeholder="Esim. PSUEVK-112",
            ).classes("w-full")

            def save() -> None:
                selected = EuraCriteria(
                    fund=fund.value or None,
                    area=area.value or None,
                    authority=authority.value or None,
                    regions=list(regions.value or []),
                    call_identifier=identifier.value.strip() or None,
                )
                with SessionLocal() as session:
                    save_eura_criteria(session, selected)
                ui.notify("EURA-hakuehdot tallennettu.", type="positive")

            ui.button("Tallenna hakuehdot", on_click=save)
