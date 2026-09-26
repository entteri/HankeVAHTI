"""Paikallisen sovelluksen asetussivu."""

import asyncio
import logging

from nicegui import ui

from app.db.session import SessionLocal
from app.evaluators.relevance import EXCLUSION_PENALTY, KEYWORD_POINTS, RELEVANCE_THRESHOLDS
from app.services.relevance import score_funding_calls
from app.services.search_profiles import get_keyword_settings, save_keyword_settings
from app.services.settings import delete_all_funding_calls, funding_call_count

logger = logging.getLogger(__name__)


def _score_from_ui() -> int:
    with SessionLocal() as session:
        return score_funding_calls(session)


def _relevance_settings() -> None:
    with SessionLocal() as session:
        settings = get_keyword_settings(session)
    with ui.card().classes("w-full p-5 gap-4"):
        ui.label("Relevanssin hakusanat").classes("text-xl font-semibold")
        ui.label(
            "Kirjoita yksi sana tai ilmaus riville. Voit lisätä, muokata ja poistaa rivejä. "
            "Sanat koskevat molempien lähteiden hakuja. Poissulkusanat laskevat vain pisteitä."
        ).classes("text-sm text-gray-600")
        keywords = ui.textarea("Kiinnostavat hakusanat", value="\n".join(settings.keywords)).classes("w-full")
        exclusions = ui.textarea("Poissulkusanat", value="\n".join(settings.excluded_keywords)).classes("w-full")
        ui.label(
            f"Kukin eri hakusana: +{KEYWORD_POINTS} pistettä, yhteensä enintään 100. "
            f"Sen jälkeen kukin eri poissulkusana: −{EXCLUSION_PENALTY} pistettä, vähintään 0. "
            "Vertailussa käytetään kokonaisia sanoja ja ilmauksia kirjainkoosta riippumatta. "
            "Taivutusmuotoja ei tunnisteta. Tyhjillä listoilla tulos on 0."
        ).classes("text-sm text-gray-600")
        upper = 100
        for lower, label in RELEVANCE_THRESHOLDS:
            ui.label(f"{lower}–{upper}: {label}").classes("text-sm")
            upper = lower - 1
        ui.label(
            "Tallenna sanat ja käynnistä pisteytys. Pisteytys käyttää tallennettuja sanoja "
            "ja käsittelee kaikki haut, joiden hakuaika ei ole päättynyt, myös tulevat "
            "ja haut ilman päättymispäivää. Osallistumispäätökset säilyvät. "
            "Aja pisteytys uudelleen tuonnin tai hakusanojen muuttamisen jälkeen. "
            "Vanhat pisteet ja perustelut säilyvät uuteen pisteytykseen asti."
        ).classes("text-sm text-gray-600")
        feedback = ui.label().classes("text-sm font-medium")

        def save() -> None:
            try:
                with SessionLocal() as session:
                    saved = save_keyword_settings(
                        session, (keywords.value or "").splitlines(), (exclusions.value or "").splitlines(),
                    )
            except Exception:
                logger.exception("Relevanssin hakusanojen tallennus epäonnistui")
                ui.notify("Hakusanojen tallennus epäonnistui. Tarkista loki.", type="negative")
                return
            keywords.set_value("\n".join(saved.keywords))
            exclusions.set_value("\n".join(saved.excluded_keywords))
            feedback.set_text("Hakusanat tallennettu. Pisteytä haut päivittääksesi tulokset.")
            ui.notify("Relevanssin hakusanat tallennettu.", type="positive")

        async def score() -> None:
            save_button.disable()
            score_button.disable()
            feedback.set_text("Pisteytetään tallennetuilla hakusanoilla…")
            try:
                count = await asyncio.to_thread(_score_from_ui)
                feedback.set_text(f"Pisteytetty {count} hakua. Osallistumispäätökset säilytettiin.")
                ui.notify(f"Pisteytetty {count} hakua.", type="positive")
            except ValueError as exc:
                feedback.set_text(str(exc))
                ui.notify(str(exc), type="warning")
            except Exception:
                logger.exception("Relevanssipisteytys epäonnistui")
                feedback.set_text("Pisteytys epäonnistui. Aiemmat tulokset säilytettiin.")
                ui.notify("Pisteytys epäonnistui. Tarkista loki.", type="negative")
            finally:
                save_button.enable()
                score_button.enable()

        with ui.row().classes("gap-2 flex-wrap"):
            save_button = ui.button("Tallenna hakusanat", on_click=save)
            score_button = ui.button("Pisteytä päättymättömät haut", on_click=score)
            ui.button("Näytä hankkeet", on_click=lambda: ui.navigate.to("/hankkeet")).props("outline")


@ui.page("/asetukset")
def settings_page() -> None:
    with SessionLocal() as session:
        count = funding_call_count(session)

    with ui.column().classes("w-full max-w-3xl mx-auto p-6 gap-5"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Asetukset").classes("text-3xl font-bold")
            ui.button("Etusivulle", on_click=lambda: ui.navigate.to("/")).props("outline")

        _relevance_settings()

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
