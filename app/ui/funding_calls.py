"""Hankkeiden selailu, lisätiedot ja osallistumispäätökset."""

import asyncio
from datetime import datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

from nicegui import ui

from app.core.config import AI_PROVIDER_LABEL

from app.db.session import SessionLocal
from app.evaluators.relevance import relevance_label
from app.models import EvaluationStatus, ParticipationStage
from app.services.ai_summary import SummaryError, generate_ai_summary
from app.services.duplicates import DuplicateMatch, find_duplicate_matches
from app.services.funding_calls import FundingCallSort, FundingCallView, list_funding_calls, set_funding_call_status
from app.ui.application_text import application_text_dialog
from app.ui.keyword_highlights import highlight_keywords
from app.ui.theme import FUNDING_NAVIGATION, RELEVANCE_TONES, STATUS_TONES, page_layout

SORT_LABELS = {
    FundingCallSort.DEFAULT.value: "Oletusjärjestys",
    FundingCallSort.RELEVANCE_DESC.value: "Relevanssi: suurin ensin",
    FundingCallSort.RELEVANCE_ASC.value: "Relevanssi: pienin ensin",
    FundingCallSort.DEADLINE_ASC.value: "Deadline: lähin ensin",
    FundingCallSort.DEADLINE_DESC.value: "Deadline: kaukaisin ensin",
    FundingCallSort.REJECTED_AT_DESC.value: "Hylkäyspäivä: uusin ensin",
    FundingCallSort.REJECTED_AT_ASC.value: "Hylkäyspäivä: vanhin ensin",
}

STATUS_LABELS = {
    EvaluationStatus.NEW: "Arvioimatta",
    EvaluationStatus.UNDER_REVIEW: "Arvioinnissa",
    EvaluationStatus.INTERESTING: "Kiinnostava",
    EvaluationStatus.PARTICIPATE: "Osallistutaan",
    EvaluationStatus.REJECTED: "Hylätty",
    EvaluationStatus.ARCHIVED: "Arkistoitu",
}

STAGE_LABELS = {
    ParticipationStage.NOT_STARTED: "Ei aloitettu",
    ParticipationStage.PLANNING: "Suunnittelu",
    ParticipationStage.PREPARING_APPLICATION: "Hakemuksen valmistelu",
    ParticipationStage.WAITING_FOR_DECISION: "Odottaa päätöstä",
    ParticipationStage.APPROVED: "Hyväksytty",
    ParticipationStage.REJECTED: "Hylätty",
    ParticipationStage.COMPLETED: "Valmis",
}


def _date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "Ei tiedossa"


def _rejected_at(value: datetime | None) -> str:
    if value is None:
        return "Ei tiedossa"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Europe/Helsinki")).strftime("%d.%m.%Y klo %H:%M")


def _keyword_badges(title: str, words: list[str] | None, *, scored: bool, excluded: bool = False) -> None:
    ui.label(title).classes("font-medium")
    if words is None:
        ui.label(
            "Osumatietoja ei ole tallennettu. Valitse Asetukset → Pisteytä kaikki haut, "
            "jotta myös päättyneiden hakujen osumat päivittyvät."
            if scored else "Ei vielä pisteytetty"
        )
    elif not words:
        ui.label("Ei osumia")
    else:
        with ui.row().classes("gap-2 flex-wrap"):
            for word in words:
                badge = ui.badge(word)
                if excluded:
                    badge.props("color=red-1 text-color=red-8")


