from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_renders_placeholders():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    for text in (
        "HankeVAHTI",
        "Hae uudet hankkeet",
        "Hakuehdot",
        "Asetukset",
        "Uusia hankkeita",
        "Arvioimattomia hankkeita",
        "Osallistuttavia hankkeita",
        "Hylättyjä hankkeita",
        "Käynnissä olevia hankkeita",
    ):
        assert text in response.text


def test_import_endpoint_returns_counts(monkeypatch):
    expected = {
        "eura": {"created": 1, "updated": 0, "unchanged": 0},
        "haeavustuksia": {"created": 2, "updated": 0, "unchanged": 0},
    }
    monkeypatch.setattr("app.api.imports.run_imports", lambda db: expected)
    with TestClient(app) as client:
        response = client.post("/api/imports/run")
    assert response.status_code == 200
    assert response.json() == expected


def test_import_endpoint_reports_upstream_failure(monkeypatch):
    def fail(db):
        raise ValueError("Virheellinen lähdedata")

    monkeypatch.setattr("app.api.imports.run_imports", fail)
    with TestClient(app) as client:
        response = client.post("/api/imports/run")
    assert response.status_code == 502
    assert response.json() == {"detail": "Tietolähteiden tuonti epäonnistui"}
