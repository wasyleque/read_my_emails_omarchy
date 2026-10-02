"""Moduł oceny ryzyka bezpieczeństwa i wykrywania phishingu w wiadomościach e-mail."""

import re
from email.utils import parseaddr
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlparse

from mailvoice.core.mailparse import ParsedMail

RiskLevel = Literal["low", "medium", "high"]


class RiskAssessment:
    """Wynik oceny ryzyka wiadomości e-mail."""

    def __init__(
        self,
        risk: RiskLevel,
        score: int,
        reasons: Sequence[str] = (),
        flags: frozenset[str] = frozenset(),
    ) -> None:
        self.risk = risk
        self.score = score
        self.reasons = tuple(reasons)
        self.flags = frozenset(flags)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, RiskAssessment):
            return False
        return (
            self.risk == other.risk
            and self.score == other.score
            and self.reasons == other.reasons
            and self.flags == other.flags
        )

    def __repr__(self) -> str:
        return (
            f"RiskAssessment(risk={self.risk!r}, score={self.score}, "
            f"reasons={self.reasons!r}, flags={self.flags!r})"
        )


def defang_url(url: str) -> str:
    """Zabezpiecza URL przed przypadkowym kliknięciem (defanging: hxxps://domain[.]com)."""
    if not url:
        return ""
    u = url.strip()
    u = re.sub(
        r"^https?://",
        lambda m: "hxxps://" if m.group(0).lower().startswith("https") else "hxxp://",
        u,
        flags=re.IGNORECASE,
    )
    parts = u.split("/", 3)
    if len(parts) >= 3 and (parts[0].startswith("hxxp:") or parts[0].startswith("hxxps:")):
        parts[2] = parts[2].replace(".", "[.]")
        return "/".join(parts)

    slash_idx = u.find("/")
    if slash_idx != -1:
        return u[:slash_idx].replace(".", "[.]") + u[slash_idx:]
    return u.replace(".", "[.]")


DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe",
        ".scr",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".js",
        ".hta",
        ".cpl",
        ".jar",
        ".iso",
        ".img",
        ".wsf",
        ".pif",
    }
)

DOUBLE_EXT_PATTERN = re.compile(
    r"\.(?:pdf|docx?|xlsx?|pptx?|txt|png|jpe?g|mp3|mp4)\."
    r"(?:exe|scr|bat|cmd|ps1|vbs|js|hta|cpl|jar|iso|img)$",
    re.IGNORECASE,
)

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"new\s+instructions\b", re.IGNORECASE),
    re.compile(r"od\s+teraz\s+jesteś\b", re.IGNORECASE),
    re.compile(r"zignoruj\s+(?:wszystkie\s+)?poprzednie", re.IGNORECASE),
    re.compile(r"zapomnij\s+o\s+instrukcjach", re.IGNORECASE),
    re.compile(r"forget\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"override\s+system\s+instructions", re.IGNORECASE),
    re.compile(r"jailbreak\b", re.IGNORECASE),
    re.compile(r"developer\s+mode\b", re.IGNORECASE),
]

URGENCY_KEYWORDS = [
    "zablokowane konto",
    "zablokowana karta",
    "natychmiast",
    "w ciągu 24h",
    "w ciagu 24h",
    "pilne",
    "zawieszenie",
    "potwierdź tożsamość",
    "potwierdz tozsamosc",
    "zaloguj się aby",
    "zaloguj sie aby",
    "nieautoryzowany dostęp",
    "nieautoryzowany dostep",
    "faktura zaległa",
    "faktura zalegla",
    "dopłata do paczki",
    "doplata do paczki",
    "przelew",
    "kryptowaluty",
    "hasło wygasa",
    "haslo wygasa",
    "ostrzeżenie o zawieszeniu",
    "ostatnie ostrzeżenie",
    "zaktualizuj dane",
    "account suspended",
    "immediately",
    "within 24h",
    "within 24 hours",
    "urgent",
    "suspension",
    "verify your identity",
    "confirm your identity",
    "log in to",
    "unauthorized access",
    "overdue invoice",
    "package fee",
    "wire transfer",
    "cryptocurrency",
    "password expires",
    "action required",
    "security alert",
    "update payment details",
]

SHORTENER_DOMAINS = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "t.co",
        "goo.gl",
        "ow.ly",
        "is.gd",
        "buff.ly",
        "cutt.ly",
        "rb.gy",
    }
)

SUSPICIOUS_TLDS = frozenset(
    {
        ".tk",
        ".ml",
        ".ga",
        ".cf",
        ".gq",
        ".xyz",
        ".top",
        ".click",
        ".loan",
    }
)
FREE_TLDS = SUSPICIOUS_TLDS

