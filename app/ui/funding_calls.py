"""Hankkeiden selailu, lisätiedot ja osallistumispäätökset."""

from math import ceil

from nicegui import ui

from app.db.session import SessionLocal
from app.models import EvaluationStatus, ParticipationStage
from app.services.funding_calls import FundingCallView, list_funding_calls, set_funding_call_status

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


def _details_dialog(call: FundingCallView):
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl p-5"):
        ui.label(call.title).classes("text-xl font-bold")
        ui.label(f"Hakutunnus: {call.call_identifier or call.source_id}")
        ui.label(f"Lähde: {call.source}")
        ui.label(f"Hakuaika: {_date(call.application_start_date)} – {_date(call.application_end_date)}")
        ui.label(f"Tila: {STATUS_LABELS[call.status]}")
        ui.label(f"Soveltuvuuspisteet: {call.suitability_score if call.suitability_score is not None else 'Ei vielä pisteytetty'}")
        if call.suitability_summary:
            ui.label(call.suitability_summary).classes("whitespace-pre-wrap")
        ui.separator()
        ui.label(call.description or "Kuvausta ei ole saatavilla.").classes("whitespace-pre-wrap")
        if call.source_url:
            ui.link("Avaa lähde", call.source_url, new_tab=True)
        ui.button("Sulje", on_click=dialog.close)
    return dialog


def _render_page(title: str, initial_status: EvaluationStatus | None = None, ongoing_only: bool = False) -> None:
    state = {"search": "", "status": initial_status, "page": 1}

    def choose_status(call_id: int, status: EvaluationStatus) -> None:
        with SessionLocal() as session:
            call = set_funding_call_status(session, call_id, status)
        if call is None:
            ui.notify("Hanketta ei löytynyt.", type="negative")
            return
        ui.notify("Päätös tallennettu.", type="positive")
        state["page"] = 1
        render_rows.refresh()

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

    @ui.refreshable
    def render_rows() -> None:
        with SessionLocal() as session:
            calls, total = list_funding_calls(
                session,
                status=state["status"],
                search=state["search"],
                page=state["page"],
                ongoing_only=ongoing_only,
            )
        ui.label(f"Hankkeita: {total}").classes("text-sm text-gray-600")
        if not calls:
            ui.label("Hankkeita ei löytynyt näillä ehdoilla.").classes("text-gray-600")
        for call in calls:
            dialog = _details_dialog(call)
            with ui.card().classes("w-full p-4"):
                with ui.row().classes("w-full items-start justify-between gap-4"):
                    ui.label(call.title).classes("text-lg font-semibold")
                    ui.badge(STATUS_LABELS[call.status])
                ui.label(
                    f"{call.call_identifier or call.source_id} · {call.source} · "
                    f"Haku päättyy {_date(call.application_end_date)}"
                ).classes("text-sm text-gray-600")
                if call.participation_stage is not None and call.status is EvaluationStatus.PARTICIPATE:
                    ui.label(
                        f"Vaihe: {STAGE_LABELS[call.participation_stage]} · "
                        f"Vastuuhenkilö: {call.responsible_person or 'Ei määritetty'} · "
                        f"Seuraava tehtävä: {call.next_action or 'Ei määritetty'}"
                    ).classes("text-sm")
                with ui.row().classes("gap-2 flex-wrap"):
                    ui.button("Lisätiedot", on_click=dialog.open).props("outline")
                    if call.status is not EvaluationStatus.PARTICIPATE:
                        ui.button(
                            "Osallistu",
                            on_click=lambda _, call_id=call.id: choose_status(call_id, EvaluationStatus.PARTICIPATE),
                        )
                    if call.status is not EvaluationStatus.REJECTED:
                        ui.button(
                            "Hylkää",
                            on_click=lambda _, call_id=call.id: choose_status(call_id, EvaluationStatus.REJECTED),
                        ).props("color=negative")
        pages = ceil(total / 20)
        if pages > 1:
            ui.pagination(1, pages, value=state["page"], direction_links=True, on_change=on_page)

    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-5"):
        with ui.row().classes("w-full items-center justify-between gap-4"):
            ui.label(title).classes("text-3xl font-bold")
            ui.button("Etusivulle", on_click=lambda: ui.navigate.to("/")).props("outline")
        with ui.row().classes("gap-2 flex-wrap"):
            ui.button("Kaikki hankkeet", on_click=lambda: ui.navigate.to("/hankkeet")).props("flat")
            ui.button("Arvioi hankkeita", on_click=lambda: ui.navigate.to("/arvioi")).props("flat")
            ui.button("Osallistuttavat", on_click=lambda: ui.navigate.to("/osallistuttavat")).props("flat")
            ui.button("Hylätyt", on_click=lambda: ui.navigate.to("/hylatyt")).props("flat")
            ui.button("Käynnissä olevat", on_click=lambda: ui.navigate.to("/kaynnissa")).props("flat")
        with ui.row().classes("w-full gap-3 items-center"):
            ui.input("Hae nimellä tai tunnuksella", on_change=on_search).classes("grow")
            if initial_status is None and not ongoing_only:
                options = {"ALL": "Kaikki tilat"}
                options.update({status.value: label for status, label in STATUS_LABELS.items()})
                ui.select(options, label="Tila", value="ALL", on_change=on_status).classes("w-48")
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
