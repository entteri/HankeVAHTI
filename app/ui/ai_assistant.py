"""Yhden rahoitushaun Gemini-sparraus nykyisen Lisätiedot-näkymän rinnalla."""

import asyncio
import logging

from nicegui import ui

from app.services.funding_calls import FundingCallView
from app.services.gemini import GeminiError, ask_gemini, configuration_error

logger = logging.getLogger(__name__)

PRESET_QUESTIONS = {
    "Analysoi rahoitushaku": "Analysoi tämä rahoitushaku: tavoitteet, kohderyhmä ja keskeiset ehdot. Mitkä tiedot puuttuvat?",
    "Ehdota hankeideaa": "Ehdota Suomen eOppimiskeskukselle tähän rahoitushakuun sopivaa hankeideaa ja napakkaa hanketekstin luonnosta. Merkitse oletukset.",
    "Mitä pitää tarkistaa?": "Mitä ihmisen pitää tarkistaa alkuperäisestä hakuilmoituksesta ennen hankkeen valmistelua ja osallistumispäätöstä?",
    "Arvioi soveltuvuutta": "Arvioi tämän rahoitushaun soveltuvuutta Suomen eOppimiskeskukselle. Erota tunnetut faktat, oletukset ja tarkistettavat hakukelpoisuusehdot.",
}


def ai_assistant_dialog(call: FundingCallView):
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl p-5 gap-4"):
        ui.label("AI-sparraaja").classes("text-xl font-bold")
        ui.label(call.title).classes("text-lg font-semibold")
        ui.label(
            "Lähetä-painike ja valmiit toiminnot lähettävät kysymyksen sekä tämän haun "
            "nimen, kuvauksen, lähteen, rahaston, kategorian, hakuajan ja relevanssiarvion "
            "Googlen Gemini-palveluun. Jokainen kysymys käsitellään erikseen ilman "
            "aiempia vastauksia. Keskustelua ei tallenneta HankeVAHTIn tietokantaan."
        ).classes("text-sm text-gray-600")
        question = ui.textarea("Kysymyksesi", placeholder="Miten tästä voisi kehittää hankeidean?").classes("w-full")
        status = ui.label(configuration_error() or "Kirjoita kysymys tai valitse valmis toiminto.").classes("text-sm")
        ui.label("Geminin vastaus").classes("font-semibold")
        # Tavallinen tekstielementti: mallin palauttamaa HTML:ää ei suoriteta.
        answer = ui.label("").classes("w-full whitespace-pre-wrap break-words")
        ui.label("AI voi erehtyä. Tarkista faktat alkuperäisestä hakuilmoituksesta. Lopullinen päätös on ihmisellä.").classes("text-sm text-gray-600")
        buttons = []
        busy = False

        async def send(preset: str | None = None) -> None:
            nonlocal busy
            if busy:
                return
            if preset is not None:
                question.set_value(preset)
            text = (question.value or "").strip()
            if not text:
                status.set_text("Kirjoita kysymys tai valitse valmis toiminto.")
                return
            busy = True
            question.disable()
            for button in buttons:
                button.disable()
            status.set_text("Odotetaan Geminin vastausta…")
            answer.set_text("")
            try:
                result = await asyncio.to_thread(ask_gemini, call, text)
                if not dialog.is_deleted:
                    answer.set_text(result)
                    status.set_text("Vastaus valmis.")
            except GeminiError as exc:
                if not dialog.is_deleted:
                    status.set_text(str(exc))
            except Exception as exc:
                logger.warning("AI-sparraajan toiminto epäonnistui (%s)", type(exc).__name__)
                if not dialog.is_deleted:
                    status.set_text("AI-sparraajan pyyntö epäonnistui. Yritä uudelleen.")
            finally:
                busy = False
                if not dialog.is_deleted:
                    question.enable()
                    for button in buttons:
                        button.enable()

        with ui.row().classes("gap-2 flex-wrap"):
            buttons.append(ui.button("Lähetä", on_click=lambda: send()))
            for label, prompt in PRESET_QUESTIONS.items():
                buttons.append(ui.button(label, on_click=lambda _, text=prompt: send(text)).props("outline"))
        ui.button("Sulje sparraaja", on_click=dialog.close).props("flat")
    return dialog