BRAND_DOMAINS: dict[str, tuple[str, ...]] = {
    "pko": ("pkobp.pl", "ipko.pl", "pko.pl"),
    "mbank": ("mbank.pl",),
    "santander": ("santander.pl",),
    "ing": ("ing.pl", "ingbank.pl"),
    "alior": ("aliorbank.pl", "alior.pl"),
    "millennium": ("bankmillennium.pl", "millennium.pl"),
    "pekao": ("pekao.com.pl", "pekao.pl"),
    "allegro": ("allegro.pl", "allegromail.pl"),
    "inpost": ("inpost.pl",),
    "dhl": ("dhl.com", "dhl.pl"),
    "dpd": ("dpd.com", "dpd.com.pl", "dpd.pl"),
    "poczta polska": ("poczta-polska.pl",),
    "paypal": ("paypal.com", "paypal.pl"),
    "apple": ("apple.com", "icloud.com"),
    "google": ("google.com", "gmail.com"),
    "microsoft": ("microsoft.com", "outlook.com", "live.com", "hotmail.com"),
    "netflix": ("netflix.com",),
    "amazon": ("amazon.com", "amazon.pl"),
    "revolut": ("revolut.com",),
    "chase": ("chase.com",),
}


def _extract_domain(addr: str) -> str:
    """Wyciąga domenę z adresu e-mail."""
    clean = parseaddr(addr)[1] if "@" in addr else addr
    if "@" in clean:
        return clean.split("@")[-1].strip().lower()
    return clean.strip().lower()


def _has_homoglyphs(domain: str) -> bool:
    """Sprawdza obecność znaków cyrylicy lub greckich w domenie."""
    for ch in domain:
        cp = ord(ch)
        if (0x0400 <= cp <= 0x04FF) or (0x0370 <= cp <= 0x03FF):
            return True
    return False


