"""Paikallisen sovelluksen asetussivu."""

import logging

from nicegui import ui

from app.db.session import SessionLocal
from app.services.settings import delete_all_funding_calls, funding_call_count

logger = logging.getLogger(__name__)


@ui.page("/asetukset")
def settings_page() -> None:
    with SessionLocal() as session:
        count = funding_call_count(session)

    with ui.column().classes("w-full max-w-3xl mx-auto p-6 gap-5"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Asetukset").classes("text-3xl font-bold")
            ui.button("Etusivulle", on_click=lambda: ui.navigate.to("/")).props("outline")

        with ui.card().classes("w-full p-5 gap-4"):
            ui.label("Aloita hankkeiden haku alusta").classes("text-xl font-semibold")
            count_label = ui.label(f"Tallennettuja hankkeita: {count}")
            ui.label(
                "Poisto tyhjentää kaikki haetut hankkeet sekä niihin liittyvät arviot ja "
                "osallistumistiedot. Tallennetut hakuehdot säilyvät."
            ).classes("text-sm text-gray-600")

            def confirm_delete() -> None:
                try:
                    with SessionLocal() as session:
                        deleted = delete_all_funding_calls(session)
                except Exception:
                    logger.exception("Hankkeiden poistaminen epäonnistui")
                    ui.notify("Hankkeiden poistaminen epäonnistui. Tarkista loki.", type="negative")
                    return
                dialog.close()
                count_label.set_text("Tallennettuja hankkeita: 0")
                delete_button.disable()
                ui.notify(f"Poistettiin {deleted} hanketta. Voit hakea hankkeet uudelleen.", type="positive")

            with ui.dialog() as dialog, ui.card():
                ui.label("Poistetaanko kaikki haetut hankkeet?").classes("text-lg font-semibold")
                ui.label(
                    "Myös arviot ja osallistumistiedot poistetaan pysyvästi. "
                    "Tätä ei voi kumota. Hakuehdot säilyvät."
                )
                with ui.row().classes("justify-end w-full"):
                    ui.button("Peruuta", on_click=dialog.close).props("flat")
                    ui.button("Poista hankkeet", on_click=confirm_delete).props("color=negative")

            delete_button = ui.button("Poista kaikki haetut hankkeet", on_click=dialog.open).props("color=negative")
            if count == 0:
                delete_button.disable()
