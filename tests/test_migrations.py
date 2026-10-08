"""Verify migrations against temporary databases, preserving existing user data."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_ai_summary_migration_preserves_existing_data(tmp_path):
    database = tmp_path / "migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}",
           "OPENAI_API_KEY": "", "GEMINI_API_KEY": ""}
    root = Path(__file__).resolve().parents[1]

    def upgrade(revision):
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=root, env=env, check=True, capture_output=True, text=True,
        )

    upgrade("0004_haeavustuksia_search_criteria")
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            INSERT INTO funding_calls (id, source, source_id, title, raw_data, created_at, updated_at)
            VALUES (1, 'EURA', 'migration-test', 'Tallennettu haku', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO evaluations (id, funding_call_id, status, suitability_score, suitability_summary, created_at, updated_at)
            VALUES (1, 1, 'PARTICIPATE', 80, 'Perustelu', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO participations (id, funding_call_id, stage, notes, created_at, updated_at)
            VALUES (1, 1, 'PLANNING', 'Muistiinpano', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO search_profiles (id, name, keywords, excluded_keywords, active)
            VALUES (1, 'HankeVAHTI: relevanssi', '["koulutus"]', '[]', 1);
        """)
        tables = ("funding_calls", "evaluations", "participations", "search_profiles")
        before = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}

    upgrade("0005_ai_summary")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_ai_summary"
        assert connection.execute("SELECT ai_summary FROM evaluations").fetchone() == (None,)
        for table in tables:
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            if table == "evaluations":
                rows = [row[:-1] for row in rows]  # SQLite appends the new nullable column.
            assert rows == before[table]


def test_decision_and_match_migration_upgrade_downgrade_preserve_legacy_data(tmp_path):
    database = tmp_path / "decisions.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}",
           "OPENAI_API_KEY": "", "GEMINI_API_KEY": ""}
    root = Path(__file__).resolve().parents[1]

    def migrate(direction, revision):
        subprocess.run([sys.executable, "-m", "alembic", direction, revision],
                       cwd=root, env=env, check=True, capture_output=True, text=True)

    migrate("upgrade", "0005_ai_summary")
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            INSERT INTO funding_calls (id, source, source_id, title, raw_data, created_at, updated_at)
            VALUES (1, 'EURA', 'legacy', 'Vanha hylätty', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO evaluations (id, funding_call_id, status, suitability_score, suitability_summary,
                                     ai_summary, created_at, updated_at)
            VALUES (1, 1, 'REJECTED', 60, 'Vanha pisteytys', 'AI-teksti', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO participations (id, funding_call_id, stage, notes, responsible_person, next_action, created_at, updated_at)
            VALUES (1, 1, 'PLANNING', 'Muistiinpano', 'Risto', 'Palaveri', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO search_profiles (id, name, keywords, excluded_keywords, active)
            VALUES (1, 'HankeVAHTI: relevanssi', '["koulutus"]', '[]', 1);
        """)
        tables = ("funding_calls", "evaluations", "participations", "search_profiles")
        columns = {table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")] for table in tables}
        before = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}

    for direction, revision in [("upgrade", "head"), ("downgrade", "0005_ai_summary"), ("upgrade", "head")]:
        migrate(direction, revision)
        with sqlite3.connect(database) as connection:
            for table in tables:
                assert connection.execute(f"SELECT {', '.join(columns[table])} FROM {table}").fetchall() == before[table]
            current_columns = {row[1]: row for row in connection.execute("PRAGMA table_info(evaluations)")}
            new_columns = {"rejected_at", "matched_keywords", "matched_excluded_keywords"}
            if direction == "upgrade":
                assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006_evaluation_decisions_matches"
                assert connection.execute("SELECT rejected_at, matched_keywords, matched_excluded_keywords FROM evaluations").fetchone() == (None, None, None)
                assert all(current_columns[name][3] == 0 for name in new_columns)
                # Downgrade poistaa vain uudet tiedot; vanhat sarakkeet säilyvät.
                connection.execute("UPDATE evaluations SET rejected_at = '2026-10-08 06:34:00', matched_keywords = '[\"koulutus\"]', matched_excluded_keywords = '[]'")
            else:
                assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_ai_summary"
                assert not new_columns.intersection(current_columns)
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
