"""Testy wykrywania modeli i konfiguracji Ollama w oknie Ustawień (SettingsDialog)."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from mailvoice.core.analyzer import Analysis, AnalyzerTransportError
from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig
from mailvoice.core.ollama_models import is_cloud_model
from mailvoice.ui.settings import SettingsDialog
from mailvoice.voice.tts import FakeSpeaker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeSecretStore:
    def __init__(self):
        self.secrets = {}

    def get(self, key):
        return self.secrets.get(key)

    def set(self, key, value):
        self.secrets[key] = value

    def delete(self, key):
        self.secrets.pop(key, None)


def _wait_for_worker(worker, qapp):
    if worker:
        worker.wait(3000)
    for _ in range(10):
        qapp.processEvents()


def test_settings_ollama_tab_detection_and_populate(qapp, tmp_path):
    """Weryfikuje wykrywanie modeli, filtrowanie chmurowych i zapełnianie list wyboru."""
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(name="jan@firma.pl", host="imap.firma.pl", username="jan@firma.pl")
        ],
        ollama=OllamaConfig(
            model="qwen3:8b",
            polish_model="qooba/bielik-11b-v3.0-instruct",
        ),
    )
    secret_store = FakeSecretStore()

    def fake_fetch(url: str) -> list[str]:
        if "127.0.0.1" in url:
            return [
                "qwen3:8b",
                "llama3.2:3b",
                "qooba/bielik-11b-v3.0-instruct",
                "deepseek-coder:6.7b",
                "my-private-model:cloud",
                "other:cloud",
            ]
        return []

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )
    dlg._ollama_fetch_fn = fake_fetch
    dlg.show()
    qapp.processEvents()

    # Przełącz na zakładkę Ollama (indeks 3) - uruchamia automatyczne wykrywanie
    dlg.tabs.setCurrentIndex(3)
    _wait_for_worker(dlg.ollama_detect_worker, qapp)

    assert dlg.ollama_detection is not None
    assert dlg.ollama_detection.local_ok is True
    assert "Znaleziono serwer" in dlg.lbl_detect_status.text()

    # Model ogólny: tylko modele do analizy (bez deepseek-coder i bez cloud)
    models_in_combo = [dlg.cb_model.itemData(i) for i in range(dlg.cb_model.count())]
    assert "qwen3:8b" in models_in_combo
    assert "llama3.2:3b" in models_in_combo
    assert "deepseek-coder:6.7b" not in models_in_combo
    assert "my-private-model:cloud" not in models_in_combo
    assert "other:cloud" not in models_in_combo

    # Zalecany model ma dopisek "(zalecany)"
    assert "(zalecany)" in dlg.cb_model.itemText(0)

    # Model polski: pierwsza opcja to "taki sam jak ogólny", Bielik oznaczony jako zalecany
    assert dlg.cb_polish_model.itemData(0) == ""
    polish_models = [dlg.cb_polish_model.itemData(i) for i in range(dlg.cb_polish_model.count())]
    assert "qooba/bielik-11b-v3.0-instruct" in polish_models
    bielik_idx = polish_models.index("qooba/bielik-11b-v3.0-instruct")
    assert "(zalecany do PL)" in dlg.cb_polish_model.itemText(bielik_idx)

    # Włączenie checkboxa "Pokaż wszystkie modele"
    dlg.chk_all_models.setChecked(True)
    qapp.processEvents()

    models_with_all = [dlg.cb_model.itemData(i) for i in range(dlg.cb_model.count())]
    assert "deepseek-coder:6.7b" in models_with_all
    # Ale modele chmurowe BEZWZGLĘDNIE nie mogą się pojawić!
    assert "my-private-model:cloud" not in models_with_all
    assert "other:cloud" not in models_with_all
    assert not any(is_cloud_model(m) for m in models_with_all if m)

    dlg.close()


def test_settings_ollama_missing_model_warning_and_save_confirm(qapp, tmp_path, monkeypatch):
    """Weryfikuje ostrzeżenie o niezainstalowanym modelu i pytanie przy zapisie."""
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(name="jan@firma.pl", host="imap.firma.pl", username="jan@firma.pl")
        ],
        ollama=OllamaConfig(
            model="mistral:7b",  # Model niezainstalowany na serwerze
            polish_model="mistral:7b",
        ),
        vip_senders=["vip@example.com"],
        keywords=["wazne"],
    )
    secret_store = FakeSecretStore()

    def fake_fetch(url: str) -> list[str]:
        if "127.0.0.1" in url:
            return ["qwen3:8b", "llama3.2:3b"]
        return []

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )
    dlg._ollama_fetch_fn = fake_fetch
    dlg.show()
    qapp.processEvents()

    dlg.tabs.setCurrentIndex(3)
    _wait_for_worker(dlg.ollama_detect_worker, qapp)

    # Niezainstalowany model powinien być na liście oznaczony ostrzeżeniem
    assert dlg.cb_model.currentData() == "mistral:7b"
    assert "niezainstalowany" in dlg.cb_model.currentText()
    assert not dlg.lbl_model_warning.isHidden()
    assert "nie jest zainstalowany" in dlg.lbl_model_warning.text()

    # Wybór zainstalowanego modelu ukrywa ostrzeżenie
    idx_qwen = -1
    for i in range(dlg.cb_model.count()):
        if dlg.cb_model.itemData(i) == "qwen3:8b":
            idx_qwen = i
            break
    assert idx_qwen >= 0
    dlg.cb_model.setCurrentIndex(idx_qwen)
    qapp.processEvents()
    assert dlg.lbl_model_warning.isHidden()

    # Powrót do niezainstalowanego modelu ponownie włącza ostrzeżenie
    idx_mistral = -1
    for i in range(dlg.cb_model.count()):
        if dlg.cb_model.itemData(i) == "mistral:7b":
            idx_mistral = i
            break
    assert idx_mistral >= 0
    dlg.cb_model.setCurrentIndex(idx_mistral)
    qapp.processEvents()
    assert not dlg.lbl_model_warning.isHidden()

    # 1. Próba zapisu z niezainstalowanym modelem - użytkownik wybiera "Nie"
    questions = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: (questions.append(args), QMessageBox.StandardButton.No)[1],
    )
    dlg._on_save()
    assert len(questions) == 1
    assert "mistral:7b" in str(questions[0])
    # Zapis nie doszedł do skutku
    assert not config_path.exists()

    # 2. Próba zapisu z niezainstalowanym modelem - użytkownik potwierdza "Tak"
    saved_configs = []
    dlg.on_config_saved = lambda c: saved_configs.append(c)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    dlg._on_save()
    assert len(saved_configs) == 1
    saved_cfg = saved_configs[0]
    assert saved_cfg.ollama.model == "mistral:7b"
    assert saved_cfg.ollama.prefer == "local"  # Ponieważ lokalny serwer odpowiedział
    # Pozostałe ustawienia zachowane
    assert saved_cfg.vip_senders == ["vip@example.com"]
    assert saved_cfg.keywords == ["wazne"]
    assert config_path.exists()

    dlg.close()


def test_settings_ollama_server_not_found(qapp, tmp_path):
    """Weryfikuje zachowanie przy braku serwera Ollama."""
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig()
    secret_store = FakeSecretStore()

    def fake_fetch_fail(url: str) -> list[str]:
        return []

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )
    dlg._ollama_fetch_fn = fake_fetch_fail
    dlg.show()
    qapp.processEvents()

    dlg.tabs.setCurrentIndex(3)
    _wait_for_worker(dlg.ollama_detect_worker, qapp)

    assert "Nie znaleziono" in dlg.lbl_detect_status.text()
    assert not dlg.lbl_ollama_guide.isHidden()
    # Sekcja zaawansowana z adresami URL powinna zostać rozwinięta
    assert dlg.adv_ollama.isChecked() is True

    dlg.close()


def test_settings_ollama_check_model_button(qapp, tmp_path):
    """Weryfikuje działanie przycisku 'Sprawdź model'."""
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(ollama=OllamaConfig(model="qwen3:8b"))
    secret_store = FakeSecretStore()

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )

    class DummyClientOk:
        def __init__(self, c):
            self.cfg = c

        def classify(self, messages, model):
            return Analysis(importance=5, reason="Ważne", action="read_now", language="pl")

    dlg._ollama_client_factory = DummyClientOk

    # 1. Sukces
    dlg._on_check_model()
    _wait_for_worker(dlg.ollama_check_worker, qapp)

    assert "Model działa poprawnie" in dlg.lbl_check_result.text()

    # 2. Błąd
    class DummyClientFail:
        def __init__(self, c):
            self.cfg = c

        def classify(self, messages, model):
            raise AnalyzerTransportError("Serwery AI zawiodły: HTTP 404")

    dlg._ollama_client_factory = DummyClientFail
    dlg._on_check_model()
    _wait_for_worker(dlg.ollama_check_worker, qapp)

    assert "nie jest zainstalowany na serwerze Ollama" in dlg.lbl_check_result.text()

    dlg.close()


def test_settings_ollama_screenshot(qapp, tmp_path):
    """Zrzut ekranu zakładki Ollama (do docs/screenshots gdy flaga aktywna)."""
    config_path = tmp_path / "config.json"
    app_cfg = AppConfig(
        accounts=[
            AccountConfig(
                name="jan.kowalski@firma.pl",
                host="imap.firma.pl",
                username="jan.kowalski@firma.pl",
            )
        ],
        ollama=OllamaConfig(
            model="qwen3:8b",
            polish_model="qooba/bielik-11b-v3.0-instruct",
        ),
    )
    secret_store = FakeSecretStore()

    def fake_fetch(url: str) -> list[str]:
        return [
            "qwen3:8b",
            "llama3.2:3b",
            "qooba/bielik-11b-v3.0-instruct",
            "mistral:7b",
        ]

    dlg = SettingsDialog(
        config=app_cfg,
        config_path=config_path,
        secret_store=secret_store,
        speaker=FakeSpeaker(),
    )
    dlg._ollama_fetch_fn = fake_fetch
    dlg.show()
    qapp.processEvents()

    dlg.tabs.setCurrentIndex(3)
    _wait_for_worker(dlg.ollama_detect_worker, qapp)

    if os.environ.get("MAILVOICE_UPDATE_SCREENSHOTS") == "1":
        screenshot_path = Path("docs/screenshots/settings_ollama.png")
    else:
        screenshot_path = tmp_path / "settings_ollama.png"

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = dlg.grab()
    saved = pixmap.save(str(screenshot_path))
    dlg.close()

    assert saved is True
    assert screenshot_path.exists()
    assert screenshot_path.stat().st_size > 0
