"""One import at a time across UI tabs and API, using mocked sources."""

from threading import Event

import pytest
from nicegui import events, ui

from app.ui.dashboard import _on_import_click
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


@pytest.mark.parametrize("fail", [False, True])
def test_import_guard_across_tabs_and_api_releases_after_completion(db_session, monkeypatch, fail):
    started, release = Event(), Event()
    calls, notifications = [], []

    def fetch_eura(*args):
        calls.append("eura")
        if len(calls) == 1:
            started.set()
            assert release.wait(4)
            if fail:
                raise ValueError("Testivirhe")
        return []

    monkeypatch.setattr("app.services.imports.fetch_eura_calls", fetch_eura)
    monkeypatch.setattr("app.services.imports.fetch_haeavustuksia_calls", lambda *args, **kwargs: [])
    monkeypatch.setattr(ui, "notify", lambda message, **kwargs: notifications.append(message))
    with _test_client(db_session, monkeypatch) as client:
        first_page = _page_client(client.get("/"))
        second_page = _page_client(client.get("/"))
        first_button = next(e for e in first_page.elements.values()
                            if isinstance(e, ui.button) and e.text == "Hae uudet hankkeet")
        second_button = next(e for e in second_page.elements.values()
                             if isinstance(e, ui.button) and e.text == "Hae uudet hankkeet")
        future = client.portal.start_task_soon(_click, first_page, "Hae uudet hankkeet")
        try:
            assert started.wait(3)
            assert not first_button.enabled
            assert first_button.props["loading"]
            # An event queued before the disabled state reached the browser.
            client.portal.call(_on_import_click, events.ClickEventArguments(sender=first_button, client=first_page))
            client.portal.call(_click, second_page, "Hae uudet hankkeet")
            assert "Hakujen tuonti on jo käynnissä." in notifications
            assert second_button.enabled
            response = client.post("/api/imports/run")
            assert response.status_code == 409
            assert response.json() == {"detail": "Hakujen tuonti on jo käynnissä."}
            assert calls == ["eura"]
        finally:
            release.set()
            future.result(timeout=5)
        assert first_button.enabled
        assert not first_button.props.get("loading")
        if fail:
            assert "Tuonti epäonnistui. Tarkista loki." in notifications
        else:
            assert "Uusia hankkeita ei löytynyt. Päivitettyjä: 0." in notifications
        # A new API import succeeds after either success or exception, using the same service lock.
        response = client.post("/api/imports/run")
        assert response.status_code == 200
        assert calls == ["eura", "eura"]
        assert response.json() == {
            "eura": {"created": 0, "updated": 0, "unchanged": 0},
            "haeavustuksia": {"created": 0, "updated": 0, "unchanged": 0},
        }
