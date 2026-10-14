"""Paroļu jaukšana un sesiju marķieri (CR-4).

Izmanto `hashlib.scrypt` no standarta bibliotēkas, jo kursa vides attēlā nav
`bcrypt` vai `argon2` pakotņu.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LENGTH = 64


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_LENGTH
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    digest = _scrypt(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))


# Izmanto, ja e-pasts nav atrasts, lai atbildes laiks neatklātu, vai konts eksistē.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> tuple[str, str]:
    """Atgriež (marķieris sīkdatnei, tā jaucējvērtība datu bāzei)."""
    token = secrets.token_urlsafe(32)
    return token, hash_session_token(token)
