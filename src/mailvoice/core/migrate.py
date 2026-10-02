"""Jednorazowe migracje stanu między wersjami programu."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

_TLS_FILES = ("server.crt", "server.key")
_DEVICE_COLUMNS = "id, name, token_hash, created_at, last_seen, revoked"


def migrate_server_state(config_dir: Path, data_dir: Path) -> list[str]:
    """Przenosi stan serwera dla telefonu z katalogu konfiguracji do katalogu danych.

    Wcześniejsza wersja okna głównego używała katalogu konfiguracji jako katalogu danych, więc
    certyfikat TLS, jego klucz i lista sparowanych telefonów leżały w ~/.config. Tryb headless
    szukał ich w katalogu danych. Certyfikat jest PRZENOSZONY (nie generowany od nowa), żeby jego
    odcisk się nie zmienił i sparowane telefony nadal działały.
    """
    done: list[str] = []
    if config_dir.resolve() == data_dir.resolve():
        return done
    data_dir.mkdir(parents=True, exist_ok=True)

    for name in _TLS_FILES:
        src, dst = config_dir / name, data_dir / name
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            done.append(f"przeniesiono {name}")

    old_db = config_dir / "mailvoice.db"
    if old_db.exists():
        copied = _copy_devices(old_db, data_dir / "mailvoice.db")
        _retire(old_db)
        if copied:
            done.append(f"przeniesiono sparowane urządzenia: {copied}")
    return done


def _copy_devices(old_db: Path, new_db: Path) -> int:
    src = sqlite3.connect(old_db)
    try:
        try:
            rows = src.execute(f"SELECT {_DEVICE_COLUMNS} FROM paired_devices").fetchall()
        except sqlite3.Error:
            return 0  # stara baza bez tabeli urządzeń
    finally:
        src.close()
    if not rows:
        return 0
    from mailvoice.core.devices import DeviceManager

    DeviceManager(new_db).close()  # tworzy tabelę, jeśli jej jeszcze nie ma
    dst = sqlite3.connect(new_db)
    try:
        before = dst.total_changes
        dst.executemany(
            f"INSERT OR IGNORE INTO paired_devices ({_DEVICE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        dst.commit()
        return dst.total_changes - before
    finally:
        dst.close()


def _retire(old_db: Path) -> None:
    """Odkłada starą bazę (z kopią zapasową), żeby migracja nie wznowiła usuniętych urządzeń."""
    try:
        conn = sqlite3.connect(old_db)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except sqlite3.Error:
        pass
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{old_db}{suffix}")
        if path.exists():
            os.replace(path, Path(f"{old_db}{suffix}.migrated"))
