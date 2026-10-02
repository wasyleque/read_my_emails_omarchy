"""Blokada pojedynczej instancji aplikacji (GUI i tryb headless nie mogą działać równolegle).

Dwie kopie czytałyby tę samą pocztę i dublowały powiadomienia głosowe. Blokada plikowa systemu
operacyjnego zwalnia się sama przy zamknięciu lub awarii procesu — nie zostają „martwe” blokady.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import platformdirs


def lock_path() -> Path:
    return Path(platformdirs.user_data_dir("mailvoice")) / "mailvoice.lock"


class InstanceLock:
    """Trzymaj referencję do obiektu przez cały czas działania programu."""

    def __init__(self, handle) -> None:
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()
            self._handle = None


def acquire_instance_lock(path: Path | None = None) -> InstanceLock | None:
    """Zwraca blokadę albo None, gdy inna instancja już działa."""
    path = path or lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")  # noqa: SIM115 — trzymany do końca procesu
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return InstanceLock(handle)
