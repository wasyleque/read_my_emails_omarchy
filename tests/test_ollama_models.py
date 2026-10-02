from mailvoice.core.ollama_models import is_cloud_model, suggest_models

INSTALLED = [
    "ALIENTELLIGENCE/roominteriorsuggester:latest",
    "codegemma:latest",
    "deepseek-r1:32b",
    "goonsai/qwen2.5-3B-goonsai-nsfw-100k:latest",
    "huihui_ai/qwen3-coder-abliterated:latest",
    "llama3.1:latest",
    "llava:latest",
    "qooba/bielik-11b-v3.0-instruct:Q4_K_M",
    "qwen3-coder:30b",
    "qwen3.5:cloud",
    "qwen3.8:latest",
]


def test_never_suggests_cloud_models():
    assert is_cloud_model("qwen3.5:cloud") and not is_cloud_model("qwen3.8:latest")
    choice = suggest_models(INSTALLED)
    assert not any(is_cloud_model(m) for m in choice.choices)


def test_picks_general_and_polish_from_installed_only():
    choice = suggest_models(INSTALLED)
    assert choice.general == "qwen3.8:latest"
    assert choice.polish == "qooba/bielik-11b-v3.0-instruct:Q4_K_M"
    assert choice.general in INSTALLED and choice.polish in INSTALLED


def test_excludes_unsuitable_models():
    choices = suggest_models(INSTALLED).choices
    for bad in (
        "llava:latest",
        "codegemma:latest",
        "qwen3-coder:30b",
        "huihui_ai/qwen3-coder-abliterated:latest",
    ):
        assert bad not in choices
    assert not any("nsfw" in m or "roominterior" in m for m in choices)


def test_empty_and_only_polish():
    assert suggest_models([]).general is None
    only = suggest_models(["qooba/bielik-11b-v3.0-instruct:Q4_K_M"])
    assert only.general == only.polish == "qooba/bielik-11b-v3.0-instruct:Q4_K_M"


def test_detect_models_variants():
    from mailvoice.core.ollama_models import detect_models

    # 1. Local działa, LAN nie
    def fetch_local_only(url: str):
        if "127.0.0.1" in url:
            return ["qwen3:8b", "bielik:latest"]
        return []

    det1 = detect_models(
        "http://127.0.0.1:11434",
        "http://192.168.1.50:11434",
        fetch=fetch_local_only,
    )
    assert det1.local_ok is True
    assert det1.lan_ok is False
    assert det1.source == "local"
    assert det1.models == ["qwen3:8b", "bielik:latest"]

    # 2. Tylko LAN działa
    def fetch_lan_only(url: str):
        if "192.168.1.50" in url:
            return ["mistral:latest"]
        return []

    det2 = detect_models(
        "http://127.0.0.1:11434",
        "http://192.168.1.50:11434",
        fetch=fetch_lan_only,
    )
    assert det2.local_ok is False
    assert det2.lan_ok is True
    assert det2.source == "lan"
    assert det2.models == ["mistral:latest"]

    # 3. Żaden nie działa
    det3 = detect_models(
        "http://127.0.0.1:11434",
        "http://192.168.1.50:11434",
        fetch=lambda u: [],
    )
    assert det3.local_ok is False
    assert det3.lan_ok is False
    assert det3.source is None
    assert det3.models == []

    # 4. Oba działają (preferuje lokalny jako źródło)
    def fetch_both(url: str):
        if "127.0.0.1" in url:
            return ["local-model:7b"]
        return ["lan-model:7b"]

    det4 = detect_models(
        "http://127.0.0.1:11434",
        "http://192.168.1.50:11434",
        fetch=fetch_both,
    )
    assert det4.local_ok is True
    assert det4.lan_ok is True
    assert det4.source == "local"
    assert det4.models == ["local-model:7b"]


def test_describe_selection():
    from mailvoice.core.ollama_models import describe_selection

    installed = ["qwen3:8b", "qooba/bielik-11b-v3.0-instruct:latest"]
    assert describe_selection("qwen3:8b", installed) == "ok"
    assert describe_selection("qwen3", installed) == "ok"
    assert describe_selection("non-existent-model", installed) == "missing"
    assert describe_selection(None, installed) == "unknown"
    assert describe_selection("", installed) == "unknown"
    assert describe_selection("qwen3:8b", []) == "unknown"


def test_get_available_models_excludes_cloud():
    from mailvoice.core.ollama_models import get_available_models

    models = ["qwen3:8b", "llama3.1:latest", "gpt:cloud", "claude-cloud:latest", "coder:latest"]
    # show_all=False: wyklucza chmurowe oraz inne nieodpowiednie (np. coder)
    basic = get_available_models(models, show_all=False)
    assert "qwen3:8b" in basic
    assert "gpt:cloud" not in basic
    assert "coder:latest" not in basic

    # show_all=True: pozwala na inne modele, ale BEZWZGLĘDNIE wyklucza chmurowe
    all_models = get_available_models(models, show_all=True)
    assert "qwen3:8b" in all_models
    assert "coder:latest" in all_models
    assert "gpt:cloud" not in all_models
    assert "claude-cloud:latest" not in all_models
    assert not any(is_cloud_model(m) for m in all_models)


def test_check_model_success_and_errors():
    from mailvoice.core.analyzer import Analysis, AnalyzerFormatError, AnalyzerTransportError
    from mailvoice.core.config import OllamaConfig
    from mailvoice.core.ollama_models import check_model

    cfg = OllamaConfig()

    # 1. Sukces
    class DummyClientOk:
        def __init__(self, c):
            self.cfg = c

        def classify(self, messages, model):
            return Analysis(importance=5, reason="Ważne", action="read_now", language="pl")

    res_ok = check_model(cfg, "qwen3:8b", client_factory=DummyClientOk)
    assert res_ok.ok is True
    assert "Model działa poprawnie" in res_ok.message
    assert res_ok.elapsed_s >= 0.0

    # 2. Błąd 404 (model niezainstalowany na serwerze)
    class DummyClient404:
        def __init__(self, c):
            self.cfg = c

        def classify(self, messages, model):
            raise AnalyzerTransportError(
                "Serwery AI zawiodły: http://lan -> HTTP 404 (model nie znaleziony na serwerze)"
            )

    res_404 = check_model(cfg, "unknown:latest", client_factory=DummyClient404)
    assert res_404.ok is False
    assert "nie jest zainstalowany na serwerze Ollama" in res_404.message

    # 3. Brak połączenia z serwerem
    class DummyClientConn:
        def __init__(self, c):
            self.cfg = c

        def classify(self, messages, model):
            raise AnalyzerTransportError(
                "Serwery AI zawiodły: http://lan -> połączenie odrzucone lub brak serwera"
            )

    res_conn = check_model(cfg, "qwen3:8b", client_factory=DummyClientConn)
    assert res_conn.ok is False
    assert "Nie można połączyć się z serwerem" in res_conn.message

    # 4. Zły format odpowiedzi
    class DummyClientFormat:
        def __init__(self, c):
            self.cfg = c

        def classify(self, messages, model):
            raise AnalyzerFormatError("Niepoprawny JSON z Ollamy")

    res_fmt = check_model(cfg, "qwen3:8b", client_factory=DummyClientFormat)
    assert res_fmt.ok is False
    assert len(res_fmt.message) > 0

