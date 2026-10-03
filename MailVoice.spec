# -*- mode: python ; coding: utf-8 -*-
"""Konfiguracja PyInstaller dla MailVoice (Windows, tryb --onedir).

Budowanie:  pyinstaller MailVoice.spec --noconfirm
Wynik:      dist/MailVoice/MailVoice.exe  (+ katalog z bibliotekami)

Celowo --onedir (nie --onefile): szybszy start i mniej fałszywych alarmów antywirusa.
Modele głosu/Whisper pobierają się po instalacji (NIE są pakowane do .exe).
Na Windows TTS używa głosów systemowych (SAPI), więc Piper nie jest potrzebny.
"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ["mailvoice"]

# Pakiety z natywnymi bibliotekami/danymi, których PyInstaller sam nie wykrywa w całości.
# faster-whisper + ctranslate2 + onnxruntime + av = rozpoznawanie mowy (komendy głosowe z mikrofonu).
# Jeśli komendy głosowe nie są potrzebne, można je usunąć z listy — .exe będzie znacznie mniejszy.
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "sounddevice"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["run_mailvoice.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MailVoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI — bez okna konsoli (błędy trafiają do logu przez crashlog)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MailVoice",
)
