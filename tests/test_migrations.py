"""Verify that the AI-summary migration preserves existing user data."""

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

    upgrade("head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_ai_summary"
        assert connection.execute("SELECT ai_summary FROM evaluations").fetchone() == (None,)
        for table in tables:
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            if table == "evaluations":
                rows = [row[:-1] for row in rows]  # SQLite appends the new nullable column.
            assert rows == before[table]
