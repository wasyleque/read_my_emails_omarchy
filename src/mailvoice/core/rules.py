from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple


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


@dataclass(frozen=True)
class RuleResult:
    blocked: bool
    score_bonus: int
    reasons: Tuple[str, ...]


def evaluate(mail: MailInfo, rules: Rules) -> RuleResult:
    # Rule 1: Check if sender is blocked
    for blocked_sender in rules.blocked_senders:
        if blocked_sender.lower() in mail.sender.lower():
            return RuleResult(blocked=True, score_bonus=0, reasons=("blocked_sender",))

    score_bonus = 0
    reasons = []

    # Rule 2: Check if sender is VIP
    if any(v.lower() in mail.sender.lower() for v in rules.vip_senders):
        score_bonus += 3
        reasons.append("vip_sender")

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
    return RuleResult(blocked=False, score_bonus=score_bonus, reasons=tuple(reasons))
