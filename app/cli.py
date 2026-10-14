"""Servera puses komandas (N3).

Pirmā administratora iecelšana:
    python -m app.cli set-role janis@example.com ADMIN
Datu bāzes fails: vides mainīgais `AUTH_DB_PATH` (noklusējums `auth.db`).
"""

from __future__ import annotations

import argparse
import os
import sys

from app.db import Database, LastAdmin
from app.main import ROLES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="CRM servera komandas")
    commands = parser.add_subparsers(dest="command", required=True)
    set_role = commands.add_parser("set-role", help="Piešķirt lietotājam lomu")
    set_role.add_argument("email", help="Lietotāja e-pasts")
    set_role.add_argument("role", choices=ROLES, help="Jaunā loma")
    args = parser.parse_args(argv)

    db = Database(os.environ.get("AUTH_DB_PATH", "auth.db"))
    user_id = db.find_user_id(args.email.strip().lower())
    if user_id is None:
        print("Lietotājs ar šādu e-pastu nav atrasts.", file=sys.stderr)
        return 1
    try:
        db.set_role(user_id, args.role)
    except LastAdmin:
        print("Vienīgajam administratoram lomu noņemt nevar.", file=sys.stderr)
        return 1
    print(f"Loma mainīta: {args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
