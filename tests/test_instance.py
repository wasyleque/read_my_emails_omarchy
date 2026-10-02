from mailvoice.core.instance import acquire_instance_lock


def test_second_instance_is_refused_until_first_releases(tmp_path):
    path = tmp_path / "mailvoice.lock"
    first = acquire_instance_lock(path)
    assert first is not None
    assert acquire_instance_lock(path) is None  # druga kopia odrzucona
    first.release()
    third = acquire_instance_lock(path)
    assert third is not None  # po zwolnieniu można uruchomić ponownie
    third.release()


def test_lock_survives_in_another_process_and_frees_on_exit(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "mailvoice.lock"
    code = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from mailvoice.core.instance import acquire_instance_lock\n"
        f"l = acquire_instance_lock(Path(r'{path}'))\n"
        "print('OK' if l else 'NO', flush=True)\n"
        "time.sleep(2)\n"
    )
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert child.stdout.readline().strip() == "OK"
    assert acquire_instance_lock(path) is None  # zajęte przez inny proces
    child.wait()
    again = acquire_instance_lock(path)  # proces zakończony -> blokada wolna
    assert again is not None
    again.release()
