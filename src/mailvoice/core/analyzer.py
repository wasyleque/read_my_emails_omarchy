import json
from dataclasses import dataclass
from typing import Dict, List

import httpx

from mailvoice.core.config import OllamaConfig
from mailvoice.core.textutil import truncate_for_llm


class AnalyzerError(Exception):
    """Bazowy wyjątek rzucany w przypadku błędów analizy."""

    pass


class AnalyzerTransportError(AnalyzerError):
    """Błąd komunikacji z serwerem Ollama (sieć, timeout, HTTP)."""

    pass


class AnalyzerFormatError(AnalyzerError):
    """Błąd formatu lub walidacji odpowiedzi z modelu Ollama."""

    pass


@dataclass(frozen=True)
class Analysis:
    importance: int
    reason: str
    action: str
    language: str


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "importance": {"type": "integer", "minimum": 0, "maximum": 10},
        "reason": {"type": "string"},
        "action": {"type": "string", "enum": ["read_now", "read_later", "ignore"]},
        "language": {"type": "string", "enum": ["pl", "en", "other"]},
    },
    "required": ["importance", "reason", "action", "language"],
}


def build_messages(
    user_description: str, sender: str, subject: str, body: str, rule_reasons: tuple[str, ...] = ()
) -> List[Dict]:
    """Build messages for Ollama analysis."""
    system_message = {
        "role": "system",
        "content": f"""Oceń ważność maila w skali 0-10 (0=nieważny, 10=krytyczny)
zgodnie z opisem użytkownika:
{user_description}

Zwracaj tylko JSON zgodny ze schematem:
{json.dumps(ANALYSIS_SCHEMA)}""",
    }

    user_content = f"Od: {sender}\nTemat: {subject}\nTreść:\n{truncate_for_llm(body, 1500)}"

    if rule_reasons:
        user_content += f"\n\nUzasadnienie reguł: {'; '.join(rule_reasons)}"

    user_message = {"role": "user", "content": user_content}

    return [system_message, user_message]


def pick_model(language: str, cfg: OllamaConfig) -> str:
    """Pick the appropriate model based on language."""
    if language == "pl":
        return cfg.polish_model
    return cfg.model


class OllamaClient:
    def __init__(self, cfg: OllamaConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self.transport = transport

    def classify(self, messages: List[Dict], model: str) -> Analysis:
        """Classify email using Ollama."""
        # Determine URL order based on preference
        urls = (
            [self.cfg.lan_url, self.cfg.local_url]
            if self.cfg.prefer == "lan"
            else [self.cfg.local_url, self.cfg.lan_url]
        )

        last_error = None

        for url in urls:
            try:
                # Prepare the request
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "format": ANALYSIS_SCHEMA,
                    "options": {"temperature": 0},
                }

                # Make the request
                with httpx.Client(transport=self.transport, timeout=self.cfg.timeout_s) as client:
                    response = client.post(f"{url}/api/chat", json=payload)
                    response.raise_for_status()

                return _parse_response(response)
            except httpx.HTTPError as e:
                last_error = e
                continue

        # If we get here, all URLs failed
        raise AnalyzerTransportError(f"All Ollama endpoints failed: {last_error}")

    def chat_text(self, messages: List[Dict], model: str) -> str:
        """Wysyła zapytanie do Ollamy i zwraca treść odpowiedzi jako zwykły tekst."""
        urls = (
            [self.cfg.lan_url, self.cfg.local_url]
            if self.cfg.prefer == "lan"
            else [self.cfg.local_url, self.cfg.lan_url]
        )

        last_error = None

        for url in urls:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.2},
                }

                with httpx.Client(transport=self.transport, timeout=self.cfg.timeout_s) as client:
                    response = client.post(f"{url}/api/chat", json=payload)
                    response.raise_for_status()

                data = response.json()
                content = str(data.get("message", {}).get("content", "")).strip()
                return content
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last_error = e
                continue

        raise AnalyzerTransportError(f"All Ollama endpoints failed: {last_error}")

    def chat_json(self, messages: List[Dict], model: str, schema: dict) -> dict:
        """Wysyła zapytanie do Ollamy ze zdefiniowanym schematem JSON i zwraca słownik."""
        urls = (
            [self.cfg.lan_url, self.cfg.local_url]
            if self.cfg.prefer == "lan"
            else [self.cfg.local_url, self.cfg.lan_url]
        )

        last_error = None

        for url in urls:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "format": schema,
                    "options": {"temperature": 0.1},
                }

                with httpx.Client(transport=self.transport, timeout=self.cfg.timeout_s) as client:
                    response = client.post(f"{url}/api/chat", json=payload)
                    response.raise_for_status()

                data = response.json()
                content = str(data.get("message", {}).get("content", "")).strip()
                try:
                    return json.loads(content)
                except (ValueError, json.JSONDecodeError) as exc:
                    raise AnalyzerFormatError(f"Niepoprawny JSON z Ollamy: {exc}") from exc
            except (httpx.HTTPError, KeyError) as e:
                last_error = e
                continue

        raise AnalyzerTransportError(f"All Ollama endpoints failed: {last_error}")


def _parse_response(response: httpx.Response) -> Analysis:
    """Parsuje odpowiedź /api/chat; każdy błąd formatu -> AnalyzerFormatError."""
    try:
        result = json.loads(response.json()["message"]["content"])
        importance = max(0, min(10, int(result["importance"])))
        reason = str(result["reason"])
        action = result["action"]
        language = result["language"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AnalyzerFormatError(f"Niepoprawna odpowiedź Ollamy: {exc}") from exc
    if action not in ("read_now", "read_later", "ignore"):
        action = "read_later"
    if language not in ("pl", "en", "other"):
        language = "other"
    return Analysis(importance=importance, reason=reason, action=action, language=language)
