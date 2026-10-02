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
