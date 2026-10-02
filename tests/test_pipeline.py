"""Testy modułu potoku przetwarzania poczty (pipeline.py)."""

import json
from email.message import EmailMessage

import httpx
import pytest

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig, OllamaConfig
from mailvoice.core.pipeline import (
    PipelineDeps,
    load_pending_backlog,
    resolve_backlog,
    run_cycle,
)
from mailvoice.core.store import Store
from tests.test_imap_fetch import FakeMailboxClient


def _make_email_bytes(
    sender: str,
    subject: str,
    body: str,
    message_id: str,
    in_reply_to: str | None = None,
    to: str | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    if to:
        msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg["Date"] = "Wed, 01 Oct 2026 12:00:00 +0000"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    msg.set_content(body)
    return msg.as_bytes()


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_pipeline_normal_cycle(store):
    config = AppConfig(
        accounts=[
            AccountConfig(
                name="test_acc",
                host="imap.test.local",
                folders=["INBOX"],
                sent_folder="Sent",
            )
        ],
        vip_senders=["boss@firm.pl"],
        blocked_senders=["spam@bad.com"],
        importance_threshold=6,
        ollama=OllamaConfig(lan_url="http://lan:11434"),
    )

    client = FakeMailboxClient(uidvalidity=10)
    store.set_last_uid("test_acc", "INBOX", 10, 0)  # folder znany: maile 1-3 są nowe
    # Mail 1: Zablokowany
    client.folders["INBOX"][1] = _make_email_bytes(
        sender="spam@bad.com",
        subject="Kup cos",
        body="Spam",
        message_id="<msg1@bad.com>",
    )
    # Mail 2: Od szefa (VIP bonus +3), Ollama da 4 -> suma 7 >= 6 (ważny)
    client.folders["INBOX"][2] = _make_email_bytes(
        sender="boss@firm.pl",
        subject="Ważne spotkanie",
        body="Musimy omowic budzet",
        message_id="<msg2@firm.pl>",
    )
    # Mail 3: Zwykły, Ollama da 2 -> suma 2 < 6 (nieważny)
    client.folders["INBOX"][3] = _make_email_bytes(
        sender="newsletter@info.pl",
        subject="Nowinki",
        body="Newsletter tygodniowy",
        message_id="<msg3@info.pl>",
    )

    ollama_calls = []

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        content = data["messages"][1]["content"]
        ollama_calls.append(content)

        if "Ważne spotkanie" in content:
            resp = {
                "importance": 4,
                "reason": "Spotkanie z szefem",
                "action": "read_now",
                "language": "pl",
            }
        else:
            resp = {
                "importance": 2,
                "reason": "Biuletyn",
                "action": "ignore",
                "language": "pl",
            }
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(resp)}},
        )

    transport = httpx.MockTransport(mock_ollama)
    ollama_client = OllamaClient(config.ollama, transport=transport)

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda acc: client,
        ollama_client=ollama_client,
    )

    result = run_cycle(deps)

    assert len(result.errors) == 0
    # Tylko mail 2 jest ważny
    assert len(result.important) == 1
    assert result.important[0].uid == 2
    assert result.important[0].final_importance == 7
    assert "vip_sender" in result.important[0].rule_reasons

    # Zablokowany mail 1 NIE trafił do Ollamy (tylko 2 zapytania)
    assert len(ollama_calls) == 2

    # Wszystkie 3 maile są oznaczone w store jako seen
    assert store.is_seen("test_acc", "INBOX", 10, 1, "<msg1@bad.com>") is True
    assert store.is_seen("test_acc", "INBOX", 10, 2, "<msg2@firm.pl>") is True
    assert store.is_seen("test_acc", "INBOX", 10, 3, "<msg3@info.pl>") is True

    # last_uid został przesunięty na 3
    assert store.get_last_uid("test_acc", "INBOX", 10) == 3


