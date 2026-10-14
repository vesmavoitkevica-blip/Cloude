"""SQLite glabātuve lietotājiem un sesijām (CR-4) un organizācijām (F1)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    reg_number TEXT UNIQUE,
    address TEXT,
    responsible_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

ORGANIZATION_COLUMNS = (
    "id, name, reg_number, address, responsible_user_id, created_at, updated_at"
)

# Milisekundes, lai `updatedAt` mainītos arī pēc ātras secīgas rediģēšanas.
NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


class DuplicateRegNumber(Exception):
    """Reģistrācijas numurs jau pieder citai organizācijai."""


LATVIAN_ALPHABET = "aābcčdeēfgģhiījkķlļmnņoprsštuūvzž"
_LATVIAN_ORDER = {letter: index for index, letter in enumerate(LATVIAN_ALPHABET)}


def _casefold(value: str | None) -> str | None:
    return value.casefold() if value is not None else None


def latvian_sort_key(text: str) -> tuple[int, ...]:
    """Kārto pēc latviešu alfabēta: Ābele pirms Bērziem, nevis aiz Z."""
    return tuple(
        _LATVIAN_ORDER.get(char, len(LATVIAN_ALPHABET) + ord(char)) for char in text.casefold()
    )


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        # SQLite LOWER/LIKE nešķiro burtus tikai ASCII diapazonā; latviešu burtiem vajag Python.
        conn.create_function("casefold", 1, _casefold, deterministic=True)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create_user(self, email: str, password_hash: str) -> int | None:
        """Atgriež jaunā lietotāja ID vai None, ja e-pasts jau ir reģistrēts."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, password_hash),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def find_user(self, email: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()

    def create_session(self, token_hash: str, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)",
                (token_hash, user_id),
            )

    def find_session_user_id(self, token_hash: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return row["user_id"] if row else None

    def user_exists(self, user_id: int) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is not None

    def create_organization(
        self, name: str, reg_number: str | None, address: str | None, responsible_user_id: int
    ) -> sqlite3.Row:
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    f"INSERT INTO organizations (name, reg_number, address, responsible_user_id,"
                    f" created_at, updated_at) VALUES (?, ?, ?, ?, {NOW}, {NOW})",
                    (name, reg_number, address, responsible_user_id),
                )
                return self._get_organization(conn, cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise DuplicateRegNumber from exc

    def update_organization(
        self,
        org_id: int,
        name: str,
        reg_number: str | None,
        address: str | None,
        responsible_user_id: int | None,
    ) -> sqlite3.Row | None:
        """Atgriež atjaunoto organizāciju vai None, ja tādas nav."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    "UPDATE organizations SET name = ?, reg_number = ?, address = ?,"
                    " responsible_user_id = COALESCE(?, responsible_user_id),"
                    f" updated_at = {NOW} WHERE id = ?",
                    (name, reg_number, address, responsible_user_id, org_id),
                )
                if cursor.rowcount == 0:
                    return None
                return self._get_organization(conn, org_id)
        except sqlite3.IntegrityError as exc:
            raise DuplicateRegNumber from exc

    def get_organization(self, org_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return self._get_organization(conn, org_id)

    def search_organizations(
        self, query: str | None, responsible_user_id: int | None
    ) -> list[sqlite3.Row]:
        sql = f"SELECT {ORGANIZATION_COLUMNS} FROM organizations WHERE 1 = 1"
        params: list = []
        if query:
            # instr, nevis LIKE, lai % un _ meklējamajā tekstā nebūtu aizstājējzīmes.
            sql += " AND (instr(casefold(name), ?) > 0 OR instr(coalesce(reg_number, ''), ?) > 0)"
            params += [query.casefold(), query]
        if responsible_user_id is not None:
            sql += " AND responsible_user_id = ?"
            params.append(responsible_user_id)
        with self.connect() as conn:
            rows = conn.execute(sql + " ORDER BY id", params).fetchall()
        return sorted(rows, key=lambda row: latvian_sort_key(row["name"]))

    @staticmethod
    def _get_organization(conn: sqlite3.Connection, org_id: int) -> sqlite3.Row | None:
        return conn.execute(
            f"SELECT {ORGANIZATION_COLUMNS} FROM organizations WHERE id = ?", (org_id,)
        ).fetchone()
