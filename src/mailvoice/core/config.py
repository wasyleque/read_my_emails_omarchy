import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class AccountConfig:
    name: str
    host: str
    port: int = 993
    username: str = ""
    use_ssl: bool = True
    folders: List[str] = field(default_factory=lambda: ["INBOX"])
    sent_folder: str = "Sent"


@dataclass
class OllamaConfig:
    lan_url: str = "http://192.168.1.50:11434"
    local_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    polish_model: str = "qooba/bielik-11b-v3.0-instruct"
    prefer: str = "lan"  # 'lan' or 'local'
    timeout_s: float = 60.0


@dataclass
class AppConfig:
    accounts: List[AccountConfig] = field(default_factory=list)
    analysis_prompt: str = ""
    vip_senders: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    blocked_senders: List[str] = field(default_factory=list)
    interval_minutes: int = 10
    notify_mode: str = "beep"  # 'beep' or 'ask'
    beep_repeat_minutes: int = 5
    ask_retry_minutes: int = 15
    importance_threshold: int = 6
    backlog_days: int = 30
    language: str = "auto"  # 'auto', 'pl', or 'en'
    ollama: OllamaConfig = field(default_factory=OllamaConfig)

    def to_dict(self) -> dict:
        """Convert AppConfig to dictionary representation."""
        result = {}
        for key, value in self.__dict__.items():
            if key == "accounts":
                result[key] = [account.__dict__ for account in value]
            elif key == "ollama":
                result[key] = value.__dict__
            else:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        """Create AppConfig from dictionary, handling defaults and validation."""
        # Handle nested objects
        accounts = []
        if "accounts" in d:
            for account_data in d["accounts"]:
                known_acc = AccountConfig.__dataclass_fields__
                account = AccountConfig(**{k: v for k, v in account_data.items() if k in known_acc})
                accounts.append(account)

        ollama = OllamaConfig()
        if "ollama" in d:
            known = OllamaConfig.__dataclass_fields__
            ollama = OllamaConfig(**{k: v for k, v in d["ollama"].items() if k in known})

        # Handle validation
        notify_mode = d.get("notify_mode", "beep")
        if notify_mode not in ("beep", "ask"):
            raise ValueError(f"Invalid notify_mode: {notify_mode}")

        if ollama.prefer not in ("lan", "local"):
            raise ValueError(f"Invalid ollama.prefer value: {ollama.prefer}")

        language = d.get("language", "auto")
        if language not in ("auto", "pl", "en"):
            raise ValueError(f"Invalid language: {language}")

        interval_minutes = d.get("interval_minutes", 10)
        if interval_minutes < 1:
            raise ValueError(f"Interval minutes must be >= 1, got: {interval_minutes}")

        importance_threshold = d.get("importance_threshold", 6)
        if not (0 <= importance_threshold <= 10):
            raise ValueError(
                f"Importance threshold must be between 0 and 10, got: {importance_threshold}"
            )

        ask_retry_minutes = d.get("ask_retry_minutes", 15)
        if ask_retry_minutes < 1:
            raise ValueError(f"Ask retry minutes must be >= 1, got: {ask_retry_minutes}")

        # Create instance with defaults for missing fields
        return cls(
            accounts=accounts,
            analysis_prompt=d.get("analysis_prompt", ""),
            vip_senders=d.get("vip_senders", []),
            keywords=d.get("keywords", []),
            blocked_senders=d.get("blocked_senders", []),
            interval_minutes=interval_minutes,
            notify_mode=notify_mode,
            beep_repeat_minutes=d.get("beep_repeat_minutes", 5),
            ask_retry_minutes=ask_retry_minutes,
            importance_threshold=importance_threshold,
            backlog_days=d.get("backlog_days", 30),
            language=language,
            ollama=ollama,
        )


def save_config(cfg: AppConfig, path: Path) -> None:
    """Save configuration to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, ensure_ascii=False)


def load_config(path: Path) -> AppConfig:
    """Load configuration from JSON file. Returns default if file doesn't exist."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    except FileNotFoundError:
        # Return default config if file doesn't exist
        return AppConfig(accounts=[])
