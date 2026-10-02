"""Test przycisku „Sprawdź połączenie” w kreatorze (wątek ImapTestWorker) na atrapie klienta."""

import pytest

from mailvoice.core.imap_fetch import FetchError
from mailvoice.ui import wizard as wizard_mod


class _FakeClient:
    """Atrapa: ma TYLKO metody prawdziwego ImapToolsClient (nie ma login()/logout())."""

    instances: list["_FakeClient"] = []
    error: Exception | None = None

    def __init__(self, **kwargs) -> None:
        self.closed = False
        type(self).instances.append(self)

    def get_uidvalidity(self, folder: str) -> int:
        if type(self).error:
            raise type(self).error
        return 1

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _fake_client(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.error = None
    monkeypatch.setattr(wizard_mod, "ImapToolsClient", _FakeClient)


def _run(lang="pl"):
    worker = wizard_mod.ImapTestWorker("h", 993, "u", "p", True, lang)
    results = {"ok": 0, "err": [], "details": []}
    worker.finished_ok.connect(lambda: results.__setitem__("ok", results["ok"] + 1))
    worker.finished_error.connect(
        lambda msg, det: (results["err"].append(msg), results["details"].append(det))
    )
    worker.run()  # synchronicznie, bez uruchamiania wątku
    return results


def test_successful_connection_emits_ok_and_closes_client():
    results = _run()
    assert results["ok"] == 1 and results["err"] == []
    assert _FakeClient.instances[0].closed


def test_failed_login_emits_friendly_message_and_closes_client():
    _FakeClient.error = FetchError("IMAP4 login failed: [AUTHENTICATIONFAILED] Invalid credentials")
    results = _run()
    assert results["ok"] == 0 and len(results["err"]) == 1
    assert "Hasło lub login nie pasują" in results["err"][0]
    assert "Typ błędu: FetchError" in results["details"][0]
    assert _FakeClient.instances[0].closed


def test_worker_only_uses_methods_that_exist_on_real_client():
    """Regresja: kreator wołał nieistniejące client.login()/logout()."""
    from mailvoice.core.imap_fetch import ImapToolsClient

    for name in ("get_uidvalidity", "close"):
        assert hasattr(ImapToolsClient, name)
    assert not hasattr(ImapToolsClient, "login")
    src = open(wizard_mod.__file__, encoding="utf-8").read()
    assert "client.login(" not in src and "client.logout(" not in src