def _details_dialog(call: FundingCallView, duplicate_matches: list[DuplicateMatch], create_summary):
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl p-5 max-h-[90vh] overflow-y-auto"):
        ui.label(call.title).classes("text-xl font-bold")
        ui.label(f"Hakutunnus: {call.call_identifier or call.source_id}")
        ui.label(f"Lähde: {call.source}")
        ui.label(f"Hakuaika: {_date(call.application_start_date)} – {_date(call.application_end_date)}")
        ui.label(f"Tila: {STATUS_LABELS[call.status]}")
        if call.status is EvaluationStatus.REJECTED:
            ui.label(f"Hylätty: {_rejected_at(call.rejected_at)}")
        if duplicate_matches:
            ui.separator()
            ui.label("Mahdollinen duplikaatti").classes("text-lg font-semibold text-orange-800")
            ui.label("Tarkista, ovatko ilmoitukset sama haku. Niitä ei yhdistetä automaattisesti.")
            for match in duplicate_matches:
                other = match.haeavustuksia if match.eura.id == call.id else match.eura
                ui.label(f"{other.source}: {other.title} ({other.identifier})")
                ui.label(match.reason).classes("text-sm text-gray-600")
                if other.source_url:
                    ui.link("Avaa mahdollinen vastinpari", other.source_url, new_tab=True)
        ui.separator()
        ui.label("Relevanssianalyysi").classes("text-lg font-semibold")
        ui.label(f"Relevanssi: {str(call.suitability_score) + ' / 100' if call.suitability_score is not None else 'Ei vielä pisteytetty'}")
        ui.label(f"Luokitus: {relevance_label(call.suitability_score)}")
        scored = call.suitability_score is not None or bool(call.suitability_summary)
        _keyword_badges("Osuneet hakusanat", call.matched_keywords, scored=scored)
        _keyword_badges("Poissulkevat osumat", call.matched_excluded_keywords, scored=scored, excluded=True)
        if call.suitability_summary:
            # Osumat näytetään yllä rakenteisista kentistä; säilytä laskennan perustelu.
            explanation = "\n".join(
                line for line in call.suitability_summary.splitlines()
                if not line.startswith(("Osuvat hakusanat (", "Poissulkevat osumat ("))
            ).strip()
            if explanation:
                ui.label(explanation).classes("whitespace-pre-wrap")
        ui.label("Suositus ei muuta osallistumispäätöstä. Pisteytys päivitetään Asetukset-sivulla.").classes("text-sm text-gray-600")
        ui.label("AI-soveltuvuusarvio").classes("font-semibold")
        summary_text = ui.label(call.ai_summary or "Soveltuvuusarviota ei ole vielä muodostettu.").classes("w-full whitespace-pre-wrap break-words")
        ui.label(
            f"Painike lähettää haun tiedot, organisaatioprofiilin ja arviointiohjeen palveluun {AI_PROVIDER_LABEL}. "
            "Alkuperäistä hakusivua ei lueta. Arvio ei muuta pisteitä tai osallistumispäätöstä."
        ).classes("text-sm text-gray-600")
        ui.button(
            "Muodosta AI-soveltuvuusarvio",
            on_click=lambda event: create_summary(call.id, event.sender, summary_text),
        ).props("outline")
        ui.separator()
        ui.html(highlight_keywords(
            call.description or "Kuvausta ei ole saatavilla.", call.matched_keywords or [],
        )).classes("whitespace-pre-wrap")
        if call.source_url:
            label = {
                "EURA": "Avaa hakuilmoitus EURA:ssa",
                "HAEAVUSTUKSIA": "Avaa haku Haeavustuksia.fi:ssä",
            }.get(call.source, "Avaa lähde")
            ui.link(label, call.source_url, new_tab=True)
        ui.button("Muotoile hakemustekstiä", on_click=lambda: application_text_dialog(call).open()).props("outline")
        ui.button("Luo hankehakemus", on_click=lambda: ui.navigate.to(f"/hankkeet/{call.id}/hakemus"))
        ui.button("Sulje", on_click=dialog.close)
    return dialog


