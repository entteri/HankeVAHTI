"""Both draft features survive upgrades and edits independently."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from nicegui import ui
import pytest
from sqlalchemy import create_engine, inspect

from app.db.base import Base
from app.services.application_drafts import list_application_drafts, save_application_draft
from app.services.eura_application_drafts import (
    get_application_draft as get_eura_draft,
    save_application_draft as save_eura_draft,
)
from app.services.application_text import ApplicationTextResult
from tests.test_ai_summary import _selected_call
from tests.test_application_text import edit
from tests.test_funding_calls import _test_client
from tests.test_relevance_ui import _click, _page_client


@pytest.mark.parametrize("start", ["master", "prototype"])
def test_upgrade_preserves_both_origins(tmp_path, start):
    path = tmp_path / "upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}",
           "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}

    def migrate(direction, revision):
        subprocess.run([sys.executable, "-m", "alembic", direction, revision],
                       cwd=Path(__file__).resolve().parents[1], env=env, check=True,
                       capture_output=True, text=True)

    migrate("upgrade", "0008_application_drafts" if start == "master" else "0007_multiple_search_criteria")
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO funding_calls (id, source, source_id, title, raw_data, created_at, updated_at) "
                   "VALUES (1, 'EURA', 'test', 'Haku', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO evaluations (id, funding_call_id, status, suitability_score, ai_summary, created_at, updated_at) "
                   "VALUES (1, 1, 'PARTICIPATE', 80, 'Tallennettu arvio', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        if start == "master":
            db.executemany("INSERT INTO application_drafts (id, funding_call_id, title, content, created_at, updated_at) "
                           "VALUES (?, 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                           [(3, 'Ensimmäinen', 'Oma teksti'), (7, 'Toinen', 'Toinen teksti')])
        else:
            # Reproduce the actual old prototype schema and stamp, not the
            # revised migration: existing installations have already run it.
            db.execute("CREATE TABLE application_drafts (id INTEGER PRIMARY KEY, funding_call_id INTEGER NOT NULL "
                       "REFERENCES funding_calls(id) ON DELETE CASCADE, content_json JSON NOT NULL, "
                       "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
                       "CONSTRAINT uq_application_drafts_funding_call_id UNIQUE (funding_call_id))")
            content = json.dumps({"project_context": "Oma idea", "fields": {"public_summary": "Tiivistelmä"},
                                  "confirmed_fields": ["public_summary"], "additional_information": {}})
            db.execute("INSERT INTO application_drafts VALUES (9, 1, ?, '2026-10-01', '2026-10-02')", (content,))
            db.execute("UPDATE alembic_version SET version_num='0008_application_draft'")
        saved = db.execute("SELECT * FROM application_drafts ORDER BY id").fetchall()
        other_tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                "AND name NOT IN ('application_drafts', 'alembic_version')")]
        before = {t: db.execute(f'SELECT * FROM "{t}"').fetchall() for t in other_tables}

    migrate("upgrade", "head")
    migrate("upgrade", "head")  # repeated startup/update is safe
    target = "application_drafts" if start == "master" else "eura_application_drafts"
    with sqlite3.connect(path) as db:
        assert db.execute(f"SELECT * FROM {target} ORDER BY id").fetchall() == saved
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0010_merge_notification_and_application_drafts"
        )
        for table, rows in before.items():
            assert db.execute(f'SELECT * FROM "{table}"').fetchall() == rows
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    engine = create_engine(env["DATABASE_URL"])
    inspector = inspect(engine)
    for table in ("application_drafts", "eura_application_drafts"):
        assert {c["name"] for c in inspector.get_columns(table)} == set(Base.metadata.tables[table].columns.keys())
    engine.dispose()

    # Rolling back the EURA feature must keep master's text drafts.
    with sqlite3.connect(path) as db:
        text_before = db.execute("SELECT * FROM application_drafts ORDER BY id").fetchall()
    migrate("downgrade", "0008_application_drafts")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM application_drafts ORDER BY id").fetchall() == text_before
    migrate("upgrade", "head")


def test_two_text_drafts_and_eura_draft_can_be_edited_independently(db_session):
    call = _selected_call(db_session)
    first = save_application_draft(db_session, call.id, "Ensimmäinen", "Teksti 1")
    second = save_application_draft(db_session, call.id, "Toinen", "Teksti 2")
    save_eura_draft(db_session, call.id, {"fields": {"public_summary": "EURA tiivistelmä"}})
    save_application_draft(db_session, call.id, "Otsikko", "Muokattu", draft_id=first.id)
    save_eura_draft(db_session, call.id, {"fields": {"public_summary": "Muokattu EURA"}})
    db_session.expire_all()
    drafts = {d.id: (d.title, d.content) for d in list_application_drafts(db_session, call.id)}
    assert drafts == {first.id: ("Otsikko", "Muokattu"), second.id: ("Toinen", "Teksti 2")}
    assert get_eura_draft(db_session, call.id).content_json["fields"]["public_summary"] == "Muokattu EURA"


def test_master_ui_save_reload_and_ai_suggestion_preserve_eura(db_session, monkeypatch):
    call = _selected_call(db_session)
    save_eura_draft(db_session, call.id, {"fields": {"public_summary": "Säilytettävä EURA"}})
    monkeypatch.setattr("app.ui.application_text.format_application_text",
                        lambda *args: ApplicationTextResult("AI:n tekstiehdotus", "", None))
    with _test_client(db_session, monkeypatch) as client:
        page = _page_client(client.get("/hankkeet"))
        client.portal.call(_click, page, "Muotoile hakemustekstiä")
        client.portal.call(edit, page, "Hakemuksen osion kysymys tai otsikko", "Otsikko")
        client.portal.call(edit, page, "Oma hakemustekstiluonnos", "Oma teksti")
        client.portal.call(_click, page, "Tallenna luonnos")
        client.portal.call(_click, page, "Muotoile teksti")
        client.portal.call(_click, page, "Käytä tekoälyn ehdotusta")
        client.portal.call(_click, page, "Tallenna luonnos")
        fresh_page = _page_client(client.get("/hankkeet"))
        client.portal.call(_click, fresh_page, "Muotoile hakemustekstiä")
        client.portal.call(_click, fresh_page, "Avaa luonnos")
        editor = next(e for e in fresh_page.elements.values() if isinstance(e, ui.textarea)
                      and e.props.get("label") == "Oma hakemustekstiluonnos")
        assert editor.value == "AI:n tekstiehdotus"
        assert any(isinstance(e, ui.button) and e.text == "Luo hankehakemus" for e in fresh_page.elements.values())
    db_session.expire_all()
    assert len(list_application_drafts(db_session, call.id)) == 1
    assert get_eura_draft(db_session, call.id).content_json["fields"]["public_summary"] == "Säilytettävä EURA"
