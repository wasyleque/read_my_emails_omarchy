"""Moduł inteligentnego wyszukiwania maili za pomocą AI (aisearch)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from mailvoice.core.analyzer import AnalyzerError, OllamaClient, pick_model
from mailvoice.core.config import AppConfig
from mailvoice.core.store import MailIndexRecord, Store
from mailvoice.core.threading import clean_subject


@dataclass(frozen=True)
class MailRef:
    """Referencja do wiadomości e-mail w skrzynce i indeksie."""

    account: str
    folder: str
    uidvalidity: int
    uid: int
    message_id: str | None
    subject: str
    sender: str
    date: str | None


@dataclass(frozen=True)
class SearchHit:
    """Trafienie wyszukiwania AI z oceną prawdopodobieństwa i uzasadnieniem."""

    mail_ref: MailRef
    score: float
    why_probable: str
    snippet: str
    confidence: str = "średnia"  # 'wysoka' | 'średnia' | 'niska'


QUERY_EXPANSION_SCHEMA = {
    "type": "object",
    "properties": {
        "senders": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["senders", "keywords"],
}

RERANK_SCHEMA = {
    "type": "object",
    "properties": {
        "ranked_uids": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "uid": {"type": "integer"},
                    "score": {"type": "number"},
                    "confidence": {"type": "string", "enum": ["wysoka", "średnia", "niska"]},
                    "why_probable": {"type": "string"},
                },
                "required": ["uid", "score", "confidence", "why_probable"],
            },
        }
    },
    "required": ["ranked_uids"],
}


def _expand_query(llm: OllamaClient, query: str, model: str) -> tuple[list[str], list[str]]:
    """Rozszerza zapytanie w języku naturalnym o synonimy i nazwiska przy użyciu LLM."""
    system_prompt = (
        "Jesteś asystentem wyszukiwania w poczcie. Twoim zadaniem jest wyodrębnienie z zapytania "
        "użytkownika potencjalnych nazwisk/nadawców (senders) oraz słów kluczowych wraz z ich "
        "odmianami i synonimami (keywords).\n"
        "Zwróć wynik w formacie JSON zgodnym ze schematem."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Zapytanie użytkownika: {query}"},
    ]

    try:
        res = llm.chat_json(messages, model, QUERY_EXPANSION_SCHEMA)
        if isinstance(res, dict):
            senders = [str(s).strip() for s in res.get("senders", []) if str(s).strip()]
            keywords = [str(k).strip() for k in res.get("keywords", []) if str(k).strip()]
            if senders or keywords:
                return senders, keywords
    except (AnalyzerError, Exception):
        pass

    # Fallback: tokenizacja zapytania
    words = [w.strip() for w in query.split() if len(w.strip()) >= 3]
    return [], words or [query.strip()]


def search(
    store: Store,
    llm: OllamaClient | None = None,
    client: Any = None,
    query: str = "",
    days: int | None = None,
    limit: int = 5,
    config: AppConfig | None = None,
) -> list[SearchHit]:
    """Wyszukuje wiadomości za pomocą zapytania w języku naturalnym z re-rankingiem LLM."""
    query = query.strip()
    if not query:
        return []

    actual_llm = llm if isinstance(llm, OllamaClient) else client
    if actual_llm is None and isinstance(llm, OllamaClient):
        actual_llm = llm

    cfg = config or AppConfig()
    model = pick_model("pl", cfg.ollama)
    now = datetime.now(timezone.utc)

    # 1. Okno czasowe
    effective_days = days if (days is not None and days >= 1) else cfg.digest_days
    since_dt = now - timedelta(days=effective_days)
    since_iso = since_dt.isoformat()

    # 2. Krok (a): Rozszerzenie zapytania przez LLM
    senders, keywords = _expand_query(actual_llm, query, model) if actual_llm else ([], [query])

    # 3. Krok (b): Pobranie kandydatów z SQLite FTS5 / LIKE
    candidates = store.search_candidates(
        keywords=keywords,
        senders=senders,
        since=since_iso,
        limit=20,
    )
    if not candidates:
        return []

    # 4. Krok (c): Re-ranking przez LLM
    candidate_lines = []
    uid_map: dict[int, MailIndexRecord] = {}
    for c in candidates:
        uid_map[c.uid] = c
        summary = c.summary or c.why or clean_subject(c.subject)
        dt_str = c.date[:10] if c.date else ""
        candidate_lines.append(
            f"- UID: {c.uid}, Data: {dt_str}, Od: {c.sender}, Temat: {c.subject}\n"
            f"  Treść/opis: {summary}"
        )

    system_prompt = (
        "Oceń stopień dopasowania kandydatów wiadomości e-mail do zapytania użytkownika.\n"
        "Dla każdego pasującego kandydata zwróć:\n"
        "- uid: identyfikator wiadomości\n"
        "- score: liczba od 0.0 do 1.0 (im wyższa, tym większe prawdopodobieństwo)\n"
        "- confidence: 'wysoka', 'średnia' lub 'niska'\n"
        "- why_probable: jedno krótkie zdanie uzasadnienia po polsku (dlaczego to ten mail)\n"
        "Zwróć format JSON zgodny ze schematem."
    )
    user_content = f"Zapytanie użytkownika: {query}\n\nKandydaci wiadomości:\n" + "\n".join(
        candidate_lines
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    hits: list[SearchHit] = []
    ranked_success = False

    try:
        if actual_llm is not None:
            res = actual_llm.chat_json(messages, model, RERANK_SCHEMA)
            if isinstance(res, dict) and "ranked_uids" in res:
                for item in res["ranked_uids"]:
                    u_id = item.get("uid")
                    if u_id in uid_map:
                        rec = uid_map[u_id]
                        score = float(item.get("score", 0.5))
                        conf = str(item.get("confidence", "średnia"))
                        if conf not in ("wysoka", "średnia", "niska"):
                            conf = "średnia"
                        why = str(item.get("why_probable") or "Prawdopodobne dopasowanie tematu.")
                        snippet = rec.summary or rec.why or clean_subject(rec.subject)
                        mail_ref = MailRef(
                            account=rec.account,
                            folder=rec.folder,
                            uidvalidity=rec.uidvalidity,
                            uid=rec.uid,
                            message_id=rec.message_id,
                            subject=rec.subject,
                            sender=rec.sender,
                            date=rec.date,
                        )
                        hits.append(
                            SearchHit(
                                mail_ref=mail_ref,
                                score=score,
                                why_probable=why,
                                snippet=snippet,
                                confidence=conf,
                            )
                        )
                if hits:
                    ranked_success = True
    except (AnalyzerError, Exception):
        # Błąd LLM -> degradacja do samego FTS bez wyjątku
        pass

    if not ranked_success:
        # Fallback: kolejność z FTS/indeksu
        for idx, rec in enumerate(candidates):
            score = max(0.1, 1.0 - (idx * 0.05))
            conf = "wysoka" if idx == 0 else "średnia"
            why = "Dopasowanie słów kluczowych w indeksie wiadomości."
            snippet = rec.summary or rec.why or clean_subject(rec.subject)
            mail_ref = MailRef(
                account=rec.account,
                folder=rec.folder,
                uidvalidity=rec.uidvalidity,
                uid=rec.uid,
                message_id=rec.message_id,
                subject=rec.subject,
                sender=rec.sender,
                date=rec.date,
            )
            hits.append(
                SearchHit(
                    mail_ref=mail_ref,
                    score=score,
                    why_probable=why,
                    snippet=snippet,
                    confidence=conf,
                )
            )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def fetch_mail_preview(
    client_factory: Any,
    account: str,
    folder: str,
    uid: int,
) -> str | None:
    """Pobiera pełną treść TYLKO jednej wybranej wiadomości z IMAP (BODY.PEEK)."""
    if not client_factory:
        return None
    try:
        # Opcjonalne dociągnięcie na wyraźne żądanie użytkownika
        client = client_factory(account)
        if hasattr(client, "fetch_message_body"):
            return client.fetch_message_body(folder, uid)
    except Exception:
        pass
    return None
