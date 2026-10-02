"""Zabezpieczenia przed przypadkowym trafieniem danych osobistych do repozytorium."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_blocks_personal_data():
    lines = (ROOT / ".gitignore").read_text().splitlines()
    for pattern in ("config.json", "*.db", "*.sqlite", "*.eml", "*.mbox", ".env", "*.vault"):
        assert pattern in lines, f"brak {pattern} w .gitignore"


def test_default_config_path_is_not_relative_to_cwd():
    src = (ROOT / "src/mailvoice/ui/main_window.py").read_text()
    assert 'Path("config.json")' not in src  # nie zapisuj configu w bieżącym katalogu
