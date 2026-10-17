
"""A small application-section editor and copyable formatting result."""

import asyncio
import logging

from nicegui import ui

from app.core.config import AI_PROVIDER_LABEL
from app.db.session import SessionLocal
from app.services.application_drafts import (
    list_application_drafts,
    save_application_draft,
)
from app.services.application_text import (
    ApplicationTextError,
    format_application_text,
)
from app.services.funding_calls import FundingCallView

logger = logging.getLogger(__name__)


def application_text_dialog(call: FundingCallView):
    with ui.dialog() as dialog, ui.card().classes(
        "w-full max-w-3xl p-5 gap-4 max-h-[90vh] overflow-y-auto hv-dialog-wide"
    ):
        ui.label("Muotoile hakemustekstiä").classes("text-xl font-bold")
        ui.label(call.title).classes("text-lg")
        ui.label(
            "Voit tallentaa luonnoksen ja jatkaa sen muokkaamista myöhemmin. "
            f"Muotoile-painike lähettää antamasi tekstit, haun tiedot ja "
            f"organisaatioprofiilin palveluun {AI_PROVIDER_LABEL}. "
            "Tarkista tekoälyn tuottaman tekstin tosiasiat."
        ).classes("text-sm text-gray-600")

        question = ui.input(
            "Hakemuksen osion kysymys tai otsikko"
        ).classes("w-full")
        draft = ui.textarea(
            "Oma hakemustekstiluonnos"
        ).classes("w-full")
        criteria = ui.textarea(
            "Arviointikriteerit tai lisäohjeet (valinnainen)"
        ).classes("w-full")
        limit = ui.input(
            "Merkkimääräraja (valinnainen)",
            placeholder="Esimerkiksi 2000",
        ).classes("w-full")

        status = ui.label(
            "Täytä kysymys ja luonnosteksti. API-avainta tarvitaan vasta muotoiluun."
        )
        result_text = ui.textarea(
            "Valmis hakemusteksti", value=""
        ).props("readonly autogrow").classes("w-full")
        count = ui.label("Merkkimäärä: 0")
        additional = ui.label("").classes("whitespace-pre-wrap break-words")

        copy_button = ui.button(
            "Kopioi valmis teksti",
            on_click=lambda: ui.clipboard.write(result_text.value),
        ).props("outline")
        copy_button.disable()

        save_status = ui.label("")
        ui.separator()
        ui.label("Tallennetut hakemusluonnokset").classes(
            "text-lg font-bold"
        )
        saved_drafts = ui.column().classes("w-full gap-2")

        current_draft_id: int | None = None
        busy = False

        def refresh_saved_drafts() -> None:
            saved_drafts.clear()

            try:
                with SessionLocal() as session:
                    drafts = list_application_drafts(session, call.id)

                with saved_drafts:
                    if not drafts:
                        ui.label(
                            "Ei vielä tallennettuja luonnoksia."
                        ).classes("text-sm text-gray-500")
                        return

                    for saved in drafts:
                        # Copy values while the database session is open.
                        saved_id = saved.id
                        saved_title = saved.title
                        saved_updated_at = saved.updated_at

                        with ui.card().classes("w-full p-3 gap-2"):
                            ui.label(saved_title).classes("font-medium")
                            if saved_updated_at:
                                ui.label(
                                    "Viimeksi muokattu: "
                                    f"{saved_updated_at:%d.%m.%Y %H:%M}"
                                ).classes("text-sm text-gray-500")

                            ui.button(
                                "Avaa luonnos",
                                on_click=lambda draft_id=saved_id: load_draft(
                                    draft_id
                                ),
                            ).props("outline")

            except Exception:
                logger.exception(
                    "Hakemusluonnosten hakeminen epäonnistui"
                )
                with saved_drafts:
                    ui.label(
                        "Luonnosten hakeminen epäonnistui. "
                        "Tarkista terminaalin virheviesti."
                    )

        def load_draft(draft_id: int) -> None:
            nonlocal current_draft_id

            try:
                with SessionLocal() as session:
                    drafts = list_application_drafts(session, call.id)
                    selected = next(
                        (item for item in drafts if item.id == draft_id),
                        None,
                    )

                    if selected is None:
                        save_status.set_text(
                            "Luonnosta ei löytynyt tältä rahoitushaulta."
                        )
                        return

                    selected_title = selected.title
                    selected_content = selected.content

                current_draft_id = draft_id
                question.set_value(selected_title)
                draft.set_value(selected_content)
                save_status.set_text(
                    "Luonnos avattu. Voit muokata tekstiä ja tallentaa muutokset."
                )

            except Exception:
                logger.exception("Hakemusluonnoksen avaaminen epäonnistui")
                save_status.set_text(
                    "Luonnoksen avaaminen epäonnistui. Tarkista terminaali."
                )

        def save_draft() -> None:
            nonlocal current_draft_id

            title = (question.value or "").strip()
            content = draft.value or ""

            if not title:
                save_status.set_text("Anna luonnokselle otsikko.")
                return

            if not content.strip():
                save_status.set_text(
                    "Kirjoita luonnosteksti ennen tallentamista."
                )
                return

            try:
                with SessionLocal() as session:
                    saved = save_application_draft(
                        session=session,
                        funding_call_id=call.id,
                        title=title,
                        content=content,
                        draft_id=current_draft_id,
                    )
                    current_draft_id = saved.id

                save_status.set_text("Luonnos tallennettu onnistuneesti.")
                refresh_saved_drafts()

            except Exception:
                logger.exception(
                    "Hakemusluonnoksen tallentaminen epäonnistui"
                )
                save_status.set_text(
                    "Tallennus epäonnistui. Tarkista terminaalin virheviesti."
                )

        async def format_text() -> None:
            nonlocal busy

            if busy:
                return

            limit_text = (limit.value or "").strip()
            if limit_text and (
                not limit_text.isascii()
                or not limit_text.isdigit()
                or int(limit_text) <= 0
            ):
                status.set_text(
                    "Merkkimäärärajan tulee olla positiivinen "
                    "kokonaisluku tai tyhjä."
                )
                return

            busy = True
            controls = [question, draft, criteria, limit, submit]
            for control in controls:
                control.disable()

            status.set_text("Muotoillaan tekstiä…")

            try:
                result = await asyncio.to_thread(
                    format_application_text,
                    call,
                    question.value or "",
                    draft.value or "",
                    criteria.value or "",
                    int(limit_text) if limit_text else None,
                )

                if dialog.is_deleted:
                    return

                result_text.set_value(result.text)
                count.set_text(
                    f"Merkkimäärä: {result.character_count}"
                    + (
                        f" / {result.character_limit}"
                        if result.character_limit is not None
                        else ""
                    )
                )
                additional.set_text(
                    "Tarvittavat lisätiedot: " + result.additional_information
                    if result.additional_information
                    else ""
                )
                status.set_text(
                    f"Merkkimääräraja ylittyy {result.excess} merkillä. "
                    "Tekstiä ei katkaistu."
                    if result.excess
                    else (
                        "Teksti on valmis. Tarkista sisältö ennen käyttöä."
                        if result.text
                        else "Täydennä tarvittavat lisätiedot."
                    )
                )
                copy_button.set_enabled(bool(result.text))

            except ApplicationTextError as exc:
                if not dialog.is_deleted:
                    status.set_text(str(exc))

            except Exception as exc:
                logger.warning(
                    "Hakemustekstin muotoilu epäonnistui (%s)",
                    type(exc).__name__,
                )
                if not dialog.is_deleted:
                    status.set_text("Muotoilu epäonnistui. Yritä uudelleen.")

            finally:
                busy = False
                if not dialog.is_deleted:
                    for control in controls:
                        control.enable()


        submit = ui.button("Muotoile teksti", on_click=format_text)

        def use_ai_suggestion() -> None:
            suggested_text = result_text.value or ""
            if not suggested_text.strip():
                status.set_text("Tekoälyn ehdottamaa tekstiä ei ole vielä.")
                return

            draft.set_value(suggested_text)
            status.set_text(
                "Tekoälyn ehdotus siirrettiin luonnokseen. "
                "Tarkista teksti ja tallenna muutokset."
            )

        ui.button(
            "Käytä tekoälyn ehdotusta",
            on_click=use_ai_suggestion,
        ).props("outline")

        ui.button(
            "Tallenna luonnos", on_click=save_draft
        ).props("outline")
        ui.button("Sulje", on_click=dialog.close).props("flat")


        refresh_saved_drafts()

    return dialog