def _render_page(title: str, initial_status: EvaluationStatus | None = None, ongoing_only: bool = False) -> None:
    state = {"search": "", "status": initial_status, "page": 1, "sort": FundingCallSort.DEFAULT}
    pending_summaries: set[int] = set()
    pending_decision: tuple[int, EvaluationStatus] | None = None

    def request_status(call: FundingCallView, status: EvaluationStatus) -> None:
        nonlocal pending_decision
        pending_decision = (call.id, status)
        confirmation_name.set_text(call.title)
        confirmation_change.set_text(f"Tila: {STATUS_LABELS[call.status]} → {STATUS_LABELS[status]}")
        color = {EvaluationStatus.PARTICIPATE: "positive", EvaluationStatus.REJECTED: "negative"}.get(status, "primary")
        confirm_button.props(f"color={color}")
        confirmation.open()

    def clear_decision() -> None:
        nonlocal pending_decision
        pending_decision = None
        confirmation_name.set_text("")
        confirmation_change.set_text("")

    def cancel_decision() -> None:
        clear_decision()
        confirmation.close()

    def confirm_decision() -> None:
        decision = pending_decision
        if decision is None or not confirmation.value:
            return
        # Consume the pending choice before saving, so a double click cannot repeat it.
        cancel_decision()
        choose_status(*decision)

    def choose_status(call_id: int, status: EvaluationStatus) -> None:
        with SessionLocal() as session:
            call = set_funding_call_status(session, call_id, status)
        if call is None:
            ui.notify("Hanketta ei löytynyt.", type="negative")
            return
        ui.notify("Päätös tallennettu.", type="positive")
        state["page"] = 1
        render_rows.refresh()

    async def create_summary(call_id: int, button: ui.button, summary_text: ui.label | None = None) -> None:
        if call_id in pending_summaries:
            return
        pending_summaries.add(call_id)
        button.disable()

        def generate() -> str:
            with SessionLocal() as session:
                return generate_ai_summary(session, call_id)

        try:
            summary = await asyncio.to_thread(generate)
        except SummaryError as exc:
            ui.notify(str(exc), type="negative")
        except Exception:
            ui.notify("Soveltuvuusarvion luonti epäonnistui. Yritä uudelleen.", type="negative")
        else:
            if summary_text is not None and not summary_text.is_deleted:
                summary_text.set_text(summary)
            ui.notify("AI-soveltuvuusarvio tallennettu.", type="positive")
        finally:
            pending_summaries.discard(call_id)
            if summary_text is None:
                render_rows.refresh()
            elif not button.is_deleted:
                button.enable()

    def on_search(event) -> None:
        state["search"] = event.value or ""
        state["page"] = 1
        render_rows.refresh()

    def on_status(event) -> None:
        state["status"] = EvaluationStatus(event.value) if event.value != "ALL" else None
        state["page"] = 1
        render_rows.refresh()

    def on_page(event) -> None:
        state["page"] = event.value
        render_rows.refresh()

    def on_sort(event) -> None:
        state["sort"] = FundingCallSort(event.value)
        state["page"] = 1
        render_rows.refresh()

    @ui.refreshable
    def render_rows() -> None:
        with SessionLocal() as session:
            duplicate_matches = find_duplicate_matches(session)
            calls, total = list_funding_calls(
                session,
                status=state["status"],
                search=state["search"],
                page=state["page"],
                ongoing_only=ongoing_only,
                sort=state["sort"],
            )
        matches_by_id: dict[int, list[DuplicateMatch]] = {}
        for match in duplicate_matches:
            matches_by_id.setdefault(match.eura.id, []).append(match)
            matches_by_id.setdefault(match.haeavustuksia.id, []).append(match)
        ui.label(f"Hankkeita: {total}").classes("text-sm text-gray-600")
        if not calls:
            ui.label("Hankkeita ei löytynyt näillä ehdoilla.").classes("text-gray-600")
        with ui.column().classes("hv-call-list"):
            for call in calls:
                call_matches = matches_by_id.get(call.id, [])
                dialog = _details_dialog(call, call_matches, create_summary)
                dialog.on("hide", lambda: render_rows.refresh())
                with ui.card().classes("w-full hv-call-row"):
                    with ui.row().classes("w-full hv-call-heading"):
                        ui.label(call.title).classes("text-lg font-semibold")
                        if call_matches:
                            ui.badge("Mahdollinen duplikaatti").props("color=orange")
                        ui.badge(STATUS_LABELS[call.status]).classes(f"hv-tone-{STATUS_TONES[call.status.value]}")
                    ui.label(
                        f"{call.call_identifier or call.source_id} · {call.source} · "
                        f"Haku päättyy {_date(call.application_end_date)}"
                    ).classes("text-sm text-gray-600 hv-call-meta")
                    if call.status is EvaluationStatus.REJECTED:
                        ui.label(f"Hylätty: {_rejected_at(call.rejected_at)}").classes("text-sm")
                    ui.label(
                        f"Relevanssi: {call.suitability_score} / 100 · {relevance_label(call.suitability_score)}"
                        if call.suitability_score is not None else "Relevanssi: Ei vielä pisteytetty"
                    ).classes(f"text-sm font-medium hv-call-score hv-tone-{RELEVANCE_TONES.get(relevance_label(call.suitability_score), 'neutral')}")
                    if call.participation_stage is not None and call.status is EvaluationStatus.PARTICIPATE:
                        ui.label(
                            f"Vaihe: {STAGE_LABELS[call.participation_stage]} · "
                            f"Vastuuhenkilö: {call.responsible_person or 'Ei määritetty'} · "
                            f"Seuraava tehtävä: {call.next_action or 'Ei määritetty'}"
                        ).classes("text-sm")
                    if initial_status is EvaluationStatus.PARTICIPATE:
                        if call.ai_summary:
                            ui.label("AI-soveltuvuusarvio").classes("font-semibold hv-saved-summary")
                            ui.label(call.ai_summary).classes("whitespace-pre-wrap hv-saved-summary")
                        summary_button = ui.button(
                            "AI-soveltuvuusarvio",
                            on_click=lambda event, call_id=call.id: create_summary(call_id, event.sender),
                        ).props("outline").classes("hv-summary-action")
                        if call.id in pending_summaries:
                            summary_button.disable()
                    with ui.row().classes("gap-2 flex-wrap hv-call-actions"):
                        ui.button("Lisätiedot", on_click=dialog.open).props("outline")
                        if call.status is not EvaluationStatus.NEW:
                            ui.button(
                                "Arvioimatta",
                                on_click=lambda _, selected=call: request_status(selected, EvaluationStatus.NEW),
                            )
                        if call.status is not EvaluationStatus.PARTICIPATE:
                            ui.button(
                                "Osallistu",
                                on_click=lambda _, selected=call: request_status(selected, EvaluationStatus.PARTICIPATE),
                            ).props("color=positive")
                        if call.status is not EvaluationStatus.REJECTED:
                            ui.button(
                                "Hylkää",
                                on_click=lambda _, selected=call: request_status(selected, EvaluationStatus.REJECTED),
                            ).props("color=negative")
        pages = ceil(total / 20)
        if pages > 1:
            ui.pagination(1, pages, value=state["page"], direction_links=True, on_change=on_page)

    with page_layout(FUNDING_NAVIGATION):
        with ui.dialog() as confirmation, ui.card().classes("hv-dialog-confirm"):
            ui.label("Vahvista tilan muutos").classes("text-lg font-semibold")
            confirmation_name = ui.label("").classes("font-medium")
            confirmation_change = ui.label("")
            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Peruuta", on_click=cancel_decision).props("flat autofocus")
                confirm_button = ui.button("Vahvista", on_click=confirm_decision)
        confirmation.on("hide", clear_decision)
        with ui.row().classes("w-full items-center justify-between gap-4"):
            ui.label(title).classes("text-3xl font-bold")
            ui.button("Etusivulle", on_click=lambda: ui.navigate.to("/")).props("outline")
        ui.label("Pisteet ovat suosituksia. Päivitä pisteytys Asetukset-sivulla tuonnin tai hakusanojen muuttamisen jälkeen.").classes("text-sm text-gray-600")
        if initial_status is EvaluationStatus.PARTICIPATE:
            ui.label(
                "AI-soveltuvuusarvio lähettää haun tiedot sekä organisaatioprofiilin ja peruspromptin "
                f"sisällön palveluun {AI_PROVIDER_LABEL}. Soveltuvuusarvio tallennetaan hankkeelle; pisteet ja päätös säilyvät."
            ).classes("text-sm text-gray-600")
        with ui.row().classes("w-full gap-3 items-center hv-filters"):
            ui.input("Hae nimellä tai tunnuksella", on_change=on_search).classes("grow")
            if initial_status is None and not ongoing_only:
                options = {"ALL": "Kaikki tilat"}
                options.update({status.value: label for status, label in STATUS_LABELS.items()})
                ui.select(options, label="Tila", value="ALL", on_change=on_status).classes("w-48")
            ui.select(
                SORT_LABELS, label="Lajittelu", value=state["sort"].value, on_change=on_sort,
            ).classes("w-64")
        render_rows()


