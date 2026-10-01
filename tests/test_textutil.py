"""
Tests for textutil module.
"""

from mailvoice.core.textutil import clean_body, html_to_text, truncate_for_llm


def test_html_to_text_basic():
    """Test basic HTML to text conversion."""
    html = "<p>Hello <b>world</b></p>"
    result = html_to_text(html)
    assert result == "Hello world"


def test_html_to_text_entities():
    """Test HTML entity decoding."""
    html = "<p>&amp; &nbsp; &oacute;</p>"
    result = html_to_text(html)
    assert result == "& ó"


def test_html_to_text_script_style():
    """Test that script and style content is skipped."""
    html = (
        "<p>Hello</p><script>alert('test');</script><style>body {color: red;}</style><p>World</p>"
    )
    result = html_to_text(html)
    assert result == "Hello\n\nWorld"


def test_html_to_text_newlines():
    """Test block element newlines."""
    html = "<p>Hello</p><div>World</div><br><h1>Title</h1>"
    result = html_to_text(html)
    assert result == "Hello\n\nWorld\n\nTitle"


def test_clean_body_quotes():
    """Test quote line removal."""
    text = "Hello\n> This is a quote\n> Another quote\nWorld"
    result = clean_body(text)
    assert result == "Hello\nWorld"


def test_clean_body_signature():
    """Test signature removal."""
    text = "Hello\n-- \nSignature line\nAnother line"
    result = clean_body(text)
    assert result == "Hello"


def test_clean_body_both():
    """Test both quote and signature removal."""
    text = "Hello\n> Quote line\n-- \nSignature line"
    result = clean_body(text)
    assert result == "Hello"


def test_truncate_for_llm_word_boundary():
    """Test truncation at word boundary."""
    text = "This is a very long text that should be truncated at the last word boundary"
    result = truncate_for_llm(text, 20)
    assert result == "This is a very long…"
    assert len(result) <= 20


def test_truncate_for_llm_short_text():
    """Test truncation of short text (no change)."""
    text = "Short text"
    result = truncate_for_llm(text, 20)
    assert result == text


def test_truncate_for_llm_punctuation():
    """Test truncation with Polish characters."""
    text = "To jest tekst z polskimi znakami: ąęółćśźż"
    result = truncate_for_llm(text, 15)
    assert result == "To jest tekst…"


def test_html_to_text_empty():
    """Test empty input."""
    result = html_to_text("")
    assert result == ""


def test_clean_body_empty():
    """Test empty input."""
    result = clean_body("")
    assert result == ""


def test_truncate_for_llm_empty():
    """Test empty input."""
    result = truncate_for_llm("", 10)
    assert result == ""


def test_html_to_text_whitespace():
    """Test whitespace handling."""
    html = "<p>  Hello   \n\n  world  </p>"
    result = html_to_text(html)
    assert result == "Hello world"


def test_clean_body_whitespace():
    """Test whitespace handling in clean_body."""
    text = "Hello\n\n\n\nWorld"
    result = clean_body(text)
    assert result == "Hello\n\nWorld"