def test_pipeline_ollama_failure_does_not_lose_mail(store):
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
    )

    client = FakeMailboxClient(uidvalidity=1)
    store.set_last_uid("acc1", "INBOX", 1, 0)  # folder znany: mail jest nowy
    # Mail 1 przejdzie pomyślnie
    client.folders["INBOX"][1] = _make_email_bytes(
        sender="a@a.pl", subject="S1", body="B1", message_id="<m1@a.pl>"
    )
    # Mail 2 wywoła błąd Ollamy
    client.folders["INBOX"][2] = _make_email_bytes(
        sender="b@b.pl", subject="S2", body="B2", message_id="<m2@b.pl>"
    )

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        if "S2" in data["messages"][1]["content"]:
            raise httpx.ConnectError("Ollama offline")
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"importance": 5, "reason": "ok", "action": "read_later", "language": "pl"}
                    )
                }
            },
        )

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda acc: client,
        ollama_client=OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama)),
    )

    result = run_cycle(deps)

    # Jeden błąd zarejestrowany
    assert len(result.errors) == 1
    # Mail 1 oznaczony jako seen
    assert store.is_seen("acc1", "INBOX", 1, 1, "<m1@a.pl>") is True
    # Mail 2 NIE oznaczony jako seen (spróbujemy w kolejnym cyklu)
    assert store.is_seen("acc1", "INBOX", 1, 2, "<m2@b.pl>") is False
    # last_uid nie został przesunięty za mail 1
    assert store.get_last_uid("acc1", "INBOX", 1) == 1


def test_pipeline_backlog_handling_and_resolve(store):
    config = AppConfig(
        accounts=[AccountConfig(name="acc1", host="imap.local", folders=["INBOX"])],
        importance_threshold=6,
    )

    client = FakeMailboxClient(uidvalidity=5)
    # Wiadomości zaległe (starsze niż last_uid)
    client.folders["INBOX"][1] = _make_email_bytes(
        sender="c@c.pl", subject="Stary ważny", body="Treść", message_id="<m1@c.pl>"
    )
    client.unseen_uids["INBOX"] = {1}
    store.set_last_uid("acc1", "INBOX", 5, 1)

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"importance": 8, "reason": "Ważne", "action": "read_now", "language": "pl"}
                    )
                }
            },
        )

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda acc: client,
        ollama_client=OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama)),
    )

    result = run_cycle(deps, check_backlog=True)
    assert len(result.backlog_important) == 1
    assert result.backlog_important[0].uid == 1

    # Ważny zaległy ma status backlog_pending w seen
    assert store.get_seen_status("acc1", "INBOX", 5, 1) == "backlog_pending"

    # Odtwarzanie zaległości po restarcie
    pending = load_pending_backlog(store)
    assert len(pending) == 1
    assert pending[0].uid == 1
    assert pending[0].message_id == "<m1@c.pl>"

    # Użytkownik odrzuca zaległe (accepted=False) -> zapis z flagą backlog_declined
    resolve_backlog(store, pending, accepted=False)
    assert store.get_seen_status("acc1", "INBOX", 5, 1) == "backlog_declined"

    # W kolejnym cyklu zaległość nie jest dublowana
    result2 = run_cycle(deps, check_backlog=True)
    assert len(result2.backlog_important) == 0