@ui.page("/hankkeet")
def all_funding_calls() -> None:
    _render_page("Kaikki hankkeet")


@ui.page("/arvioi")
def review_funding_calls() -> None:
    _render_page("Arvioi hankkeita", EvaluationStatus.NEW)


@ui.page("/osallistuttavat")
def participating_funding_calls() -> None:
    _render_page("Osallistuttavat hankkeet", EvaluationStatus.PARTICIPATE)


@ui.page("/hylatyt")
def rejected_funding_calls() -> None:
    _render_page("Hylätyt hankkeet", EvaluationStatus.REJECTED)


@ui.page("/kaynnissa")
def ongoing_funding_calls() -> None:
    _render_page("Käynnissä olevat hankkeet", ongoing_only=True)


@ui.page("/duplikaatit")
def possible_duplicates() -> None:
    with SessionLocal() as session:
        matches = find_duplicate_matches(session)
    with page_layout():
        ui.label("Mahdolliset duplikaatit").classes("text-3xl font-bold")
        ui.label(
            "EURA:n ja Haeavustuksia.fi:n haut voivat tarkoittaa samaa hakua. "
            "Vertaa alkuperäisiä ilmoituksia ennen päätöstä; tietoja ei yhdistetä tai poisteta."
        ).classes("text-sm text-gray-600")
        ui.label(f"Mahdollisia pareja: {len(matches)}").classes("font-medium")
        if not matches:
            ui.label("Mahdollisia duplikaatteja ei löytynyt.")
        for match in matches:
            with ui.card().classes("w-full p-4"):
                ui.badge("Mahdollinen duplikaatti").props("color=orange")
                ui.label(match.reason).classes("text-sm text-gray-600")
                for call in (match.eura, match.haeavustuksia):
                    with ui.column().classes("gap-1"):
                        ui.label(f"{call.source}: {call.title}").classes("font-semibold")
                        ui.label(
                            f"Hakutunnus: {call.identifier} · Hakuaika: "
                            f"{_date(call.start_date)} – {_date(call.end_date)}"
                        ).classes("text-sm")
                        if call.source_url:
                            ui.link("Avaa alkuperäinen ilmoitus", call.source_url, new_tab=True)