def assess(
    mail: ParsedMail,
    headers: Mapping[str, Any] | None = None,
    my_addresses: Sequence[str] = (),
    known_contacts: Sequence[str] = (),
) -> RiskAssessment:
    """Ocenia ryzyko phishingu i bezpieczeństwa wiadomości e-mail."""
    score = 0
    reasons: list[str] = []
    flags: set[str] = set()

    clean_sender_addr = parseaddr(mail.sender)[1].strip().lower()
    sender_domain = _extract_domain(clean_sender_addr)
    known_lower = {k.strip().lower() for k in known_contacts}
    my_lower = {m.strip().lower() for m in my_addresses}

    # 1. SPF / DKIM / DMARC fail
    auth_header = (
        (headers.get("Authentication-Results", "") if headers else "")
        or mail.authentication_results
        or ""
    )
    received_spf = headers.get("Received-SPF", "") if headers else ""
    combined_auth = f"{auth_header} {received_spf}".lower()

    if (
        "spf=fail" in combined_auth
        or "spf=softfail" in combined_auth
        or "dkim=fail" in combined_auth
        or "dmarc=fail" in combined_auth
        or combined_auth.startswith("fail")
        or combined_auth.startswith("softfail")
    ):
        score += 40
        flags.add("auth_fail")
        reasons.append("Błąd uwierzytelnienia SPF/DKIM/DMARC (możliwy spoofing)")

    # 2. Homoglify w domenie nadawcy
    if sender_domain and _has_homoglyphs(sender_domain):
        score += 50
        flags.add("homoglyph")
        reasons.append(
            f"Wykryto homoglify (znaki cyrylicy/greckie) w domenie nadawcy ({sender_domain})"
        )

    # 3. Rozbieżność domen nadawcy (From vs Reply-To)
    if mail.reply_to:
        reply_domain = _extract_domain(mail.reply_to)
        if reply_domain and sender_domain and reply_domain != sender_domain:
            reply_addr = parseaddr(mail.reply_to)[1].lower()
            if reply_addr not in known_lower and reply_addr not in my_lower:
                score += 25
                flags.add("mismatched_sender")
                reasons.append(
                    f"Rozbieżność Reply-To ({reply_domain}) z domeną nadawcy ({sender_domain})"
                )

    # 4. Podejrzane linki
    suspicious_links_count = 0
    for link in mail.links:
        parsed_link = urlparse(link)
        netloc = parsed_link.netloc.lower()
        host = netloc.split(":")[0]

        is_suspicious = False
        # Adres IP w linku
        if re.match(r"^(?:\d{1,3}\.){3}\d{1,3}$", host):
            is_suspicious = True
        # Skracacz linków
        elif host in SHORTENER_DOMAINS:
            is_suspicious = True
        # Podejrzana darmowa domena TLD
        elif any(host.endswith(tld) for tld in FREE_TLDS):
            is_suspicious = True

        if is_suspicious:
            suspicious_links_count += 1
            if suspicious_links_count <= 3:
                score += 20
                flags.add("suspicious_link")
                reasons.append(f"Podejrzany link ({defang_url(link)})")

    # Rozbieżność widocznego tekstu linku z rzeczywistym adresem docelowym
    mismatched_re = re.compile(
        r"(?:https?://|www\.)([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s()<>\"']*)\s*\((https?://[^\s()<>\"']+)\)",
        re.IGNORECASE,
    )
    found_mismatch = False
    for m in mismatched_re.finditer(mail.body_text):
        disp_target = m.group(1).lower()
        act_href = m.group(2).lower()
        disp_host = urlparse("http://" + disp_target).netloc.split(":")[0]
        act_host = urlparse(act_href).netloc.split(":")[0]
        if disp_host and act_host and disp_host != act_host:
            score += 35
            flags.add("mismatched_link_text")
            reasons.append(
                f"Tekst linku ({disp_host}) wskazuje na inny niż adres docelowy ({act_host})"
            )
            found_mismatch = True
            break

    # Sprawdzenie czy w treści widnieje URL marki/banku, a żaden link nie prowadzi do tej domeny
    if not found_mismatch and mail.links:
        body_urls = re.findall(
            r"(?:https?://|www\.)([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            mail.body_text,
            re.IGNORECASE,
        )
        actual_hosts = {urlparse(lnk).netloc.split(":")[0].lower() for lnk in mail.links}
        for b_host in body_urls:
            b_host_lower = b_host.lower()
            if b_host_lower and not any(
                b_host_lower == act or act.endswith(f".{b_host_lower}") for act in actual_hosts
            ):
                first_act = next(iter(actual_hosts)) if actual_hosts else "obcy serwer"
                score += 35
                flags.add("mismatched_link_text")
                reasons.append(
                    f"Tekst linku ({b_host_lower}) wskazuje na inny niż "
                    f"adres docelowy ({first_act})"
                )
                break

    # 5. Wymuszenie pośpiechu / prośba o dane / płatności
    body_lower = mail.body_text.lower()
    subject_lower = mail.subject.lower()
    text_to_scan = f"{subject_lower}\n{body_lower}"

    urgency_matches = [kw for kw in URGENCY_KEYWORDS if kw in text_to_scan]
    if len(urgency_matches) >= 3:
        score += 30
        flags.add("urgency_or_credentials")
        reasons.append(
            "Wielokrotne słowa kluczowe wymuszenia pośpiechu lub prośby o dane/płatności"
        )
    elif len(urgency_matches) >= 1:
        score += 15
        flags.add("urgency_or_credentials")
        reasons.append("Wykryto słowa kluczowe wymuszenia pośpiechu lub prośby o dane/płatności")

    # 6. Ryzykowne rozszerzenia załączników
    for att in mail.attachments:
        att_name_lower = att.name.lower()
        is_dangerous = False

        if any(att_name_lower.endswith(ext) for ext in DANGEROUS_EXTENSIONS):
            is_dangerous = True
        elif DOUBLE_EXT_PATTERN.search(att_name_lower):
            is_dangerous = True
        elif att_name_lower.endswith(".zip") and any(
            pwd_kw in text_to_scan for pwd_kw in ("hasło", "haslo", "password")
        ):
            is_dangerous = True

        if is_dangerous:
            score += 50
            flags.add("dangerous_attachment")
            reasons.append(f"Niebezpieczny załącznik ({att.name})")
            break

    # 7. Ukryty tekst / prompt injection
    # Sprawdzanie czy w tekście są znaki zero-width / bidi lub flaga w headers
    has_hidden = bool(
        headers
        and (
            headers.get("hidden_content_found")
            or headers.get("X-MailVoice-Hidden-Content")
            or headers.get("x-mailvoice-hidden-content")
        )
    )
    if re.search(r"[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2066-\u2069]", mail.body_text):
        has_hidden = True

    if has_hidden:
        score += 30
        flags.add("hidden_text")
        reasons.append("Wykryto ukryty tekst lub znaki kontrolne Unicode")

    # Prompt injection patterns
    for pat in PROMPT_INJECTION_PATTERNS:
        if pat.search(mail.body_text) or pat.search(mail.subject):
            score += 40
            flags.add("prompt_injection_pattern")
            reasons.append("Wykryto wzorzec próby manipulacji modelem AI (prompt injection)")
            break

    # 8. Brand Impersonation
    if clean_sender_addr not in known_lower and clean_sender_addr not in my_lower:
        sender_full_lower = mail.sender.lower()
        for brand, official_domains in BRAND_DOMAINS.items():
            if brand in sender_full_lower or brand in subject_lower:
                # Sprawdzamy czy domena nadawcy odpowiada oficjalnym domenom marki
                is_official = any(
                    sender_domain == dom or sender_domain.endswith(f".{dom}")
                    for dom in official_domains
                )
                if not is_official:
                    score += 40
                    flags.add("brand_impersonation")
                    reasons.append(
                        f"Podejrzenie podszywania się pod markę '{brand.title()}' "
                        f"z nieautoryzowanej domeny ({sender_domain})"
                    )
                    break

    final_score = min(100, score)
    if final_score >= 50:
        risk: RiskLevel = "high"
    elif final_score >= 25:
        risk = "medium"
    else:
        risk = "low"

    return RiskAssessment(
        risk=risk,
        score=final_score,
        reasons=tuple(reasons),
        flags=frozenset(flags),
    )
