"""
Text processing utilities for MailVoice application.
"""

import re
from html import unescape
from html.parser import HTMLParser

ZERO_WIDTH_AND_BIDI_PATTERN = re.compile(
    r"[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2066-\u2069]"
)


def _check_style_hidden(style: str) -> bool:
    """Sprawdza czy reguły CSS w stylu inline ukrywają element."""
    s = "".join(style.split()).lower()

    if "display:none" in s or "visibility:hidden" in s or "visibility:collapse" in s:
        return True

    if re.search(r"opacity:0(?:\.0+)?(?:;|$|!)", s):
        return True

    if re.search(r"font-size:(?:0(?:\.\d+)?(?:px|pt|em|rem|%)?|1px|1pt)(?:;|$|!)", s):
        return True

    if "color:transparent" in s:
        return True

    # Wykrywanie white-on-white lub identycznego koloru tekstu i tła
    white_vals = ("#fff", "#ffffff", "white", "rgb(255,255,255)")
    c_m = re.search(r"(?:^|;)color:([^;!]+)", s)
    bg_m = re.search(r"(?:^|;)background(?:-color)?:([^;!]+)", s)
    if c_m and bg_m:
        c_val = c_m.group(1).strip()
        bg_val = bg_m.group(1).strip()
        if c_val == bg_val:
            return True
        if c_val in white_vals and bg_val in white_vals:
            return True

    return False


class _HTMLToTextParser(HTMLParser):
    """Parser HTML do czystego tekstu z eliminacją ukrytych elementów."""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tag_stack: list[str] = []
        self.hidden_stack: list[bool] = []
        self.hidden_content_found: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}

        is_hidden = False
        if "hidden" in attrs_dict:
            is_hidden = True
        elif attrs_dict.get("aria-hidden", "").strip().lower() == "true":
            is_hidden = True
        elif "style" in attrs_dict and _check_style_hidden(attrs_dict["style"]):
            is_hidden = True

        if self.hidden_stack and self.hidden_stack[-1]:
            is_hidden = True

        if tag == "br":
            if not is_hidden:
                self.text.append("\n")
            return

        self.tag_stack.append(tag)
        self.hidden_stack.append(is_hidden)

        if not is_hidden:
            if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
                self.text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "br":
            return

        is_currently_hidden = bool(self.hidden_stack and self.hidden_stack[-1])
        if not is_currently_hidden and tag in (
            "p",
            "div",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ):
            self.text.append("\n")

        if tag in self.tag_stack:
            idx = len(self.tag_stack) - 1 - self.tag_stack[::-1].index(tag)
            self.tag_stack.pop(idx)
            if idx < len(self.hidden_stack):
                self.hidden_stack.pop(idx)

    def handle_data(self, data: str) -> None:
        if any(tag in ("script", "style") for tag in self.tag_stack):
            return
        if any(tag in ("noscript", "template") for tag in self.tag_stack):
            if data.strip():
                self.hidden_content_found = True
            return

        is_hidden = bool(self.hidden_stack and self.hidden_stack[-1])
        if is_hidden:
            if data.strip():
                self.hidden_content_found = True
            return

        clean = ZERO_WIDTH_AND_BIDI_PATTERN.sub("", data)
        if clean != data:
            self.hidden_content_found = True
        self.text.append(re.sub(r"\s+", " ", clean))

    def handle_comment(self, data: str) -> None:
        if data.strip():
            self.hidden_content_found = True

    def get_text(self) -> str:
        return "".join(self.text)


def html_to_text_ex(html: str) -> tuple[str, bool]:
    """
    Konwertuje HTML na czysty tekst z usuwaniem i wykrywaniem ukrytych treści.

    Args:
        html (str): Treść HTML do przetworzenia

    Returns:
        tuple[str, bool]: (oczyszczony tekst, flaga czy wykryto ukrytą treść)
    """
    if not html:
        return "", False

    hidden_content_found = False
    if ZERO_WIDTH_AND_BIDI_PATTERN.search(html):
        hidden_content_found = True

    parser = _HTMLToTextParser()
    parser.feed(html)
    text = parser.get_text()
    if parser.hidden_content_found:
        hidden_content_found = True

    # Dekodowanie encji HTML
    text = unescape(text).replace("\xa0", " ")

    if ZERO_WIDTH_AND_BIDI_PATTERN.search(text):
        hidden_content_found = True
        text = ZERO_WIDTH_AND_BIDI_PATTERN.sub("", text)

    # Redukcja białych znaków
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip(), hidden_content_found


def html_to_text(html: str) -> str:
    """
    Konwertuje HTML na czysty tekst (zachowana zgodność wsteczna).

    Args:
        html (str): Treść HTML

    Returns:
        str: Oczyszczony tekst
    """
    text, _ = html_to_text_ex(html)
    return text


def clean_body(text: str) -> str:
    """
    Clean email body by removing quote lines and signature.

    Args:
        text (str): Email body text

    Returns:
        str: Cleaned text with quotes and signatures removed
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        # Skip quote lines (starting with >)
        if line.startswith(">"):
            continue

        # Stop at signature marker (line starting with -- )
        if line.startswith("-- ") or line.rstrip() == "--":
            break

        cleaned_lines.append(line)

    # Join lines and clean up extra whitespace
    result = "\n".join(cleaned_lines)

    # Replace multiple consecutive newlines with double newline
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def truncate_for_llm(text: str, max_chars: int = 1500) -> str:
    """
    Truncate text for LLM input while preserving word boundaries.

    Args:
        text (str): Text to truncate
        max_chars (int): Maximum number of characters

    Returns:
        str: Truncated text with ellipsis if needed
    """
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    # Find the last space before max_chars to avoid cutting words
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")

    if last_space > 0:
        truncated = text[:last_space]

    return truncated + "…"
