import sqlite3
from pathlib import Path

from mailvoice.core.devices import DeviceManager
from mailvoice.core.migrate import migrate_server_state


def _old_state(config_dir: Path) -> None:
    config_dir.mkdir(parents=True)
    (config_dir / "server.crt").write_text("CERT")
    (config_dir / "server.key").write_text("KEY")
    mgr = DeviceManager(config_dir / "mailvoice.db")
    session = mgr.start_pairing_session()
    mgr.pair_device(session.code, "Telefon testowy")
    mgr.close()


def test_moves_certificate_and_devices_without_changing_the_certificate(tmp_path):
    cfg, data = tmp_path / "config", tmp_path / "data"
    _old_state(cfg)
    done = migrate_server_state(cfg, data)
    assert (data / "server.crt").read_text() == "CERT"  # ten sam certyfikat = ten sam odcisk
    assert (data / "server.key").read_text() == "KEY"
    assert not (cfg / "server.crt").exists()
    assert len(done) == 3
    mgr = DeviceManager(data / "mailvoice.db")
    assert [d.name for d in mgr.list_devices(include_revoked=False)] == ["Telefon testowy"]


def test_migration_runs_once_and_does_not_resurrect_removed_devices(tmp_path):
    cfg, data = tmp_path / "config", tmp_path / "data"
    _old_state(cfg)
    migrate_server_state(cfg, data)
    conn = sqlite3.connect(data / "mailvoice.db")
    conn.execute("DELETE FROM paired_devices")
    conn.commit()
    conn.close()
    assert migrate_server_state(cfg, data) == []  # nic do zrobienia
    mgr = DeviceManager(data / "mailvoice.db")
    assert mgr.list_devices(include_revoked=True) == []  # usunięte urządzenie nie wraca
    assert (cfg / "mailvoice.db.migrated").exists()  # stara baza odłożona, nie skasowana


def test_does_not_overwrite_existing_certificate_in_data_dir(tmp_path):
    cfg, data = tmp_path / "config", tmp_path / "data"
    _old_state(cfg)
    data.mkdir()
    (data / "server.crt").write_text("NOWY")
    migrate_server_state(cfg, data)
    assert (data / "server.crt").read_text() == "NOWY"


def test_same_directory_is_a_noop(tmp_path):
    assert migrate_server_state(tmp_path, tmp_path) == []


def test_main_window_does_not_use_config_dir_as_data_dir():
    src = (Path(__file__).resolve().parents[1] / "src/mailvoice/ui/main_window.py").read_text(
        encoding="utf-8"
    )
    assert "self.config_path.parent" not in src
