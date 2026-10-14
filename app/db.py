"""SQLite glabātuve: lietotāji un sesijas (CR-4, N3), organizācijas (F1), mijiedarbības (F3)
un pieprasījumi (F4)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    name TEXT,
    role TEXT NOT NULL DEFAULT 'EMPLOYEE'
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
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    occurred_on TEXT NOT NULL,
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    next_step TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS interactions_by_organization
    ON interactions (organization_id, occurred_on DESC, id DESC);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS requests_by_due_date ON requests (due_date, id);
"""

# Kolonnas, kas pievienotas pēc tabulas izveides; vecām datu bāzēm tās pievieno ar ALTER TABLE.
USER_MIGRATIONS = {
    "name": "ALTER TABLE users ADD COLUMN name TEXT",
    "role": "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'EMPLOYEE'",
}
USER_COLUMNS = "id, email, name, role"


class LastAdmin(Exception):
    """Vienīgajam administratoram nevar noņemt lomu."""


ORGANIZATION_COLUMNS = (
    "id, name, reg_number, address, responsible_user_id, created_at, updated_at"
)

INTERACTION_SELECT = """
SELECT i.id, i.organization_id, o.name AS organization_name,
       o.responsible_user_id AS organization_responsible_id, i.author_id, i.occurred_on,
       i.type, i.summary, i.next_step, i.created_at, i.updated_at
FROM interactions i JOIN organizations o ON o.id = i.organization_id
"""
NEWEST_FIRST = " ORDER BY i.occurred_on DESC, i.id DESC"

