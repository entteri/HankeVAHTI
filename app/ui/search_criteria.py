"""EURA- ja Haeavustuksia-hakuilmoitusten hakuehdot."""

import logging

import httpx
from nicegui import ui

from app.db.session import SessionLocal
from app.importers.eura import fetch_eura_options
from app.importers.haeavustuksia import fetch_haeavustuksia_authorities
from app.services.eura_criteria import EuraCriteria, get_eura_criteria, save_eura_criteria
from app.services.haeavustuksia_criteria import (
    GRANT_TYPE_LABELS,
    HaeavustuksiaCriteria,
    get_haeavustuksia_criteria,
    save_haeavustuksia_criteria,
)
from app.ui.theme import page_layout

logger = logging.getLogger(__name__)


def _select_options(options: dict[str, str]) -> dict[str, str]:
    return dict(sorted(options.items(), key=lambda item: item[1].casefold()))


def _selected_text(codes: list[str], labels: dict[str, str]) -> str:
    return ", ".join(labels.get(code, code) for code in codes) if codes else "kaikki"


def _saved_criteria_text(criteria: EuraCriteria, options: dict[str, dict[str, str]]) -> str:
    parts = [
        f"Rahasto: {_selected_text(criteria.funds, options['fund'])}",
        f"Haun kohdealue: {_selected_text(criteria.areas, options['area'])}",
        f"Viranomainen: {_selected_text(criteria.authorities, options['authority'])}",
        f"Maakunnat: {_selected_text(criteria.regions, options['regions'])}",
        f"Hakutunnus: {criteria.call_identifier or 'kaikki'}",
    ]
    return "Voimassa olevat EURA-hakuehdot: " + "; ".join(parts) + "."


def _saved_hae_criteria_text(criteria: HaeavustuksiaCriteria, authorities: dict[str, str]) -> str:
    return (
        "Voimassa olevat Haeavustuksia-hakuehdot: "
        f"Avustuslaji: {_selected_text(criteria.grant_types, GRANT_TYPE_LABELS)}; "
        f"Tulevat haut: {'kyllä' if criteria.show_future else 'ei'}; "
        f"Käynnissä olevat haut: {'kyllä' if criteria.show_ongoing else 'ei'}; "
        f"Viranomainen: {_selected_text(criteria.authorities, authorities)}."
    )


def _eura_section() -> None:
    ui.label("EURA 2021 -hakuilmoitukset").classes("text-xl font-semibold")
    ui.label(
        "Valinnat haetaan EURA-sivuston koodistosta. Rajaukset tallentuvat vasta, kun painat "
        "Tallenna EURA-hakuehdot. Ne vaikuttavat seuraaviin EURA-tuonteihin; aiemmin tuotuja "
        "hankkeita ei poisteta."
    ).classes("text-sm text-gray-600")
    ui.label("Voit valita useita vaihtoehtoja. Tyhjä valinta tarkoittaa kaikkia.").classes("text-sm text-gray-600")

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
    for field, codes in (
        ("fund", criteria.funds),
        ("area", criteria.areas),
        ("authority", criteria.authorities),
        ("regions", criteria.regions),
    ):
        for code in codes:
            options[field].setdefault(code, code)

    with ui.card().classes("w-full p-5 gap-4"):
        saved_label = ui.label(_saved_criteria_text(criteria, options)).classes("text-sm font-medium")
        fund = ui.select(
            _select_options(options["fund"]),
            label="Rahasto",
            value=criteria.funds,
            multiple=True,
            clearable=True,
        ).classes("w-full")
        area = ui.select(
            _select_options(options["area"]),
            label="Haun kohdealue",
            value=criteria.areas,
            multiple=True,
            clearable=True,
        ).classes("w-full")
        authority = ui.select(
            _select_options(options["authority"]),
            label="Viranomainen",
            value=criteria.authorities,
            multiple=True,
            with_input=True,
            clearable=True,
        ).classes("w-full")
        regions = ui.select(
            _select_options(options["regions"]),
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
                funds=list(fund.value or []),
                areas=list(area.value or []),
                authorities=list(authority.value or []),
                regions=list(regions.value or []),
                call_identifier=identifier.value.strip() or None,
            )
            with SessionLocal() as session:
                save_eura_criteria(session, selected)
            saved_label.set_text(_saved_criteria_text(selected, options))
            ui.notify("EURA-hakuehdot tallennettu.", type="positive")

        ui.button("Tallenna EURA-hakuehdot", on_click=save)


def _hae_section() -> None:
    ui.label("Haeavustuksia.fi-hakuilmoitukset").classes("text-xl font-semibold")
    ui.label(
        "Nämä rajaukset vaikuttavat seuraaviin Haeavustuksia-tuonteihin. "
        "Aiemmin tuotuja hankkeita ei poisteta."
    ).classes("text-sm text-gray-600")
    ui.label("Voit valita useita vaihtoehtoja. Tyhjä valinta tarkoittaa kaikkia.").classes("text-sm text-gray-600")

    with SessionLocal() as session:
        criteria = get_haeavustuksia_criteria(session)
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            authorities = fetch_haeavustuksia_authorities(client)
    except (httpx.HTTPError, ValueError, KeyError):
        logger.exception("Haeavustuksia-viranomaisia ei voitu hakea")
        authorities = {}
        ui.label("Haeavustuksia-viranomaisia ei voitu hakea. Muut rajaukset ovat käytettävissä.")
    for code in criteria.authorities:
        authorities.setdefault(code, code)

    with ui.card().classes("w-full p-5 gap-4"):
        saved_label = ui.label(_saved_hae_criteria_text(criteria, authorities)).classes("text-sm font-medium")
        grant_type = ui.select(
            _select_options(GRANT_TYPE_LABELS),
            label="Avustuslaji",
            value=criteria.grant_types,
            multiple=True,
            clearable=True,
        ).classes("w-full")
        show_future = ui.checkbox("Tulevat haut", value=criteria.show_future)
        show_ongoing = ui.checkbox("Käynnissä olevat haut", value=criteria.show_ongoing)
        authority = ui.select(
            _select_options(authorities),
            label="Valtionapuviranomainen",
            value=criteria.authorities,
            multiple=True,
            with_input=True,
            clearable=True,
        ).classes("w-full")

        def save() -> None:
            selected = HaeavustuksiaCriteria(
                grant_types=list(grant_type.value or []),
                show_future=show_future.value,
                show_ongoing=show_ongoing.value,
                authorities=list(authority.value or []),
            )
            with SessionLocal() as session:
                save_haeavustuksia_criteria(session, selected)
            saved_label.set_text(_saved_hae_criteria_text(selected, authorities))
            ui.notify("Haeavustuksia-hakuehdot tallennettu.", type="positive")

        ui.button("Tallenna Haeavustuksia-hakuehdot", on_click=save)


@ui.page("/hakuehdot")
def search_criteria_page() -> None:
    with page_layout(form=True):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Hakuehdot").classes("text-3xl font-bold")
        _eura_section()
        _hae_section()
