"""Long application editor using the existing page shell and field services."""

import asyncio
import logging

from nicegui import ui
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import AI_PROVIDER_LABEL
from app.db.session import SessionLocal
from app.services.application_document import (
    ApplicationDocumentError, DOCX_MEDIA_TYPE, application_filename, export_application_document,
)
from app.services.eura_application_drafts import (
    EuraApplicationDraftError, generate_application_field, get_application_draft, save_application_draft,
)
from app.services.application_template import APPLICATION_FIELDS, SECTIONS
from app.services.application_text import ApplicationTextError
from app.services.funding_calls import get_funding_call
from app.ui.theme import page_layout

logger = logging.getLogger(__name__)


@ui.page("/hankkeet/{call_id}/hakemus")
def application_draft_page(call_id: int):
    with page_layout((("Kaikki hankkeet", "/hankkeet"), ("Etusivulle", "/")), form=True):
        ui.label("Hankehakemusluonnos").classes("text-2xl font-bold")
        try:
            with SessionLocal() as session:
                call = get_funding_call(session, call_id)
                if call is None:
                    ui.label("Rahoitushakua ei löydy.")
                    return
                saved = get_application_draft(session, call_id)
                content = saved.content_json if saved else {}
        except SQLAlchemyError:
            ui.label("Hakemusluonnosta ei voitu avata. Tarkista tietokantayhteys ja että tietokannan migraatiot on ajettu.")
            return
        ui.label(call.title).classes("text-xl")
        ui.label(
            "Tämä on HankeVAHTI:n työskentelyluonnos. AI tuottaa ehdotuksia, mutta käyttäjä vastaa hakemuksen "
            "sisällöstä ja tarkistaa tiedot ennen niiden siirtämistä EURA-järjestelmään."
        )
        ui.label(
            "AI ei täytä automaattisesti henkilötietoja, virallisia organisaatiotietoja, budjettia, rahoitusta "
            "tai muita tosiasiallisia tietoja, joita lähdeaineisto ei sisällä."
        ).classes("text-sm text-gray-600")
        ui.label(
            f"AI-painike lähettää lähtötiedot, käsiteltävän tekstin, vahvistetut hanketekstit, haun tiedot ja "
            f"organisaatioprofiilin, arviointikriteerit.md:n taustatiedot ja kirjoitusohjeet palveluun {AI_PROVIDER_LABEL}. "
            "Älä kirjoita tarpeettomia henkilötietoja. "
            "Merkitse tarkistamasi teksti AI:n taustatiedoksi, jotta sitä voi käyttää muissa kentissä."
        ).classes("text-sm text-gray-600")
        ui.label("Tallenna muutokset ennen sivulta poistumista. Wordiin viedään viimeksi tallennettu luonnos.").classes("text-sm")
        project_context = ui.textarea("Omat ideat ja tarkennukset (vapaaehtoinen)", value=content.get("project_context", "")).props("autogrow").classes("w-full")
        ui.label(
            "Voit jättää kentän tyhjäksi. AI käyttää haun kuvausta ja organisaation taustatietoja "
            "sekä mahdollisia vahvistettuja hanketekstejä. Tarkista ehdotetut tavoitteet ja toimet ennen käyttöä."
        ).classes("text-sm text-gray-600")
        editors, confirmations, additional_labels, buttons = {}, {}, {}, {}
        additional = dict(content.get("additional_information", {}))
        busy = False
        dirty = False
        status = ui.label("Luonnos ladattu." if saved else "Uusi luonnos. Voit pyytää AI-ehdotuksen suoraan kentän painikkeesta.").classes("whitespace-pre-wrap")

        def mark_dirty():
            nonlocal dirty
            dirty = True
            status.set_text("Tallentamattomia muutoksia.")

        project_context.on_value_change(mark_dirty)

        def snapshot():
            return {"project_context": project_context.value or "",
                    "fields": {key: editor.value or "" for key, editor in editors.items()},
                    "confirmed_fields": [key for key, check in confirmations.items() if check.value],
                    "additional_information": dict(additional)}

        def save():
            nonlocal dirty
            try:
                with SessionLocal() as session:
                    save_application_draft(session, call_id, snapshot())
                dirty = False
                status.set_text("Hankehakemusluonnos tallennettu.")
                ui.notify("Hankehakemusluonnos tallennettu.", type="positive")
            except (EuraApplicationDraftError, SQLAlchemyError) as exc:
                status.set_text(str(exc) if isinstance(exc, EuraApplicationDraftError) else "Tallennus epäonnistui. Tekstit ovat edelleen tässä näkymässä. Yritä uudelleen.")

        async def download():
            nonlocal busy
            if busy:
                return
            if dirty:
                status.set_text("Tallenna muutokset ennen Word-luonnoksen lataamista.")
                return
            busy = True
            set_busy(True)
            try:
                with SessionLocal() as session:
                    latest = get_application_draft(session, call_id)
                    if latest is None:
                        status.set_text("Tallenna luonnos ennen Word-luonnoksen lataamista.")
                        return
                    saved_content = latest.content_json
                output = await asyncio.to_thread(export_application_document, call, saved_content)
                if status.is_deleted:
                    return
                ui.download(output, filename=application_filename(call_id), media_type=DOCX_MEDIA_TYPE)
                status.set_text("Word-luonnos valmis. Tarkista sisältö ja täydennä viralliset tiedot Wordissa.")
            except ApplicationDocumentError as exc:
                status.set_text(str(exc))
            except SQLAlchemyError:
                status.set_text("Tallennetun luonnoksen lukeminen epäonnistui. Yritä uudelleen.")
            finally:
                busy = False
                if not status.is_deleted:
                    set_busy(False)

        with ui.row().classes("w-full gap-3 hv-application-actions"):
            save_button = ui.button("Tallenna luonnos", on_click=save)
            download_button = ui.button("Lataa Word-luonnos", on_click=download).props("outline")

        def set_busy(value):
            for control in [save_button, download_button, project_context, *editors.values(),
                            *confirmations.values(), *buttons.values(), *clear_buttons]:
                control.set_enabled(not value)

        async def generate(key):
            nonlocal busy
            if busy:
                return
            busy = True
            set_busy(True)
            status.set_text("AI valmistelee kentän tekstiä…")
            try:
                result = await asyncio.to_thread(generate_application_field, call, key, snapshot())
                if status.is_deleted:
                    return
                if result.text.strip():
                    editors[key].set_value(result.text)
                    confirmations[key].set_value(False)
                additional[key] = result.additional_information
                additional_labels[key].set_text("Tarvittavat lisätiedot: " + result.additional_information if result.additional_information else "")
                mark_dirty()
                status.set_text("Tarkista AI:n ehdotus ja tallenna luonnos." if result.text.strip() else "AI tarvitsee lisätietoja. Aiempi kenttäteksti säilyi.")
            except ApplicationTextError as exc:
                if not status.is_deleted:
                    status.set_text(str(exc))
                    ui.notify(str(exc), type="warning")
            except Exception as exc:
                logger.warning("Hakemuskentän AI-avustus epäonnistui (%s)", type(exc).__name__)
                if not status.is_deleted:
                    status.set_text("AI-avustus epäonnistui. Aiempi teksti säilyi. Yritä uudelleen.")
                    ui.notify("AI-avustus epäonnistui. Aiempi teksti säilyi.", type="negative")
            finally:
                busy = False
                if not status.is_deleted:
                    set_busy(False)

        def add_field(field):
            key = field.id
            with ui.column().classes("w-full gap-2 hv-application-field"):
                ui.label(field.label).classes("font-medium")
                # Explicit rows also work inside initially hidden expansions, where
                # Quasar's autogrow cannot measure the final text width reliably.
                editor = ui.textarea(value=content.get("fields", {}).get(key, "")).props("rows=4").classes("w-full")
                editor.props["aria-label"] = field.label
                editor.props["data-field-id"] = key
                editors[key] = editor
                check = ui.checkbox("Tarkistettu – käytä AI:n taustatietona", value=key in content.get("confirmed_fields", []))
                confirmations[key] = check
                check.on_value_change(mark_dirty)
                if field.ai_enabled:
                    button = ui.button("Paranna AI:lla" if (editor.value or "").strip() else "Ehdota AI:lla", on_click=lambda: generate(key)).props("outline")
                    button.props["data-field-id"] = key
                    buttons[key] = button
                def changed():
                    check.set_value(False)
                    if key in buttons:
                        buttons[key].set_text("Paranna AI:lla" if (editor.value or "").strip() else "Ehdota AI:lla")
                    additional.pop(key, None)
                    additional_labels[key].set_text("")
                    mark_dirty()
                editor.on_value_change(changed)
                additional_labels[key] = ui.label("Tarvittavat lisätiedot: " + additional[key] if additional.get(key) else "").classes("whitespace-pre-wrap text-sm")

        clear_buttons = []
        for section, title in SECTIONS.items():
            with ui.expansion(title, value=section == "3").classes("w-full hv-application-section"):
                for field in APPLICATION_FIELDS:
                    if field.section == section and field.type != "risk":
                        add_field(field)
                if section == "5.3":
                    ui.label("Riskit ja niiden hallinta hankkeen toteuttamisessa").classes("text-lg font-medium")
                    ui.label("Riskit ovat ehdotuksia. Täytä ja vahvista riski ennen hallintatoimenpiteen AI-avustusta. Pohjassa on viisi riskiriviä.")
                    for row in range(1, 6):
                        with ui.expansion(f"Riski {row}").classes("w-full"):
                            keys = [f.id for f in APPLICATION_FIELDS if f.id.startswith(f"risk_{row}_")]
                            for field in APPLICATION_FIELDS:
                                if field.id in keys:
                                    add_field(field)
                            def clear_risk(keys=keys):
                                for key in keys:
                                    editors[key].set_value("")
                                    confirmations[key].set_value(False)
                                    additional.pop(key, None)
                                    additional_labels[key].set_text("")
                                mark_dirty()
                            clear_buttons.append(ui.button(f"Poista riski {row}", on_click=clear_risk).props("flat").classes("text-negative"))
        ui.label("Word-luonnos perustuu EURA-esimerkkipohjaan. Tyhjät kohdat säilyvät pohjan mukaisina. Virallinen hakemus jätetään rahoittajan sähköisessä järjestelmässä.").classes("text-sm text-gray-600")
