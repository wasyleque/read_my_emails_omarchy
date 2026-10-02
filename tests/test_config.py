import json

import pytest

from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig, load_config, save_config


def test_account_config_defaults():
    """Test AccountConfig with default values."""
    account = AccountConfig(name="Test", host="imap.test.com")
    assert account.name == "Test"
    assert account.host == "imap.test.com"
    assert account.port == 993
    assert account.username == ""
    assert account.use_ssl is True
    assert account.folders == ["INBOX"]
    assert account.sent_folder == "Sent"


def test_account_config_custom_values():
    """Test AccountConfig with custom values."""
    account = AccountConfig(
        name="Work",
        host="imap.work.com",
        port=143,
        username="user@work.com",
        use_ssl=False,
        folders=["INBOX", "Important"],
        sent_folder="Sent Items",
    )
    assert account.name == "Work"
    assert account.host == "imap.work.com"
    assert account.port == 143
    assert account.username == "user@work.com"
    assert account.use_ssl is False
    assert account.folders == ["INBOX", "Important"]
    assert account.sent_folder == "Sent Items"


def test_ollama_config_defaults():
    """Test OllamaConfig with default values."""
    ollama = OllamaConfig()
    assert ollama.lan_url == "http://192.168.1.50:11434"
    assert ollama.local_url == "http://127.0.0.1:11434"
    assert ollama.model == "qwen3:8b"
    assert ollama.polish_model == "qooba/bielik-11b-v3.0-instruct"
    assert ollama.prefer == "lan"
    assert ollama.timeout_s == 60.0


def test_ollama_config_custom_values():
    """Test OllamaConfig with custom values."""
    ollama = OllamaConfig(
        lan_url="http://192.168.1.100:11434",
        local_url="http://localhost:11434",
        model="mistral:7b",
        polish_model="polish-mistral:7b",
        prefer="local",
        timeout_s=30.0,
    )
    assert ollama.lan_url == "http://192.168.1.100:11434"
    assert ollama.local_url == "http://localhost:11434"
    assert ollama.model == "mistral:7b"
    assert ollama.polish_model == "polish-mistral:7b"
    assert ollama.prefer == "local"
    assert ollama.timeout_s == 30.0


def test_app_config_defaults():
    """Test AppConfig with default values."""
    config = AppConfig(accounts=[])
    assert config.accounts == []
    assert config.analysis_prompt == ""
    assert config.vip_senders == []
    assert config.keywords == []
    assert config.blocked_senders == []
    assert config.interval_minutes == 10
    assert config.notify_mode == "beep"
    assert config.beep_repeat_minutes == 5
    assert config.backlog_days == 30
    assert config.language == "auto"
    assert isinstance(config.ollama, OllamaConfig)


def test_app_config_custom_values():
    """Test AppConfig with custom values."""
    accounts = [AccountConfig(name="Test", host="imap.test.com")]
    ollama = OllamaConfig(prefer="local")

    config = AppConfig(
        accounts=accounts,
        analysis_prompt="Analyze important emails",
        vip_senders=["boss@company.com"],
        keywords=["urgent", "important"],
        blocked_senders=["spam@spam.com"],
        interval_minutes=15,
        notify_mode="ask",
        beep_repeat_minutes=10,
        backlog_days=60,
        language="pl",
        ollama=ollama,
    )

    assert config.accounts == accounts
    assert config.analysis_prompt == "Analyze important emails"
    assert config.vip_senders == ["boss@company.com"]
    assert config.keywords == ["urgent", "important"]
    assert config.blocked_senders == ["spam@spam.com"]
    assert config.interval_minutes == 15
    assert config.notify_mode == "ask"
    assert config.beep_repeat_minutes == 10
    assert config.backlog_days == 60
    assert config.language == "pl"
    assert config.ollama.prefer == "local"


