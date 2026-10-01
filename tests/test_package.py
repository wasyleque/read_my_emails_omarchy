"""Testy sprawdzające poprawność importu pakietu mailvoice."""


def test_package_import():
    """Weryfikacja importowalności głównych modułów pakietu mailvoice."""
    import mailvoice
    import mailvoice.core
    import mailvoice.ui
    import mailvoice.ui.main_window
    import mailvoice.voice

    assert mailvoice.__version__ == "0.1.0"
    assert mailvoice.ui.main_window.MainWindow is not None
