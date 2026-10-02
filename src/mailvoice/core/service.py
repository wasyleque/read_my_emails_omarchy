"""Warstwa usługowa aplikacji MailVoice (Service) - pętla sterująca bez Qt i audio."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

from mailvoice.core.aisearch import SearchHit, search
from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig
from mailvoice.core.contacts import (
    ContactCard,
    build_contact_card,
    resolve_contact,
)
from mailvoice.core.digest import Digest, build_digest
from mailvoice.core.imap_fetch import FetchError, ImapToolsClient, MailboxClient
from mailvoice.core.pipeline import (
    CycleResult,
    PendingBacklog,
    PipelineDeps,
    ProcessedMail,
    load_pending_backlog,
    run_cycle,
)
from mailvoice.core.pipeline import (
    resolve_backlog as pipeline_resolve_backlog,
)
from mailvoice.core.scheduler import NotificationAction, Notifier
from mailvoice.core.secrets import SecretStore, SecretStoreError
from mailvoice.core.store import Store


@dataclass(frozen=True)
class NewImportant:
    """Zdarzenie pojawienia się nowych ważnych wiadomości."""

    items: list[ProcessedMail]
    action: NotificationAction


@dataclass(frozen=True)
class BacklogQuestion:
    """Zdarzenie pytania o zaległe ważne wiadomości."""

    items: list[ProcessedMail | PendingBacklog]
    count: int


@dataclass(frozen=True)
class BeepReminder:
    """Zdarzenie ponowienia sygnału dźwiękowego."""

    count: int


@dataclass(frozen=True)
class AskReminder:
    """Zdarzenie ponowienia pytania głosowego w trybie ask."""

    count: int


@dataclass(frozen=True)
class ServiceError:
    """Zdarzenie wystąpienia błędu podczas pracy serwisu."""

    message: str
    account: str | None = None


@dataclass(frozen=True)
class DigestReady:
    """Zdarzenie wygenerowania podsumowania tematów."""

    digest: Digest


@dataclass(frozen=True)
class ContactCardReady:
    """Zdarzenie wygenerowania karty kontaktu."""

    card: ContactCard | None
    address_or_name: str


@dataclass(frozen=True)
class SearchResults:
    """Zdarzenie znalezienia wiadomości przez AI."""

    query: str
    hits: list[SearchHit]


# Alias dla kompatybilności wstecznej
Error = ServiceError

Event = (
    NewImportant
    | BacklogQuestion
    | BeepReminder
    | AskReminder
    | ServiceError
    | DigestReady
    | ContactCardReady
    | SearchResults
)


class MailService:
    """Główna usługa koordynująca sprawdzanie poczty, sekrety, model AI i powiadomienia."""

    def __init__(
        self,
        config: AppConfig,
        store: Store,
        secret_store: SecretStore,
        ollama_client: OllamaClient,
        client_factory: Callable[[AccountConfig], MailboxClient] | None = None,
        notifier: Notifier | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.secret_store = secret_store
        self.ollama_client = ollama_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._client_factory = client_factory or self._create_imap_client

        self.notifier = notifier or Notifier(
            notify_mode=config.notify_mode,
            beep_repeat_minutes=config.beep_repeat_minutes,
            ask_retry_minutes=config.ask_retry_minutes,
            clock=self._clock,
        )

        self._events: deque[Event] = deque()
        self._listeners: list[Callable[[Event], None]] = []
        self.last_cycle_time: datetime | None = None
        self._has_run_first_cycle = False

        # Sprawdzenie zaległości oczekujących w bazie z poprzedniej sesji
        self._check_startup_backlog()

    def _create_imap_client(self, account: AccountConfig) -> MailboxClient:
        """Domyślna fabryka pobierająca hasło z SecretStore tuż przed połączeniem."""
        try:
            secret = self.secret_store.get(account.name)
        except SecretStoreError as exc:
            raise FetchError(
                f"Błąd odczytu hasła z magazynu sekretów dla konta '{account.name}': {exc}"
            ) from exc

        if not secret:
            raise FetchError(
                f"Brak hasła w magazynie sekretów dla konta '{account.name}'. "
                "Skonfiguruj hasło w ustawieniach."
            )

        return ImapToolsClient(
            host=account.host,
            port=account.port,
            username=account.username,
            password=secret,
            use_ssl=account.use_ssl,
        )

    def _check_startup_backlog(self) -> None:
        """Wykrywa nieobsłużone zaległości oczekujące w bazie po restarcie aplikacji."""
        pending = load_pending_backlog(self.store)
        if pending:
            evt = BacklogQuestion(items=list(pending), count=len(pending))
            self._emit(evt)

    def add_listener(self, listener: Callable[[Event], None]) -> None:
        """Rejestruje funkcję zwrotną wywoływaną przy każdym nowym zdarzeniu."""
        self._listeners.append(listener)

    def _emit(self, event: Event) -> None:
        self._events.append(event)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

    def poll_events(self) -> list[Event]:
        """Pobiera i czyści listę oczekujących zdarzeń."""
        events: list[Event] = []
        while self._events:
            events.append(self._events.popleft())
        return events

    def trigger_cycle(self, check_backlog: bool = False) -> CycleResult:
        """Ręczne lub natychmiastowe wyzwolenie pełnego cyklu sprawdzania poczty."""
        now = self._clock()
        deps = PipelineDeps(
            config=self.config,
            store=self.store,
            client_factory=self._client_factory,
            ollama_client=self.ollama_client,
        )

        should_check_backlog = check_backlog or (not self._has_run_first_cycle)
        result = run_cycle(deps, check_backlog=should_check_backlog)
        self.last_cycle_time = now
        self._has_run_first_cycle = True

        for err in result.errors:
            self._emit(ServiceError(message=err))

        if result.backlog_important:
            self._emit(
                BacklogQuestion(
                    items=result.backlog_important,
                    count=len(result.backlog_important),
                )
            )

        if result.important:
            action = self.notifier.on_important_mail(len(result.important))
            self._emit(NewImportant(items=result.important, action=action))

        return result

    def tick(self, now: datetime | None = None) -> None:
        """Krok zegara wołany okresowo przez timer interfejsu lub wątek roboczy."""
        current_time = now or self._clock()

        # 1. Sprawdzanie czy nadszedł czas na kolejny cykl pobierania
        interval_delta = timedelta(minutes=self.config.interval_minutes)
        if self.last_cycle_time is None or (current_time - self.last_cycle_time) >= interval_delta:
            self.trigger_cycle()

        # 2. Sprawdzanie maszyny powiadomień
        action = self.notifier.tick()
        if action == NotificationAction.BEEP:
            self._emit(BeepReminder(count=self.notifier.pending_count))
        elif action == NotificationAction.ASK:
            self._emit(AskReminder(count=self.notifier.pending_count))

    def user_confirm(self) -> None:
        """Użytkownik potwierdził odbiór / odsłuchanie."""
        self.notifier.user_confirm()

    def user_decline(self) -> None:
        """Użytkownik odroczył pytanie w trybie ask."""
        self.notifier.user_decline()

    def user_dismiss(self) -> None:
        """Użytkownik wyciszył powiadomienie."""
        self.notifier.user_dismiss()

    def resolve_backlog(
        self,
        accepted: bool,
        items: Sequence[ProcessedMail | PendingBacklog] | None = None,
    ) -> None:
        """Rozstrzyga status zaległości po odpowiedzi użytkownika (tak/nie)."""
        to_resolve = items if items is not None else load_pending_backlog(self.store)
        pipeline_resolve_backlog(self.store, to_resolve, accepted)

    def request_digest(self, days: int | None = None) -> Digest:
        """Generuje podsumowanie wątków za podaną liczbę dni (lub domyślnie z configu)."""
        effective_days = days if (days is not None and days >= 1) else self.config.digest_days
        now = self._clock()
        since_dt = now - timedelta(days=effective_days)
        digest = build_digest(
            store=self.store,
            client=self.ollama_client,
            config=self.config,
            since=since_dt,
            until=now,
        )
        self._emit(DigestReady(digest=digest))
        return digest

    def contact_context(
        self,
        address_or_name: str,
        days: int | None = None,
    ) -> ContactCard | None:
        """Pobiera kontekst kontaktu (kartę) na podstawie adresu lub nazwy."""
        contact = resolve_contact(self.store, address_or_name)
        card = None
        if contact is not None:
            effective_days = days if (days is not None and days >= 1) else self.config.digest_days
            card = build_contact_card(
                store=self.store,
                llm=self.ollama_client,
                contact=contact,
                days=effective_days,
            )
        self._emit(ContactCardReady(card=card, address_or_name=address_or_name))
        return card

    def ai_search(
        self,
        query: str,
        days: int | None = None,
        limit: int = 5,
    ) -> list[SearchHit]:
        """Wyszukuje wiadomości AI w indeksie z uwzględnieniem okna czasowego."""
        effective_days = days if (days is not None and days >= 1) else self.config.digest_days
        hits = search(
            store=self.store,
            llm=self.ollama_client,
            query=query,
            days=effective_days,
            limit=limit,
            config=self.config,
        )
        self._emit(SearchResults(query=query, hits=hits))
        return hits
