import sqlite3

import pytest


@pytest.fixture
def set_role(tmp_path):
    """Maina lomu tieši datu bāzē (N3); testu `app` izmanto `tmp_path / "auth.db"`."""

    def apply(user_id: int, role: str) -> None:
        with sqlite3.connect(tmp_path / "auth.db") as conn:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    return apply
