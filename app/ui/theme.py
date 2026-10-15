"""Shared visual theme and page shell; no data fetching or application decisions."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from nicegui import context, ui


DASHBOARD_NAVIGATION = (
    ("Kaikki hankkeet", "/hankkeet"),
    ("Mahdolliset duplikaatit", "/duplikaatit"),
    ("Arvioi hankkeita", "/arvioi"),
    ("Hakuehdot", "/hakuehdot"),
    ("Asetukset", "/asetukset"),
)
FUNDING_NAVIGATION = (
    ("Kaikki hankkeet", "/hankkeet"),
    ("Mahdolliset duplikaatit", "/duplikaatit"),
    ("Arvioi hankkeita", "/arvioi"),
    ("Osallistuttavat", "/osallistuttavat"),
    ("Hylätyt", "/hylatyt"),
    ("Käynnissä olevat", "/kaynnissa"),
    ("Relevanssin asetukset", "/asetukset"),
)

# Presentation only: keep the existing status names and scoring thresholds.
STATUS_TONES = {
    "NEW": "info", "UNDER_REVIEW": "warning", "INTERESTING": "positive",
    "PARTICIPATE": "positive", "REJECTED": "negative", "ARCHIVED": "neutral",
}
RELEVANCE_TONES = {
    "Hyvin relevantti": "positive", "Mahdollisesti relevantti": "info",
    "Tarkistettava": "warning", "Todennäköisesti ei relevantti": "negative",
}


def install_theme() -> None:
    """Register styles and component defaults once at application startup."""
    ui.add_css(Path(__file__).with_name("theme.css"), shared=True)
    ui.button.default_props("no-caps unelevated")
    for field in (ui.input, ui.select, ui.textarea):
        field.default_props("outlined dense")


@contextmanager
def page_layout(
    navigation: Sequence[tuple[str, str]] = (("Etusivulle", "/"),),
    *,
    form: bool = False,
) -> Iterator[None]:
    """Display each page's existing navigation in a shared, responsive header."""
    ui.colors(primary="#193a63", secondary="#61728a", accent="#315f91",
              positive="#237457", negative="#a64248", warning="#936018", info="#315f91")
    request = context.client.request
    current_path = request.url.path if request is not None else ""
    with ui.header(fixed=False, bordered=True).classes("hv-header"):
        with ui.row().classes("hv-header-inner"):
            with ui.row().classes("hv-brand"):
                ui.icon("done").classes("hv-brand-mark").props('aria-hidden="true"')
                ui.label("HankeVAHTI")
            with ui.element("nav").classes("hv-navigation"):
                for label, target in navigation:
                    button = ui.button(label, on_click=lambda _, path=target: ui.navigate.to(path)).props("flat")
                    if current_path == target:
                        button.classes("hv-nav-active").props('aria-current="page"')
    with ui.column().classes("hv-page" + (" hv-page-form" if form else "")):
        yield
