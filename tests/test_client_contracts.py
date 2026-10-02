"""Testy kontraktowe i statyczne wywołań metod klientów IMAP i Ollama w ui/ i core/."""

import ast
import inspect
from pathlib import Path

from mailvoice.core.analyzer import OllamaClient
from mailvoice.core.imap_fetch import ImapToolsClient, MailboxClient
from tests.test_imap_fetch import FakeMailboxClient


def test_mailbox_client_protocol_parity():
    """Weryfikuje, że MailboxClient, ImapToolsClient i FakeMailboxClient mają spójne metody."""
    protocol_methods = {
        name
        for name, member in inspect.getmembers(MailboxClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    imap_tools_methods = {
        name
        for name, member in inspect.getmembers(ImapToolsClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    fake_methods = {
        name
        for name, member in inspect.getmembers(FakeMailboxClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Wszystkie metody z protokołu muszą istnieć w ImapToolsClient i FakeMailboxClient
    assert protocol_methods.issubset(imap_tools_methods)
    assert protocol_methods.issubset(fake_methods)

    # login() i logout() nie mogą istnieć
    assert "login" not in protocol_methods
    assert "login" not in imap_tools_methods
    assert "logout" not in protocol_methods
    assert "logout" not in imap_tools_methods


def test_no_login_or_logout_calls_in_src():
    """Żaden plik w src/ nie może wywoływać client.login() ani client.logout()."""
    src_dir = Path(__file__).resolve().parent.parent / "src"
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "client.login(" not in content, f"Wykryto client.login() w {py_file}"
        assert "client.logout(" not in content, f"Wykryto client.logout() w {py_file}"


def test_ast_client_method_calls_exist():
    """Weryfikuje statycznie przez AST, że wszystkie metody wywoływane na klientach istnieją."""
    src_dir = Path(__file__).resolve().parent.parent / "src"

    imap_methods = {
        name
        for name, _ in inspect.getmembers(ImapToolsClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    ollama_methods = {
        name
        for name, _ in inspect.getmembers(OllamaClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    for py_file in src_dir.rglob("*.py"):
        # Pomijamy analyzer.py, gdzie 'client' to httpx.Client
        if py_file.name == "analyzer.py":
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue

            method_name = node.func.attr
            caller = node.func.value

            # Sprawdzamy wywołania na 'client' lub '*_client'
            if isinstance(caller, ast.Name):
                var_name = caller.id
                if var_name in ("client", "mailbox_client", "imap_client"):
                    # Powinno być w imap_methods LUB ollama_methods
                    is_valid = (method_name in imap_methods) or (method_name in ollama_methods)
                    assert is_valid, (
                        f"W pliku {py_file.name}:{node.lineno} wywołano nieznaną metodę "
                        f"'{method_name}' na zmiennej '{var_name}'."
                    )
            elif isinstance(caller, ast.Attribute):
                # np. deps.ollama_client.classify()
                attr_name = caller.attr
                if attr_name == "ollama_client":
                    assert method_name in ollama_methods, (
                        f"W pliku {py_file.name}:{node.lineno} wywołano nieznaną metodę "
                        f"'{method_name}' na obiekcie Ollama ({attr_name})."
                    )
                elif attr_name in ("imap_client", "mailbox_client"):
                    assert method_name in imap_methods, (
                        f"W pliku {py_file.name}:{node.lineno} wywołano nieznaną metodę "
                        f"'{method_name}' na obiekcie IMAP ({attr_name})."
                    )
