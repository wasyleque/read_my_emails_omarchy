import sys

from mailvoice import crashlog


def test_unhandled_error_is_written_to_log(tmp_path, monkeypatch):
    log = tmp_path / "mailvoice.log"
    old_hook, old_thread_hook = sys.excepthook, crashlog.threading.excepthook
    try:
        crashlog.install(log)
        monkeypatch.setattr(crashlog, "log_path", lambda: log)
        try:
            raise ValueError("testowy błąd")
        except ValueError:
            crashlog.report(*sys.exc_info())
        for h in crashlog._logger.handlers:
            h.flush()
        assert "testowy błąd" in log.read_text(encoding="utf-8")
    finally:
        sys.excepthook, crashlog.threading.excepthook = old_hook, old_thread_hook
