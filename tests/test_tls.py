"""Testy modułu TLS (certyfikat samopodpisany, odcisk palca, uprawnienia 0600)."""

import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509

from mailvoice.core.tls import (
    fingerprint_sha256,
    generate_self_signed_cert,
    get_or_create_server_tls,
)


def test_generate_self_signed_cert():
    """Weryfikuje generowanie certyfikatu ECDSA P-256 z odpowiednim SAN i okresem ważności."""
    cert_pem, key_pem, fp = generate_self_signed_cert(san_hosts=["192.168.1.100"])

    assert b"-----BEGIN CERTIFICATE-----" in cert_pem
    assert b"-----BEGIN PRIVATE KEY-----" in key_pem
    assert len(fp) == 64
    assert fp.isalnum()

    cert = x509.load_pem_x509_certificate(cert_pem)
    assert cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=700)

    # Sprawdzenie SAN
    san_ext = cert.extensions.get_extension_for_oid(x509.OID_SUBJECT_ALTERNATIVE_NAME)
    san = san_ext.value
    assert isinstance(san, x509.SubjectAlternativeName)
    ip_values = [str(item.value) for item in san if isinstance(item, x509.IPAddress)]
    assert "192.168.1.100" in ip_values
    assert "127.0.0.1" in ip_values


def test_fingerprint_sha256_stability():
    """Weryfikuje stabilność i spójność odcisku palca SHA-256."""
    cert_pem, _, fp = generate_self_signed_cert()
    cert = x509.load_pem_x509_certificate(cert_pem)

    fp_from_obj = fingerprint_sha256(cert)
    fp_from_bytes = fingerprint_sha256(cert_pem)
    fp_from_str = fingerprint_sha256(cert_pem.decode("utf-8"))

    assert fp == fp_from_obj
    assert fp == fp_from_bytes
    assert fp == fp_from_str


def test_get_or_create_server_tls_permissions_and_reuse(tmp_path: Path):
    """Weryfikuje bezpieczne uprawnienia pliku klucza (0600) oraz ponowne użycie certyfikatu."""
    creds1 = get_or_create_server_tls(tmp_path, lan_ip="192.168.1.50")

    assert creds1.cert_path.exists()
    assert creds1.key_path.exists()
    assert len(creds1.fingerprint) == 64

    # Weryfikacja uprawnień 0600 na systemach uniksowych (Linux/macOS)
    if os.name == "posix":
        mode = stat.S_IMODE(creds1.key_path.stat().st_mode)
        assert mode == 0o600, f"Klucz prywatny musi mieć uprawnienia 0600, ma {oct(mode)}"

    # Ponowne wywołanie powinno zwrócić istniejące poświadczenia bez generowania na nowo
    creds2 = get_or_create_server_tls(tmp_path, lan_ip="192.168.1.50")
    assert creds2.fingerprint == creds1.fingerprint
    assert creds2.key_path.read_bytes() == creds1.key_path.read_bytes()


def test_get_or_create_server_tls_regenerates_when_expired(tmp_path: Path):
    """Weryfikuje automatyczne odnawianie certyfikatu gdy zbliża się wygaśnięcie."""
    # Tworzymy certyfikat z przeszłą datą wygaśnięcia
    past = datetime.now(timezone.utc) - timedelta(days=30)
    cert_pem, key_pem, _ = generate_self_signed_cert(start_time=past, days_valid=1)
    cert_path = tmp_path / "server.crt"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    old_fp = fingerprint_sha256(cert_pem)

    creds = get_or_create_server_tls(tmp_path, lan_ip="192.168.1.50")
    assert creds.fingerprint != old_fp

    cert = x509.load_pem_x509_certificate(creds.cert_path.read_bytes())
    assert cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=700)


def test_get_or_create_server_tls_regenerates_when_corrupted(tmp_path: Path):
    """Weryfikuje bezpieczne odtworzenie gdy plik klucza lub certyfikatu jest uszkodzony."""
    cert_path = tmp_path / "server.crt"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(b"BLEDNY_CERTYFIKAT")
    key_path.write_bytes(b"BLEDNY_KLUCZ")

    creds = get_or_create_server_tls(tmp_path)
    assert creds.cert_path.exists()
    assert b"-----BEGIN CERTIFICATE-----" in creds.cert_path.read_bytes()
    assert b"-----BEGIN PRIVATE KEY-----" in creds.key_path.read_bytes()
