from nicegui import ui


@ui.page("/")
def dashboard() -> None:
    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-6"):
        ui.label("HankeVAHTI").classes("text-3xl font-bold")
        with ui.row().classes("gap-3 flex-wrap"):
            ui.button("Hae uudet hankkeet", on_click=lambda: ui.notify("Tuonti lisätään seuraavassa vaiheessa"))
            ui.button("Hakuehdot", on_click=lambda: ui.notify("Hakuehdot lisätään seuraavassa vaiheessa"))
            ui.button("Asetukset", on_click=lambda: ui.notify("Asetukset lisätään seuraavassa vaiheessa"))

        with ui.grid(columns=2).classes("w-full gap-4"):
            for title in (
                "Uusia hankkeita",
                "Arvioimattomia hankkeita",
                "Osallistuttavia hankkeita",
                "Hylättyjä hankkeita",
                "Käynnissä olevia hankkeita",
            ):
                with ui.card().classes("w-full"):
                    ui.label(title).classes("text-lg font-medium")
                    ui.label("—").classes("text-2xl text-gray-500")
