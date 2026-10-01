"""
Text processing utilities for MailVoice application.
"""

import re
from html import unescape
from html.parser import HTMLParser


class _HTMLToTextParser(HTMLParser):
    """Internal parser to convert HTML to plain text."""

    def __init__(self):
        super().__init__()
        self.text = []
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        if tag != "br":
            self.tag_stack.append(tag)
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text.append("\n")
        elif tag == "br":
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text.append("\n")
        try:
            self.tag_stack.remove(tag)
        except ValueError:
            pass

    def handle_data(self, data):
        # Skip script and style content
        if not any(tag in ("script", "style") for tag in self.tag_stack):
            self.text.append(re.sub(r"\s+", " ", data))

    def get_text(self):
        return "".join(self.text)


def html_to_text(html: str) -> str:
    """
    Convert HTML to plain text.

    Args:
        html (str): HTML string to convert

    Returns:
        str: Plain text with tags removed, script/style content skipped,
             <br> and block elements converted to newlines, HTML entities decoded,
             multiple spaces and empty lines cleaned up
    """
    if not html:
        return ""

    # Parse HTML to plain text
    parser = _HTMLToTextParser()
    parser.feed(html)
    text = parser.get_text()

    # Decode HTML entities
    text = unescape(text).replace("\xa0", " ")

    # Replace multiple spaces with single space
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)

    # Replace 3+ consecutive newlines with double newline
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace
    return text.strip()


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
