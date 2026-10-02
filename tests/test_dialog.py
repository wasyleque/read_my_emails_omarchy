def test_microphone_problem_is_reported_not_swallowed():
    """Regresja: martwy mikrofon był połykany i dialog pytał w kółko bez słowa wyjaśnienia."""
    from mailvoice.voice.dialog import VoiceDialog
    from mailvoice.voice.tts import FakeSpeaker, VoiceUnavailable

    class DeadListener:
        def listen(self, timeout_s: float = 5.0):
            raise VoiceUnavailable("Mikrofon nie przekazuje dźwięku.")

    dialog = VoiceDialog(speaker=FakeSpeaker(), listener=DeadListener(), service=None)
    problems: list[str] = []
    dialog.on_problem = problems.append
    assert dialog._listen() is None
    assert dialog._listen() is None  # ten sam komunikat tylko raz
    assert problems == ["Mikrofon nie przekazuje dźwięku."]