def test_app_config_to_dict():
    """Test AppConfig.to_dict() method."""
    accounts = [AccountConfig(name="Test", host="imap.test.com")]
    config = AppConfig(accounts=accounts)

    data = config.to_dict()
    assert "accounts" in data
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["name"] == "Test"
    assert data["accounts"][0]["host"] == "imap.test.com"


def test_app_config_from_dict():
    """Test AppConfig.from_dict() method."""
    data = {
        "accounts": [{"name": "Test", "host": "imap.test.com"}],
        "analysis_prompt": "Test prompt",
        "vip_senders": ["test@example.com"],
        "keywords": ["keyword1", "keyword2"],
        "blocked_senders": ["spam@example.com"],
        "interval_minutes": 5,
        "notify_mode": "ask",
        "beep_repeat_minutes": 3,
        "backlog_days": 15,
        "language": "pl",
    }

    config = AppConfig.from_dict(data)
    assert len(config.accounts) == 1
    assert config.accounts[0].name == "Test"
    assert config.analysis_prompt == "Test prompt"
    assert config.vip_senders == ["test@example.com"]
    assert config.keywords == ["keyword1", "keyword2"]
    assert config.blocked_senders == ["spam@example.com"]
    assert config.interval_minutes == 5
    assert config.notify_mode == "ask"
    assert config.beep_repeat_minutes == 3
    assert config.backlog_days == 15
    assert config.language == "pl"


def test_app_config_from_dict_ignore_unknown_keys():
    """Test AppConfig.from_dict() ignores unknown keys."""
    data = {
        "accounts": [{"name": "Test", "host": "imap.test.com"}],
        "unknown_key": "should_be_ignored",
        "interval_minutes": 10,
    }

    config = AppConfig.from_dict(data)
    assert len(config.accounts) == 1
    assert config.interval_minutes == 10


def test_app_config_from_dict_validation_errors():
    """Test AppConfig.from_dict() validation errors."""
    # Test invalid notify_mode
    with pytest.raises(ValueError, match="Invalid notify_mode"):
        AppConfig.from_dict(
            {"accounts": [{"name": "Test", "host": "imap.test.com"}], "notify_mode": "invalid_mode"}
        )

    # Test invalid prefer
    with pytest.raises(ValueError, match="Invalid ollama.prefer"):
        AppConfig.from_dict({"ollama": {"prefer": "invalid_prefer"}})

    # Test invalid language
    with pytest.raises(ValueError, match="Invalid language"):
        AppConfig.from_dict(
            {"accounts": [{"name": "Test", "host": "imap.test.com"}], "language": "de"}
        )

    # Test invalid interval_minutes
    with pytest.raises(ValueError, match="Interval minutes must be >= 1"):
        AppConfig.from_dict(
            {"accounts": [{"name": "Test", "host": "imap.test.com"}], "interval_minutes": 0}
        )


def test_save_config(tmp_path):
    """Test save_config function."""
    config = AppConfig(accounts=[AccountConfig(name="Test", host="imap.test.com")])
    path = tmp_path / "config.json"

    save_config(config, path)

    # Verify file was created and contains expected data
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "accounts" in data
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["name"] == "Test"
    # Verify password is not in the saved config (as required)
    assert "password" not in data


def test_load_config_default(tmp_path):
    """Test load_config returns default when file doesn't exist."""
    path = tmp_path / "nonexistent.json"

    config = load_config(path)
    assert isinstance(config, AppConfig)
    assert config.accounts == []


def test_load_config_round_trip(tmp_path):
    """Test round-trip save/load functionality."""
    original_config = AppConfig(
        accounts=[AccountConfig(name="Test", host="imap.test.com")],
        analysis_prompt="Test prompt",
        interval_minutes=15,
    )

    path = tmp_path / "config.json"
    save_config(original_config, path)

    loaded_config = load_config(path)

    assert len(loaded_config.accounts) == 1
    assert loaded_config.accounts[0].name == "Test"
    assert loaded_config.analysis_prompt == "Test prompt"
    assert loaded_config.interval_minutes == 15


