"""Encrypt and decrypt the agent desk's state so it can be kept on a public git
branch (durable, versioned) without exposing the decisions.

    python -m congress.secure_state keygen
    python -m congress.secure_state encrypt SRC DST     # key from AGENTS_STATE_KEY
    python -m congress.secure_state decrypt SRC DST
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("AGENTS_STATE_KEY", "").strip()
    if not key:
        raise SystemExit("AGENTS_STATE_KEY is not set")
    return Fernet(key.encode())


def encrypt_file(src: Path, dst: Path) -> None:
    Path(dst).write_bytes(_fernet().encrypt(Path(src).read_bytes()))


def decrypt_file(src: Path, dst: Path) -> None:
    try:
        Path(dst).write_bytes(_fernet().decrypt(Path(src).read_bytes()))
    except InvalidToken:
        raise SystemExit("Could not decrypt the saved state: wrong AGENTS_STATE_KEY or a corrupted file")


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:] or ["help"]
    if cmd == "keygen":
        print(Fernet.generate_key().decode())
    elif cmd == "encrypt" and len(rest) == 2:
        encrypt_file(Path(rest[0]), Path(rest[1]))
    elif cmd == "decrypt" and len(rest) == 2:
        decrypt_file(Path(rest[0]), Path(rest[1]))
    else:
        raise SystemExit(__doc__)
