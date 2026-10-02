import pytest

from mailvoice.core.digest import reset_llm_cooldown


@pytest.fixture(autouse=True)
def _reset_digest_llm_cooldown():
    """Wyciszenie modelu po awarii jest globalne — testy nie mogą go sobie przekazywać."""
    reset_llm_cooldown()
    yield
    reset_llm_cooldown()