def _first_run_deps(store, client, calls):
    config = AppConfig(
        accounts=[AccountConfig(name="acc", host="h", folders=["INBOX"], sent_folder="")],
        importance_threshold=6,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        resp = {"importance": 9, "reason": "r", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    ollama = OllamaClient(config.ollama, transport=httpx.MockTransport(handler))
    return PipelineDeps(
        config=config, store=store, client_factory=lambda acc: client, ollama_client=ollama
    )


def test_first_run_does_not_analyze_history(store):
    client = FakeMailboxClient(uidvalidity=7)
    for uid in (1, 2, 3):
        client.folders["INBOX"][uid] = _make_email_bytes(
            sender="a@b.pl", subject=f"stary {uid}", body="x", message_id=f"<m{uid}@b.pl>"
        )
    calls: list[int] = []
    result = run_cycle(_first_run_deps(store, client, calls))

    assert calls == []  # historia (przeczytana) nie idzie do LLM
    assert result.important == [] and result.errors == []
    assert store.get_last_uid("acc", "INBOX", 7) == 3  # linia bazowa

    # nowy mail po pierwszym cyklu jest analizowany
    client.folders["INBOX"][4] = _make_email_bytes(
        sender="a@b.pl", subject="nowy", body="x", message_id="<m4@b.pl>"
    )
    result = run_cycle(_first_run_deps(store, client, calls))
    assert [m.uid for m in result.important] == [4]


def test_first_run_on_empty_mailbox_does_not_lose_first_mail(store):
    client = FakeMailboxClient(uidvalidity=8)
    calls: list[int] = []
    run_cycle(_first_run_deps(store, client, calls))
    assert store.has_last_uid("acc", "INBOX", 8)

    client.folders["INBOX"][1] = _make_email_bytes(
        sender="a@b.pl", subject="pierwszy", body="x", message_id="<m1@b.pl>"
    )
    result = run_cycle(_first_run_deps(store, client, calls))
    assert [m.uid for m in result.important] == [1]


def test_pipeline_poison_pill_format_error_retries_and_marks_failed(store):
    config = AppConfig(
        accounts=[AccountConfig(name="acc", host="h", folders=["INBOX"], sent_folder="")],
        importance_threshold=6,
    )
    client = FakeMailboxClient(uidvalidity=9)
    # Mail 1: powoduje błąd formatu (np. zły JSON z Ollamy)
    client.folders["INBOX"][1] = _make_email_bytes(
        sender="a@b.pl", subject="Poison", body="x", message_id="<m1@b.pl>"
    )
    # Mail 2: poprawny ważny mail
    client.folders["INBOX"][2] = _make_email_bytes(
        sender="a@b.pl", subject="Good", body="x", message_id="<m2@b.pl>"
    )
    store.set_last_uid("acc", "INBOX", 9, 0)

    def mock_ollama(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        content = data["messages"][1]["content"]
        if "Poison" in content:
            # Zwracamy odpowiedź 200, ale z nieprawidłową zawartością JSON (błąd formatu)
            return httpx.Response(200, json={"message": {"content": "niepoprawny json {"}})
        resp = {"importance": 8, "reason": "ok", "action": "read_now", "language": "pl"}
        return httpx.Response(200, json={"message": {"content": json.dumps(resp)}})

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda acc: client,
        ollama_client=OllamaClient(config.ollama, transport=httpx.MockTransport(mock_ollama)),
    )

    # Cykl 1: pierwsza próba dla maila 1 -> błąd, folder przerwany, mail nieoznaczony
    res1 = run_cycle(deps)
    assert len(res1.errors) == 1
    assert store.get_attempts("acc", "INBOX", 9, 1) == 1
    assert store.is_seen("acc", "INBOX", 9, 1, "<m1@b.pl>") is False
    assert store.get_last_uid("acc", "INBOX", 9) == 0

    # Cykl 2: druga próba
    res2 = run_cycle(deps)
    assert len(res2.errors) == 1
    assert store.get_attempts("acc", "INBOX", 9, 1) == 2
    assert store.is_seen("acc", "INBOX", 9, 1, "<m1@b.pl>") is False
    assert store.get_last_uid("acc", "INBOX", 9) == 0

    # Cykl 3: trzecia próba -> status='failed', last_uid przesunięte, mail 2 przetworzony
    res3 = run_cycle(deps)
    assert len(res3.errors) == 1
    assert store.is_seen("acc", "INBOX", 9, 1, "<m1@b.pl>") is True
    assert store.get_seen_status("acc", "INBOX", 9, 1) == "failed"

    # Mail 2 został pomyślnie przetworzony w tym samym cyklu 3 po przeskoczeniu failed maila 1
    assert [m.uid for m in res3.important] == [2]
    assert store.get_last_uid("acc", "INBOX", 9) == 2


def test_store_migration_preserves_data(tmp_path):
    import sqlite3

    db_path = tmp_path / "old.db"
    # Tworzymy starą strukturę bazy bez kolumny attempts i bez tabeli analysis_attempts
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE seen (
            account TEXT, folder TEXT, uidvalidity INTEGER, uid INTEGER,
            message_id TEXT, status TEXT NOT NULL DEFAULT 'new', importance INTEGER,
            PRIMARY KEY(account, folder, uidvalidity, uid)
        )
    """)
    cur.execute("INSERT INTO seen VALUES ('acc', 'INBOX', 1, 10, '<id1>', 'analyzed', 8)")
    conn.commit()
    conn.close()

    # Otwieramy przez nową klasę Store
    s = Store(db_path)
    assert s.is_seen("acc", "INBOX", 1, 10, "<id1>") is True
    assert s.get_attempts("acc", "INBOX", 1, 10) == 0

    # Można inkrementować próby
    assert s.increment_attempts("acc", "INBOX", 1, 10) == 1
    assert s.get_attempts("acc", "INBOX", 1, 10) == 1
    s.close()


def test_sent_mail_indexing_in_pipeline(store):
    config = AppConfig(
        accounts=[
            AccountConfig(
                name="test_acc",
                host="imap.test.local",
                folders=["INBOX"],
                sent_folder="Sent",
            )
        ],
        importance_threshold=6,
        ollama=OllamaConfig(lan_url="http://lan:11434"),
    )

    client = FakeMailboxClient(uidvalidity=10)
    store.set_last_uid("test_acc", "INBOX", 10, 0)
    # Mail w folderze wysłanych
    client.folders["Sent"][5] = _make_email_bytes(
        sender="me@mycompany.pl",
        to="client@customer.com",
        subject="Re: Oferta współpracy",
        body="Przesyłam szczegóły oferty.",
        message_id="<sent_msg_5@mycompany.pl>",
        in_reply_to="<inbox_msg_1@customer.com>",
    )

    classify_calls: list[str] = []

    def mock_classify(messages, model):
        classify_calls.append(str(messages))
        return None

    ollama = OllamaClient("http://lan:11434", "http://127.0.0.1:11434")
    ollama.classify = mock_classify

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda _: client,
        ollama_client=ollama,
    )

    result = run_cycle(deps)

    # Wysłane maile nie wywołują Ollama classify ani nie trafiają do ważnych
    assert len(classify_calls) == 0
    assert len(result.important) == 0

    # Wiadomość wysłana została zaindeksowana z direction='out'
    rec = store.get_mail_index("test_acc", "Sent", 10, 5)
    assert rec is not None
    assert rec.direction == "out"
    assert rec.importance == 0
    assert rec.why == ""
    assert rec.summary == ""
    assert rec.sender == "me@mycompany.pl"
    assert "client@customer.com" in rec.recipients
    assert rec.thread_key == "<inbox_msg_1@customer.com>"


def test_sent_folder_missing_does_not_crash_cycle(store):
    config = AppConfig(
        accounts=[
            AccountConfig(
                name="test_acc",
                host="imap.test.local",
                folders=["INBOX"],
                sent_folder="NonExistentFolder",
            )
        ],
        importance_threshold=5,
        ollama=OllamaConfig(lan_url="http://lan:11434"),
    )

    client = FakeMailboxClient(uidvalidity=10)
    client.folders.clear()
    client.folders["INBOX"] = {
        1: _make_email_bytes(
            sender="vip@client.com",
            subject="Ważna sprawa",
            body="Pilna odpowiedź wymagana.",
            message_id="<inbox1@client.com>",
        )
    }
    store.set_last_uid("test_acc", "INBOX", 10, 0)

    from mailvoice.core.analyzer import Analysis

    ollama = OllamaClient("http://lan:11434", "http://127.0.0.1:11434")
    ollama.classify = lambda _m, _md: Analysis(
        importance=8, reason="Pilne", action="Odpisz", language="pl"
    )

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda _: client,
        ollama_client=ollama,
    )

    result = run_cycle(deps)

    # Cykl nie uległ awarii - mail ze skrzynki odbiorczej został pomyślnie przetworzony
    assert len(result.important) == 1
    assert result.important[0].uid == 1
    # Błąd brakującego folderu wysłanych został zarejestrowany w sposób przyjazny
    assert len(result.errors) >= 1
    assert any("folder" in err.lower() for err in result.errors)


def test_sent_mail_indexing_idempotency(store):
    config = AppConfig(
        accounts=[
            AccountConfig(
                name="test_acc",
                host="imap.test.local",
                folders=["INBOX"],
                sent_folder="Sent",
            )
        ],
        importance_threshold=6,
        ollama=OllamaConfig(lan_url="http://lan:11434"),
    )

    client = FakeMailboxClient(uidvalidity=10)
    store.set_last_uid("test_acc", "INBOX", 10, 0)
    client.folders["Sent"][1] = _make_email_bytes(
        sender="me@mycompany.pl",
        to="client@customer.com",
        subject="Oferta",
        body="Tekst oferty.",
        message_id="<sent_id_1@mycompany.pl>",
    )

    ollama = OllamaClient("http://lan:11434", "http://127.0.0.1:11434")
    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda _: client,
        ollama_client=ollama,
    )

    # Cykl 1: indeksuje wiadomość wysłaną
    res1 = run_cycle(deps)
    assert len(res1.errors) == 0
    all_recs = store.get_all_indexed_records()
    assert len(all_recs) == 1
    assert all_recs[0].direction == "out"

    # Cykl 2: ponowne uruchomienie nie dubluje wpisów w mail_index
    res2 = run_cycle(deps)
    assert len(res2.errors) == 0
    all_recs2 = store.get_all_indexed_records()
    assert len(all_recs2) == 1


def test_pipeline_phishing_mail_handled_safely(store, monkeypatch):
    config = AppConfig(
        accounts=[
            AccountConfig(
                name="test_acc",
                host="imap.test.local",
                folders=["INBOX"],
                sent_folder="Sent",
            )
        ],
        importance_threshold=6,
        ollama=OllamaConfig(lan_url="http://lan:11434"),
    )

    client = FakeMailboxClient(uidvalidity=10)
    store.set_last_uid("test_acc", "INBOX", 10, 0)
    raw_msg = (
        b'From: "Bank PKO BP" <security@fakepko.xyz>\r\n'
        b"To: me@example.com\r\n"
        b"Subject: Pilne: blokada konta bankowego!\r\n"
        b"Message-ID: <phish_1@fakepko.xyz>\r\n"
        b"Date: Wed, 01 Oct 2026 12:00:00 +0000\r\n"
        b"Authentication-Results: spf=fail dkim=fail\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Kliknij natychmiast: http://fakepko.xyz/login aby odblokowac konto!"
    )
    client.folders["INBOX"][1] = raw_msg

    analyzer_called = False

    def fake_classify(*args, **kwargs):
        nonlocal analyzer_called
        analyzer_called = True
        raise AssertionError("Ollama classify should not be called for high-risk mail!")

    ollama = OllamaClient("http://lan:11434", "http://127.0.0.1:11434")
    monkeypatch.setattr(ollama, "classify", fake_classify)

    deps = PipelineDeps(
        config=config,
        store=store,
        client_factory=lambda _: client,
        ollama_client=ollama,
    )

    res = run_cycle(deps)
    assert len(res.errors) == 0
    assert len(res.important) == 0
    assert len(res.suspicious) == 1

    s_mail = res.suspicious[0]
    assert s_mail.suspicious is True
    assert s_mail.final_importance <= 3
    assert s_mail.risk_level == "high"
    assert "Podejrzana wiadomość" in s_mail.summary
    assert analyzer_called is False

    recs = store.get_all_indexed_records()
    assert len(recs) == 1
    assert recs[0].risk == "high"


def test_mail_index_schema_migration(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE mail_index (
            account TEXT NOT NULL,
            folder TEXT NOT NULL,
            uidvalidity INTEGER NOT NULL,
            uid INTEGER NOT NULL,
            message_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipients TEXT NOT NULL DEFAULT '',
            date TEXT NOT NULL,
            importance INTEGER NOT NULL,
            why TEXT NOT NULL,
            summary TEXT NOT NULL,
            thread_key TEXT NOT NULL,
            direction TEXT NOT NULL DEFAULT 'in',
            PRIMARY KEY (account, folder, uidvalidity, uid)
        )
        """
    )
    conn.commit()
    conn.close()

    s = Store(db_path)
    cols = {row[1] for row in s.connection.execute("PRAGMA table_info(mail_index)").fetchall()}
    assert "risk" in cols
    assert "risk_reasons" in cols
    s.close()
