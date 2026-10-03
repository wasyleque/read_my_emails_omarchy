"""Punkt wejścia dla PyInstaller (buduje .exe uruchamiający GUI MailVoice)."""

import sys

from mailvoice.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
