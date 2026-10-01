"""Testy modułu harmonogramu i powiadomień (scheduler.py)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mailvoice.core.mailparse import ParsedMail
from mailvoice.core.pipeline import CycleResult, ProcessedMail
from mailvoice.core.scheduler import NotificationAction, Notifier, NotifierState, Scheduler


class FakeClock:
    """Fałszywy zegar do precyzyjnego testowania upływu czasu."""

    def __init__(self, start: datetime | None = None):
        self.current = start or datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, minutes: int = 1) -> None:
        self.current += timedelta(minutes=minutes)


def test_notifier_beep_mode():
    clock = FakeClock()
    notifier = Notifier(
        notify_mode="beep",
        beep_repeat_minutes=5,
        clock=clock,
    )

    assert notifier.state == NotifierState.IDLE

    # Pojawienie się ważnego maila wyzwala BEEP
    action = notifier.on_important_mail(1)
    assert action == NotificationAction.BEEP
    assert notifier.state == NotifierState.BEEPING

    # Natychmiastowy tick nie ponawia sygnału
    assert notifier.tick() == NotificationAction.NONE

    # Po 4 minutach - nadal brak sygnału
    clock.advance(4)
    assert notifier.tick() == NotificationAction.NONE

    # Po 5 minutach - sygnał ponowiony
    clock.advance(1)
    assert notifier.tick() == NotificationAction.BEEP

    # Użytkownik potwierdza
    notifier.user_confirm()
    assert notifier.state == NotifierState.IDLE
    assert notifier.pending_count == 0

    # Po kolejnych minutach brak sygnałów
    clock.advance(10)
    assert notifier.tick() == NotificationAction.NONE


def test_notifier_ask_mode_with_decline_and_retry():
    clock = FakeClock()
    notifier = Notifier(
        notify_mode="ask",
        ask_retry_minutes=15,
        clock=clock,
    )

    # Ważny mail wyzwala pytanie ASK
    action = notifier.on_important_mail(2)
    assert action == NotificationAction.ASK
    assert notifier.state == NotifierState.ASKING
    assert notifier.pending_count == 2

    # Użytkownik odpowiada "nie" -> stan SNOOZED na 15 minut
    notifier.user_decline()
    assert notifier.state == NotifierState.SNOOZED

    # Upływ 10 minut - brak ponowienia
    clock.advance(10)
    assert notifier.tick() == NotificationAction.NONE

    # Upływ kolejnych 5 minut (łącznie 15) - ponowne pytanie ASK
    clock.advance(5)
    assert notifier.tick() == NotificationAction.ASK
    assert notifier.state == NotifierState.ASKING

    # Użytkownik potwierdza
    notifier.user_confirm()
    assert notifier.state == NotifierState.IDLE
    assert notifier.pending_count == 0


def test_notifier_dismiss():
    clock = FakeClock()
    notifier = Notifier(notify_mode="beep", clock=clock)
    notifier.on_important_mail(1)
    assert notifier.state == NotifierState.BEEPING

    notifier.user_dismiss()
    assert notifier.state == NotifierState.IDLE
    assert notifier.pending_count == 0


def test_scheduler_run_once_triggers_notifier():
    clock = FakeClock()

    class DummyDeps:
        pass

    deps = DummyDeps()
    notifier = Notifier(notify_mode="beep", clock=clock)
    scheduler = Scheduler(deps=deps, notifier=notifier, clock=clock)

    dummy_mail = ProcessedMail(
        account="acc",
        folder="INBOX",
        uidvalidity=1,
        uid=10,
        mail=ParsedMail(
            message_id="<1@a.pl>",
            sender="a@a.pl",
            subject="Sub",
            date=None,
            in_reply_to=None,
            references=(),
            body_text="Body",
        ),
        final_importance=8,
        rule_reasons=(),
        analysis_reason="reason",
        action="read_now",
        language="pl",
    )

    with patch("mailvoice.core.scheduler.run_cycle") as mock_run:
        mock_run.return_value = CycleResult(important=[dummy_mail])
        result = scheduler.run_once()

    assert len(result.important) == 1
    assert notifier.state == NotifierState.BEEPING
    assert notifier.pending_count == 1
