from dataclasses import dataclass
from email.utils import parseaddr
from typing import FrozenSet, Optional, Tuple

# Domeny publiczne: sam adres z takiej domeny może być „znany”, ale cała domena — nie
# (inaczej każdy z gmail.com dostawałby premię, bo kiedyś do kogoś stamtąd napisałeś).
FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "protonmail.com",
        "proton.me",
        "aol.com",
        "o2.pl",
        "tlen.pl",
        "wp.pl",
        "onet.pl",
        "onet.eu",
        "op.pl",
        "interia.pl",
        "interia.eu",
        "poczta.fm",
        "gazeta.pl",
        "vp.pl",
        "int.pl",
        "buziaczek.pl",
        "go2.pl",
        "autograf.pl",
    }
)


@dataclass(frozen=True)
class MailInfo:
    sender: str
    subject: str
    body: str
    in_reply_to: Optional[str] = None
    references: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Rules:
    vip_senders: Tuple[str, ...] = ()
    keywords: Tuple[str, ...] = ()
    blocked_senders: Tuple[str, ...] = ()
    sent_message_ids: FrozenSet[str] = frozenset()
    known_addresses: FrozenSet[str] = frozenset()  # adresy, do których Ty pisałeś
    known_domains: FrozenSet[str] = frozenset()  # domeny firmowe, do których Ty pisałeś


@dataclass(frozen=True)
class RuleResult:
    blocked: bool
    score_bonus: int
    reasons: Tuple[str, ...]
    known_bonus: int = 0  # część score_bonus z „znanego korespondenta” (do odjęcia przy ryzyku)


def evaluate(mail: MailInfo, rules: Rules) -> RuleResult:
    # Rule 1: Check if sender is blocked
    for blocked_sender in rules.blocked_senders:
        if blocked_sender.lower() in mail.sender.lower():
            return RuleResult(blocked=True, score_bonus=0, reasons=("blocked_sender",))

    score_bonus = 0
    known_bonus = 0
    reasons = []

    # Rule 2: Check if sender is VIP
    if any(v.lower() in mail.sender.lower() for v in rules.vip_senders):
        score_bonus += 3
        reasons.append("vip_sender")
    else:
        address = parseaddr(mail.sender)[1].lower()
        domain = address.rsplit("@", 1)[-1] if "@" in address else ""
        if address and address in rules.known_addresses:
            known_bonus = 3
            reasons.append("known_correspondent")
        elif domain and domain in rules.known_domains:
            known_bonus = 2
            reasons.append("known_domain")
    score_bonus += known_bonus

    # Rule 3: Check for keywords in subject or body
    keyword_count = 0
    for keyword in rules.keywords:
        if keyword.lower() in mail.subject.lower() or keyword.lower() in mail.body.lower():
            keyword_count += 1
            reasons.append(f"keyword:{keyword.lower()}")
            if keyword_count >= 2:  # Max +4 points (2 keywords)
                break

    score_bonus += keyword_count * 2

    # Rule 4: Check if this is a reply to a sent message
    candidates = ([mail.in_reply_to] if mail.in_reply_to else []) + list(mail.references)
    if any(c in rules.sent_message_ids for c in candidates):
        score_bonus += 3
        reasons.append("reply_to_sent")

    # Rule 5: Not blocked, return result
    return RuleResult(
        blocked=False,
        score_bonus=score_bonus,
        reasons=tuple(reasons),
        known_bonus=known_bonus,
    )