REQUEST_SELECT = """
SELECT r.id, r.organization_id, o.name AS organization_name,
       o.responsible_user_id AS organization_responsible_id, r.title, r.description,
       r.due_date, r.status, r.created_at, r.updated_at
FROM requests r JOIN organizations o ON o.id = r.organization_id
"""
# Kavēts = nav atbildēts un termiņš pirms šodienas (F9 datu noteikumi).
REQUEST_OPEN = "r.status != 'ANSWERED'"

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
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            for column, statement in USER_MIGRATIONS.items():
                if column not in existing:
                    conn.execute(statement)

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

    def create_user(
        self, email: str, password_hash: str, name: str | None = None
    ) -> sqlite3.Row | None:
        """Atgriež jauno lietotāju vai None, ja e-pasts jau ir reģistrēts."""
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
                    (email, password_hash, name),
                )
                return conn.execute(
                    f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()

    def find_user_id(self, email: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        return row["id"] if row else None

    def list_users(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(f"SELECT {USER_COLUMNS} FROM users ORDER BY email").fetchall()

    def set_role(self, user_id: int, role: str) -> sqlite3.Row | None:
        """Atgriež atjaunoto lietotāju vai None, ja tāda nav. LastAdmin, ja tas ir pēdējais."""
        with self.connect() as conn:
            # Pārbaude un maiņa vienā transakcijā, lai divi vienlaicīgi pieprasījumi
            # nevarētu noņemt lomu abiem pēdējiem administratoriem.
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                return None
            if user["role"] == "ADMIN" and role != "ADMIN":
                (admins,) = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'").fetchone()
                if admins <= 1:
                    raise LastAdmin
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            return conn.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()

    def find_user(self, email: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()

    def create_session(self, token_hash: str, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)",
                (token_hash, user_id),
            )

    def find_session_user(self, token_hash: str) -> sqlite3.Row | None:
        """Sesijas lietotājs ar pašreizējo lomu (loma netiek kopēta sesijā, N3)."""
        with self.connect() as conn:
            return conn.execute(
                "SELECT u.id, u.email, u.name, u.role FROM sessions s"
                " JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
                (token_hash,),
            ).fetchone()

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

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

    def create_interaction(
        self,
        organization_id: int,
        author_id: int,
        occurred_on: str,
        type: str,
        summary: str,
        next_step: str | None,
    ) -> sqlite3.Row:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO interactions (organization_id, author_id, occurred_on, type, summary,"
                f" next_step, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, {NOW}, {NOW})",
                (organization_id, author_id, occurred_on, type, summary, next_step),
            )
            return self._get_interaction(conn, cursor.lastrowid)

    def update_interaction(
        self, interaction_id: int, occurred_on: str, type: str, summary: str, next_step: str | None
    ) -> sqlite3.Row | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE interactions SET occurred_on = ?, type = ?, summary = ?, next_step = ?,"
                f" updated_at = {NOW} WHERE id = ?",
                (occurred_on, type, summary, next_step, interaction_id),
            )
            return self._get_interaction(conn, interaction_id)

    def get_interaction(self, interaction_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return self._get_interaction(conn, interaction_id)

    def organization_interactions(self, organization_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                INTERACTION_SELECT + " WHERE i.organization_id = ?" + NEWEST_FIRST,
                (organization_id,),
            ).fetchall()

    def latest_interactions(
        self, author_id: int | None, limit: int, responsible_user_id: int | None = None
    ) -> list[sqlite3.Row]:
        conditions, params = [], []
        if author_id is not None:
            conditions.append("i.author_id = ?")
            params.append(author_id)
        if responsible_user_id is not None:
            conditions.append("o.responsible_user_id = ?")
            params.append(responsible_user_id)
        sql = INTERACTION_SELECT + (" WHERE " + " AND ".join(conditions) if conditions else "")
        with self.connect() as conn:
            return conn.execute(sql + NEWEST_FIRST + " LIMIT ?", (*params, limit)).fetchall()

    @staticmethod
    def _get_interaction(conn: sqlite3.Connection, interaction_id: int) -> sqlite3.Row | None:
        return conn.execute(INTERACTION_SELECT + " WHERE i.id = ?", (interaction_id,)).fetchone()

    def create_request(
        self,
        organization_id: int,
        title: str,
        description: str | None,
        due_date: str,
        status: str,
    ) -> sqlite3.Row:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO requests (organization_id, title, description, due_date, status,"
                f" created_at, updated_at) VALUES (?, ?, ?, ?, ?, {NOW}, {NOW})",
                (organization_id, title, description, due_date, status),
            )
            return self._get_request(conn, cursor.lastrowid)

    def update_request(
        self, request_id: int, title: str, description: str | None, due_date: str, status: str
    ) -> sqlite3.Row | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE requests SET title = ?, description = ?, due_date = ?, status = ?,"
                f" updated_at = {NOW} WHERE id = ?",
                (title, description, due_date, status, request_id),
            )
            return self._get_request(conn, request_id)

    def get_request(self, request_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return self._get_request(conn, request_id)

    def search_requests(
        self,
        today: str,
        statuses: list[str] | None = None,
        overdue: bool | None = None,
        due_until: str | None = None,
        responsible_user_id: int | None = None,
        organization_id: int | None = None,
    ) -> list[sqlite3.Row]:
        """Datumi ir ISO virknes, tāpēc tos var salīdzināt kā tekstu."""
        conditions: list[str] = []
        params: list = []
        if statuses:
            conditions.append(f"r.status IN ({', '.join('?' * len(statuses))})")
            params += statuses
        if overdue is not None:
            conditions.append(f"{'' if overdue else 'NOT '}({REQUEST_OPEN} AND r.due_date < ?)")
            params.append(today)
        if due_until is not None:
            conditions.append(f"{REQUEST_OPEN} AND r.due_date <= ?")
            params.append(due_until)
        if responsible_user_id is not None:
            conditions.append("o.responsible_user_id = ?")
            params.append(responsible_user_id)
        if organization_id is not None:
            conditions.append("r.organization_id = ?")
            params.append(organization_id)
        sql = REQUEST_SELECT
        if conditions:
            sql += " WHERE " + " AND ".join(f"({c})" for c in conditions)
        with self.connect() as conn:
            return conn.execute(sql + " ORDER BY r.due_date, r.id", params).fetchall()

    @staticmethod
    def _get_request(conn: sqlite3.Connection, request_id: int) -> sqlite3.Row | None:
        return conn.execute(REQUEST_SELECT + " WHERE r.id = ?", (request_id,)).fetchone()
