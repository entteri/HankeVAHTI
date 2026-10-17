import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def test_upgrade_downgrade_preserves_existing_data_and_enforces_draft_constraints(tmp_path):
    database = tmp_path / "draft-migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}",
           "OPENAI_API_KEY": "", "GEMINI_API_KEY": ""}
    root = Path(__file__).resolve().parents[1]

    def migrate(direction, revision):
        subprocess.run([sys.executable, "-m", "alembic", direction, revision],
                       cwd=root, env=env, check=True, capture_output=True, text=True)

    migrate("upgrade", "0007_multiple_search_criteria")
    with sqlite3.connect(database) as conn:
        conn.executescript("""
            INSERT INTO funding_calls (id, source, source_id, title, raw_data, created_at, updated_at)
            VALUES (1, 'EURA', 'migration-test', 'Vanha haku', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO evaluations (id, funding_call_id, status, suitability_score, suitability_summary, ai_summary,
                                     matched_keywords, matched_excluded_keywords, rejected_at, created_at, updated_at)
            VALUES (1, 1, 'REJECTED', 80, 'Perustelu', 'AI arvio', '["koulutus"]', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO participations (id, funding_call_id, stage, notes, created_at, updated_at)
            VALUES (1, 1, 'PLANNING', 'Muistiinpano', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        """)
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")]
        before = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
    migrate("upgrade", "head")
    with sqlite3.connect(database) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for table in tables:
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == before[table]
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0009_draft_compatibility"
        sql = "INSERT INTO eura_application_drafts (funding_call_id, content_json, created_at, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        conn.execute(sql, (1, json.dumps({"project_context": "idea"})))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, (1, "{}"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, (999, "{}"))
        conn.execute("INSERT INTO funding_calls (id, source, source_id, title, raw_data, created_at, updated_at) VALUES (2, 'EURA', 'delete', 'Poistettava', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        conn.execute(sql, (2, "{}"))
        conn.execute("DELETE FROM funding_calls WHERE id=2")
        assert conn.execute("SELECT COUNT(*) FROM eura_application_drafts WHERE funding_call_id=2").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    migrate("downgrade", "0007_multiple_search_criteria")
    with sqlite3.connect(database) as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='eura_application_drafts'").fetchall()
        for table in tables:
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == before[table]
    migrate("upgrade", "head")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eura_application_drafts").fetchone()[0] == 0