def test_load_config_with_existing_file(tmp_path):
    """Test load_config with existing file."""
    config_data = {
        "accounts": [{"name": "Work", "host": "imap.work.com"}],
        "analysis_prompt": "Analyze work emails",
        "interval_minutes": 20,
    }

    path = tmp_path / "config.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    loaded_config = load_config(path)

    assert len(loaded_config.accounts) == 1
    assert loaded_config.accounts[0].name == "Work"
    assert loaded_config.analysis_prompt == "Analyze work emails"
    assert loaded_config.interval_minutes == 20


def test_ollama_prefer_validated_and_unknown_keys_ignored():
    with pytest.raises(ValueError):
        AppConfig.from_dict({"ollama": {"prefer": "cloud"}})
    cfg = AppConfig.from_dict({"ollama": {"prefer": "local", "bogus": 1}})
    assert cfg.ollama.prefer == "local"


def test_account_unknown_keys_ignored():
    cfg = AppConfig.from_dict({"accounts": [{"name": "x", "host": "h", "bogus": 1}]})
    assert cfg.accounts[0].host == "h"


def test_importance_threshold_validation():
    # Domyślna wartość to 6
    cfg = AppConfig.from_dict({})
    assert cfg.importance_threshold == 6

    # Poprawne wartości graniczne
    cfg_min = AppConfig.from_dict({"importance_threshold": 0})
    assert cfg_min.importance_threshold == 0
    cfg_max = AppConfig.from_dict({"importance_threshold": 10})
    assert cfg_max.importance_threshold == 10

    # Niepoprawne wartości
    with pytest.raises(ValueError, match="Importance threshold must be between 0 and 10"):
        AppConfig.from_dict({"importance_threshold": -1})

    with pytest.raises(ValueError, match="Importance threshold must be between 0 and 10"):
        AppConfig.from_dict({"importance_threshold": 11})


def test_ask_retry_minutes_validation():
    # Domyślna wartość to 15
    cfg = AppConfig.from_dict({})
    assert cfg.ask_retry_minutes == 15

    # Poprawna wartość
    cfg_custom = AppConfig.from_dict({"ask_retry_minutes": 30})
    assert cfg_custom.ask_retry_minutes == 30

    # Niepoprawna wartość < 1
    with pytest.raises(ValueError, match="Ask retry minutes must be >= 1"):
        AppConfig.from_dict({"ask_retry_minutes": 0})


def test_server_config_defaults_and_validation():
    """Weryfikuje domyślne wartości, serializację i walidację ServerConfig."""

    # Domyślne wartości
    cfg_def = AppConfig()
    assert cfg_def.server.enabled is False
    assert cfg_def.server.port == 8765
    assert cfg_def.server.bind == ""
    assert cfg_def.server.max_devices == 5

    # Wczytanie ze słownika bez klucza "server" (migracja starych baz)
    loaded_legacy = AppConfig.from_dict({})
    assert loaded_legacy.server.enabled is False

    # Niestandardowe wartości i round-trip
    custom_dict = {
        "server": {
            "enabled": True,
            "port": 9000,
            "bind": "192.168.1.100",
            "max_devices": 10,
        }
    }
    cfg_custom = AppConfig.from_dict(custom_dict)
    assert cfg_custom.server.enabled is True
    assert cfg_custom.server.port == 9000
    assert cfg_custom.server.bind == "192.168.1.100"
    assert cfg_custom.server.max_devices == 10

    roundtrip = AppConfig.from_dict(cfg_custom.to_dict())
    assert roundtrip.server == cfg_custom.server

    # Błędny port
    with pytest.raises(ValueError, match="Server port must be between 1 and 65535"):
        AppConfig.from_dict({"server": {"port": 0}})

    with pytest.raises(ValueError, match="Server port must be between 1 and 65535"):
        AppConfig.from_dict({"server": {"port": 70000}})

    # Błędna liczba urządzeń
    with pytest.raises(ValueError, match="Server max_devices must be >= 1"):
        AppConfig.from_dict({"server": {"max_devices": 0}})
