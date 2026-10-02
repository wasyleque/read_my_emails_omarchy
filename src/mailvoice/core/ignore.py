"""Reguły ignorowania maili: konkretny nadawca, cała domena albo „podobne” maile od nadawcy.

Przycisk „Ignoruj” tworzy regułę z trzech trybów:
- similar: ten sam nadawca ORAZ podobny temat (np. newsletter od firmy, ale nie jej faktury),
- sender: wszystkie maile od tego adresu,
- domain: wszystkie maile z tej domeny.
Zignorowane maile są po cichu pomijane (nie trafiają na listę ważnych, nie są czytane na głos).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from email.utils import parseaddr

IGNORE_MODES = ("similar", "sender", "domain")
MAX_RULES = 1000
_PREFIX = re.compile(
    r"^\s*((re|odp|fwd?|wg|aw|sv|ext|external|spam)\s*[:\]]\s*|\[[^\]]{0,20}\]\s*)", re.I
)
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_DIGITS = re.compile(r"\d+")


def normalize_subject(subject: str) -> str:
    """Temat bez prefiksów (Re:, Fwd:, [EXT]), cyfr i znaków specjalnych (do porównań)."""
    text = (subject or "").strip()
    previous = None
    while previous != text:  # zdejmuj kolejne prefiksy: „Re: Fwd: [EXT] …”
        previous = text
        text = _PREFIX.sub("", text, count=1)
    text = _DIGITS.sub(" ", text.lower())
    return _NON_WORD.sub(" ", text).strip()


def subject_signature(subject: str, words: int = 3) -> str:
    """Pierwsze kilka słów znormalizowanego tematu: „Faktura nr 12/2026” -> „faktura nr”."""
    return " ".join(normalize_subject(subject).split()[:words])


@dataclass(frozen=True)
class MailRule:
    """Reguła na maile: nadawca i/lub temat. Służy do ignorowania i do VIP (lustrzane odbicie).

    Pusty `sender` = każdy nadawca, pusty `subject` = każdy temat (nie oba naraz).
    """

    sender: str = ""
    subject: str = ""

    def is_valid(self) -> bool:
        return bool(self.sender.strip() or self.subject.strip())

    def matches(self, sender: str, subject: str) -> bool:
        if not self.is_valid():
            return False
        if self.sender and self.sender.lower() not in (sender or "").lower():
            return False
        if self.subject:
            wanted = normalize_subject(self.subject) or self.subject.lower().strip()
            if (
                wanted not in normalize_subject(subject)
                and self.subject.lower() not in (subject or "").lower()
            ):
                return False
        return True

    def describe(self) -> str:
        parts = []
        if self.sender:
            parts.append(f"od: {self.sender}")
        if self.subject:
            parts.append(f"temat zawiera: {self.subject}")
        return ", ".join(parts)


IgnoreRule = MailRule  # zgodność wsteczna: stara nazwa


def rule_for_mail(mode: str, sender: str, subject: str) -> MailRule:
    """Buduje regułę z maila, na którym użytkownik kliknął „Ignoruj”."""
    address = parseaddr(sender or "")[1].lower() or (sender or "").strip().lower()
    if mode == "domain":
        domain = address.rsplit("@", 1)[-1] if "@" in address else address
        return MailRule(sender=f"@{domain}")
    if mode == "similar":
        signature = subject_signature(subject)
        if signature:
            return MailRule(sender=address, subject=signature)
    return MailRule(sender=address)  # tryb „sender” oraz awaryjnie, gdy temat nie ma słów


def is_ignored(rules, sender: str, subject: str) -> bool:
    return any(rule.matches(sender, subject) for rule in rules)


def with_rule(rules: list[MailRule], rule: MailRule) -> list[MailRule]:
    """Lista reguł z dodaną nową (bez duplikatów, z limitem)."""
    if not rule.is_valid() or rule in rules:
        return list(rules)
    return [*rules, rule][-MAX_RULES:]


def add_ignore_rule(config, rule: IgnoreRule):
    return replace(config, ignore_rules=with_rule(list(config.ignore_rules), rule))


def is_ignored_by_config(config, sender: str, subject: str) -> bool:
    """Czy mail jest ignorowany przez reguły „Ignoruj” lub starą listę blokowanych nadawców."""
    if is_ignored(config.ignore_rules, sender, subject):
        return True
    low = (sender or "").lower()
    return any(b and b.lower() in low for b in config.blocked_senders)


def add_vip_rule(config, rule: MailRule):
    """Dodaje regułę VIP (przycisk „VIP…”); identyczna reguła ignorowania zostaje usunięta."""
    return replace(
        config,
        vip_rules=with_rule(list(config.vip_rules), rule),
        ignore_rules=[r for r in config.ignore_rules if r != rule],
    )
