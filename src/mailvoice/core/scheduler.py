"""Moduł harmonogramu i powiadomień (scheduler & notifier) - maszyna stanów bez Qt i audio."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable

from mailvoice.core.pipeline import CycleResult, PipelineDeps, run_cycle


class NotifierState(str, Enum):
    """Stany maszyny powiadomień."""

    IDLE = "idle"
    BEEPING = "beeping"
    ASKING = "asking"
    SNOOZED = "snoozed"


class NotificationAction(str, Enum):
    """Akcje generowane przez maszynę powiadomień."""

    BEEP = "beep"
    ASK = "ask"
    NONE = "none"


class Notifier:
    """Maszyna stanów powiadomień z wstrzykiwanym zegarem.

    Obsługuje:
    - tryb 'beep': powtarza sygnał co `beep_repeat_minutes`, dopóki użytkownik nie potwierdzi.
    - tryb 'ask': zadaje pytanie 'masz czas wysłuchać?', na 'nie' ponawia po `ask_retry_minutes`.
    """

    def __init__(
        self,
        notify_mode: str = "beep",
        beep_repeat_minutes: int = 5,
        ask_retry_minutes: int = 15,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.notify_mode = notify_mode
        self.beep_repeat_minutes = max(1, beep_repeat_minutes)
        self.ask_retry_minutes = max(1, ask_retry_minutes)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

        self.state = NotifierState.IDLE
        self.pending_count: int = 0
        self.last_action_time: datetime | None = None
        self.snoozed_until: datetime | None = None

    def on_important_mail(self, count: int = 1) -> NotificationAction:
        """Powiadamia maszynę o pojawieniu się nowych ważnych wiadomości."""
        if count <= 0:
            return NotificationAction.NONE

        self.pending_count += count
        now = self._clock()

        if self.notify_mode == "beep":
            self.state = NotifierState.BEEPING
            self.last_action_time = now
            return NotificationAction.BEEP

        # Tryb 'ask'
        if self.state == NotifierState.SNOOZED:
            # Użytkownik odroczył wcześniejsze pytanie - czekamy do końca snooze
            return NotificationAction.NONE

        self.state = NotifierState.ASKING
        self.last_action_time = now
        return NotificationAction.ASK

    def tick(self) -> NotificationAction:
        """Krok czasowy sprawdzający czy nadszedł czas na powtórzenie sygnału lub pytania."""
        if self.pending_count <= 0:
            self.state = NotifierState.IDLE
            return NotificationAction.NONE

        now = self._clock()

        if self.notify_mode == "beep":
            if self.state == NotifierState.BEEPING:
                if (
                    self.last_action_time is None
                    or (now - self.last_action_time) >= timedelta(minutes=self.beep_repeat_minutes)
                ):
                    self.last_action_time = now
                    return NotificationAction.BEEP
            return NotificationAction.NONE

        # Tryb 'ask'
        if self.state == NotifierState.SNOOZED:
            if self.snoozed_until is not None and now >= self.snoozed_until:
                self.state = NotifierState.ASKING
                self.snoozed_until = None
                self.last_action_time = now
                return NotificationAction.ASK

        return NotificationAction.NONE

    def user_confirm(self) -> None:
        """Użytkownik potwierdził odbiór / odsłuchał streszczenia."""
        self.pending_count = 0
        self.state = NotifierState.IDLE
        self.snoozed_until = None

    def user_decline(self) -> None:
        """Użytkownik odpowiedział 'nie' (odroczenie ponowienia w trybie ask)."""
        if self.notify_mode == "ask" and self.pending_count > 0:
            self.state = NotifierState.SNOOZED
            self.snoozed_until = self._clock() + timedelta(minutes=self.ask_retry_minutes)
        else:
            self.user_confirm()

    def user_dismiss(self) -> None:
        """Użytkownik zignorował powiadomienie (wyciszenie)."""
        self.pending_count = 0
        self.state = NotifierState.IDLE
        self.snoozed_until = None


class Scheduler:
    """Koordynator cyklicznego uruchamiania potoku przetwarzania poczty."""

    def __init__(
        self,
        deps: PipelineDeps,
        notifier: Notifier | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.deps = deps
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.notifier = notifier or Notifier(
            notify_mode=deps.config.notify_mode,
            beep_repeat_minutes=deps.config.beep_repeat_minutes,
            ask_retry_minutes=deps.config.ask_retry_minutes,
            clock=self._clock,
        )
        self.last_cycle_time: datetime | None = None

    def run_once(self, check_backlog: bool = False) -> CycleResult:
        """Wykonuje pojedynczy cykl i powiadamia maszynę Notifier w przypadku ważnych maili."""
        result = run_cycle(self.deps, check_backlog=check_backlog)
        self.last_cycle_time = self._clock()
        total_important = len(result.important)
        if total_important > 0:
            self.notifier.on_important_mail(total_important)
        return result
