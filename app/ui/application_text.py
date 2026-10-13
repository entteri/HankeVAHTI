"""A small application-section editor and copyable formatting result."""

import asyncio
import logging

from nicegui import ui

from app.services.application_text import ApplicationTextError, format_application_text
from app.services.funding_calls import FundingCallView

logger = logging.getLogger(__name__)


def application_text_dialog(call: FundingCallView):
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl p-5 gap-4 max-h-[90vh] overflow-y-auto"):
        ui.label("Muotoile hakemustekstiä").classes("text-xl font-bold")
        ui.label(call.title).classes("text-lg")
        ui.label(
            "Muotoile-painike lähettää antamasi tekstit, haun tiedot ja organisaatioprofiilin "
            "OpenAI-palveluun. Tekstiä ei tallenneta tietokantaan. Tarkista lopputuloksen tosiasiat."
        ).classes("text-sm text-gray-600")
        question = ui.input("Hakemuksen osion kysymys tai otsikko").classes("w-full")
        draft = ui.textarea("Oma hakemustekstiluonnos").classes("w-full")
        criteria = ui.textarea("Arviointikriteerit tai lisäohjeet (valinnainen)").classes("w-full")
        limit = ui.input("Merkkimääräraja (valinnainen)", placeholder="Esimerkiksi 2000").classes("w-full")
        status = ui.label("Täytä kysymys ja luonnosteksti. API-avainta tarvitaan vasta muotoiluun.")
        result_text = ui.textarea("Valmis hakemusteksti", value="").props("readonly autogrow").classes("w-full")
        count = ui.label("Merkkimäärä: 0")
        additional = ui.label("").classes("whitespace-pre-wrap break-words")
        copy_button = ui.button("Kopioi valmis teksti", on_click=lambda: ui.clipboard.write(result_text.value)).props("outline")
        copy_button.disable()
        busy = False

        async def format_text() -> None:
            nonlocal busy
            if busy:
                return
            limit_text = (limit.value or "").strip()
            if limit_text and (not limit_text.isascii() or not limit_text.isdigit() or int(limit_text) <= 0):
                status.set_text("Merkkimäärärajan tulee olla positiivinen kokonaisluku tai tyhjä.")
                return
            busy = True
            controls = [question, draft, criteria, limit, submit]
            for control in controls:
                control.disable()
            status.set_text("Muotoillaan tekstiä…")
            try:
                result = await asyncio.to_thread(
                    format_application_text, call, question.value or "", draft.value or "",
                    criteria.value or "", int(limit_text) if limit_text else None,
                )
                if dialog.is_deleted:
                    return
                result_text.set_value(result.text)
                count.set_text(f"Merkkimäärä: {result.character_count}" + (f" / {result.character_limit}" if result.character_limit is not None else ""))
                additional.set_text("Tarvittavat lisätiedot: " + result.additional_information if result.additional_information else "")
                status.set_text(
                    f"Merkkimääräraja ylittyy {result.excess} merkillä. Tekstiä ei katkaistu."
                    if result.excess else ("Teksti on valmis. Tarkista sisältö ennen käyttöä." if result.text else "Täydennä tarvittavat lisätiedot.")
                )
                copy_button.set_enabled(bool(result.text))
            except ApplicationTextError as exc:
                if not dialog.is_deleted:
                    status.set_text(str(exc))
            except Exception as exc:
                logger.warning("Hakemustekstin muotoilu epäonnistui (%s)", type(exc).__name__)
                if not dialog.is_deleted:
                    status.set_text("Muotoilu epäonnistui. Yritä uudelleen.")
            finally:
                busy = False
                if not dialog.is_deleted:
                    for control in controls:
                        control.enable()

        submit = ui.button("Muotoile teksti", on_click=format_text)
        ui.button("Sulje", on_click=dialog.close).props("flat")
    return dialog
