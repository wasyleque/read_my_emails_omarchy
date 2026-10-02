"""Test dymny na prawdziwej skrzynce (TYLKO ODCZYT) — wypisuje wyłącznie liczby i statusy.

Nie wypisuje tematów, nadawców, treści, adresów ani haseł. Analiza idzie na tymczasowej
bazie w pamięci, więc prawdziwa baza aplikacji nie jest dotykana. Konto dodaj wcześniej
kreatorem (`python -m mailvoice`), hasło jest czytane z systemowego sejfu.

Użycie:
    python tools/smoke_test.py                 # wszystkie konta, zaległe z ostatnich 3 dni
    python tools/smoke_test.py --days 7 --max-analyze 5
    python tools/smoke_test.py --account "moje-konto" --no-llm

Kroki: konfiguracja -> sejf -> Ollama -> IMAP (logowanie, foldery, UID) -> dowód read-only
(liczba nieprzeczytanych przed i po) -> analiza zaległych -> deduplikacja w drugim przebiegu.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import platformdirs

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.config import AccountConfig, AppConfig, load_config
from mailvoice.core.imap_fetch import ImapToolsClient
from mailvoice.core.pipeline import PipelineDeps, run_cycle
from mailvoice.core.secrets import SecretStoreError, create_store
from mailvoice.core.store import Store

OK, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"
failures = 0


def report(status: str, text: str) -> None:
    global failures
    if status == FAIL:
        failures += 1
    print(f"{status} {text}")


def check_ollama(cfg: AppConfig) -> bool:
    found = False
    for label, url in (("LAN", cfg.ollama.lan_url), ("lokalny", cfg.ollama.local_url)):
        try:
            data = httpx.get(f"{url}/api/tags", timeout=5).json()
            names = {m.get("name", "") for m in data.get("models", [])}
            has = cfg.ollama.model in names
            report(
                OK if has else WARN,
                f"Ollama {label}: odpowiada, modeli: {len(names)}, "
                f"model '{cfg.ollama.model}' {'jest' if has else 'BRAK (ollama pull ...)'}",
            )
            found = found or has
        except Exception as exc:  # tylko nazwa typu — bez szczegółów
            report(WARN, f"Ollama {label}: nie odpowiada ({type(exc).__name__})")
    return found


def check_account(acc: AccountConfig, cfg: AppConfig, store_secret, days: int) -> bool:
    secret = store_secret.get(acc.name)
    report(OK if secret else FAIL, f"[{acc.name}] hasło w sejfie: {'jest' if secret else 'BRAK'}")
    if not secret:
        return False
    if not acc.use_ssl:
        report(FAIL, f"[{acc.name}] TLS wyłączony — aplikacja odmawia takiego połączenia")
        return False
    client = ImapToolsClient(
        host=acc.host, port=acc.port, username=acc.username, password=secret, use_ssl=True
    )
    try:
        t0 = time.time()
        folder = acc.folders[0] if acc.folders else "INBOX"
        uidv = client.get_uidvalidity(folder)
        report(
            OK,
            f"[{acc.name}] logowanie i folder '{folder}' OK ({time.time() - t0:.1f}s), "
            f"UIDVALIDITY ustalone: {bool(uidv)}",
        )
        all_uids = client.get_uids_greater_than(folder, 0)
        since = date.today() - timedelta(days=days)
        unseen_before = client.get_unseen_uids(folder, since)
        report(
            OK,
            f"[{acc.name}] wiadomości w folderze: {len(all_uids)}, "
            f"nieprzeczytane z ostatnich {days} dni: {len(unseen_before)}",
        )
        if acc.sent_folder:
            try:
                sent = client.get_sent_message_ids(acc.sent_folder, since)
                report(
                    OK,
                    f"[{acc.name}] folder wysłanych '{acc.sent_folder}' OK, "
                    f"wiadomości z {days} dni: {len(sent)}",
                )
            except Exception as exc:
                report(
                    WARN,
                    f"[{acc.name}] folder wysłanych '{acc.sent_folder}' niedostępny "
                    f"({type(exc).__name__}) — popraw nazwę w ustawieniach",
                )
        # dowód read-only: pobranie treści NIE może zmienić liczby nieprzeczytanych
        sample = [u for u in unseen_before][:3]
        if sample:
            client.fetch_raw_batch(folder, sample)
            unseen_after = client.get_unseen_uids(folder, since)
            same = len(unseen_after) == len(unseen_before)
            report(
                OK if same else FAIL,
                f"[{acc.name}] read-only: nieprzeczytane przed={len(unseen_before)} "
                f"po pobraniu={len(unseen_after)} -> "
                f"{'flagi nietknięte' if same else 'ZMIENIONE!'}",
            )
        else:
            report(
                WARN,
                f"[{acc.name}] brak nieprzeczytanych — dowód read-only pominięty "
                "(wyślij sobie 1-2 maile i nie otwieraj ich)",
            )
        return True
    except Exception as exc:
        report(FAIL, f"[{acc.name}] błąd IMAP: {type(exc).__name__}")
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


def run_analysis(cfg: AppConfig, store_secret, days: int, max_analyze: int, llm: bool) -> None:
    cfg = dataclasses.replace(cfg, backlog_days=days)
    store = Store(":memory:")  # NIE prawdziwa baza
    deps = PipelineDeps(
        config=cfg,
        store=store,
        client_factory=lambda acc: ImapToolsClient(
            host=acc.host,
            port=acc.port,
            username=acc.username,
            password=store_secret.get(acc.name) or "",
            use_ssl=True,
        ),
        ollama_client=OllamaClient(cfg.ollama),
    )
    if not llm:
        report(WARN, "analiza LLM pominięta (--no-llm)")
        return
    t0 = time.time()
    res = run_cycle(deps, check_backlog=True)
    n_imp = len(res.backlog_important) + len(res.important)
    report(
        OK,
        f"analiza zaległych: ważnych {n_imp}, błędów {len(res.errors)} ({time.time() - t0:.0f}s)",
    )
    if res.errors:
        report(WARN, "są błędy analizy/pobierania — sprawdź Ollamę, nazwy folderów i połączenie")
    t1 = time.time()
    res2 = run_cycle(deps, check_backlog=True)
    again = len(res2.backlog_important) + len(res2.important)
    report(
        OK if again == 0 else FAIL,
        f"deduplikacja: drugi przebieg ponownie zgłosił {again} maili "
        f"({'OK — nic nie analizowane drugi raz' if again == 0 else 'BŁĄD'}) "
        f"({time.time() - t1:.0f}s)",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--config",
        type=Path,
        default=Path(platformdirs.user_config_dir("mailvoice")) / "config.json",
    )
    ap.add_argument("--account", help="nazwa konta (domyślnie wszystkie)")
    ap.add_argument("--days", type=int, default=3, help="okno zaległych w dniach (domyślnie 3)")
    ap.add_argument(
        "--max-analyze", type=int, default=5, help="(zarezerwowane) limit maili do analizy"
    )
    ap.add_argument("--no-llm", action="store_true", help="pomiń analizę modelem")
    args = ap.parse_args()

    if not args.config.exists():
        report(
            FAIL,
            "brak konfiguracji — uruchom najpierw `python -m mailvoice` i dodaj konto w kreatorze",
        )
        return 1
    cfg = load_config(args.config)
    accounts = [a for a in cfg.accounts if not args.account or a.name == args.account]
    report(OK if accounts else FAIL, f"konfiguracja wczytana, kont do testu: {len(accounts)}")
    if not accounts:
        return 1
    try:
        secrets = create_store()
        report(OK, "sejf haseł (keyring) dostępny")
    except SecretStoreError as exc:
        report(FAIL, f"sejf niedostępny ({type(exc).__name__})")
        return 1

    llm_ok = check_ollama(cfg)
    results = [check_account(a, cfg, secrets, args.days) for a in accounts]
    if all(results):
        cfg = dataclasses.replace(cfg, accounts=accounts)
        run_analysis(cfg, secrets, args.days, args.max_analyze, llm=llm_ok and not args.no_llm)
    print()
    print(
        "WYNIK: "
        + ("wszystko przeszło" if failures == 0 else f"{failures} problem(ów) — patrz [FAIL] wyżej")
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
