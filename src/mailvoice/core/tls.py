"""Obsługa TLS dla serwera mobilnego MailVoice (certyfikat samopodpisany ECDSA)."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@dataclass(frozen=True)
class TlsCredentials:
    """Ścieżki i metadane wygenerowanego certyfikatu i klucza TLS."""

    cert_path: Path
    key_path: Path
    fingerprint: str


def detect_lan_ip() -> str:
    """Wykrywa domyślny adres IP w sieci lokalnej (LAN)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Nie wysyła pakietów, służy jedynie do wyznaczenia routingu jądra
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def fingerprint_sha256(cert: x509.Certificate | bytes | str | Path) -> str:
    """Zwraca odcisk palca SHA-256 certyfikatu jako 64-znakowy ciąg heksadecymalny."""
    if isinstance(cert, Path):
        cert = cert.read_bytes()
    if isinstance(cert, str):
        cert = cert.encode("utf-8")
    if isinstance(cert, bytes):
        # Sprawdzamy czy to PEM czy DER
        if b"-----BEGIN CERTIFICATE-----" in cert:
            cert_obj = x509.load_pem_x509_certificate(cert)
        else:
            cert_obj = x509.load_der_x509_certificate(cert)
    else:
        cert_obj = cert

    return cert_obj.fingerprint(hashes.SHA256()).hex().lower()


def generate_self_signed_cert(
    san_hosts: Sequence[str] | None = None,
    days_valid: int = 730,
    start_time: datetime | None = None,
) -> tuple[bytes, bytes, str]:
    """Generuje samopodpisany certyfikat ECDSA P-256 oraz klucz prywatny.

    Zwraca krotkę (cert_pem, key_pem, fingerprint_hex).
    """
    private_key = ec.generate_private_key(ec.SECP256R1())

    now = start_time or datetime.now(timezone.utc)
    # Cofnięcie o 1 godzinę zabezpiecza przed ewentualną rozbieżnością zegarów urządzeń
    not_before = now - timedelta(hours=1)
    not_after = now + timedelta(days=days_valid)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "MailVoice Mobile Server"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MailVoice"),
        ]
    )

    san_entries: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address("::1")),
    ]

    hosts = list(san_hosts or [])
    for host in hosts:
        host = host.strip()
        if not host:
            continue
        try:
            ip_obj = ipaddress.ip_address(host)
            if ip_obj not in [e.value for e in san_entries if isinstance(e, x509.IPAddress)]:
                san_entries.append(x509.IPAddress(ip_obj))
        except ValueError:
            if host not in [e.value for e in san_entries if isinstance(e, x509.DNSName)]:
                san_entries.append(x509.DNSName(host))

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
    )

    cert = builder.sign(private_key, hashes.SHA256())

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fp = cert.fingerprint(hashes.SHA256()).hex().lower()

    return cert_pem, key_pem, fp


def _atomic_write_secure(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Zapisuje dane atomowo do pliku, wymuszając określone uprawnienia (np. 0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".tmp.{os.getpid()}_{hashlib.sha256(data).hexdigest()[:8]}")

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY  # type: ignore[attr-defined]

    fd = os.open(str(tmp_path), flags, mode)
    try:
        with open(fd, "wb", closefd=True) as f:
            f.write(data)
        try:
            os.chmod(tmp_path, mode)
        except OSError:
            pass
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def get_or_create_server_tls(
    data_dir: Path,
    lan_ip: str | None = None,
    force_recreate: bool = False,
) -> TlsCredentials:
    """Zapewnia obecność ważnego certyfikatu TLS i klucza w katalogu danych.

    Gdy pliki nie istnieją, klucz lub certyfikat jest uszkodzony, bądź certyfikat
    wygasa w ciągu najbliższych 7 dni — tworzy nową parę z uprawnieniami 0600 dla klucza.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    cert_path = data_dir / "server.crt"
    key_path = data_dir / "server.key"

    resolved_ip = lan_ip or detect_lan_ip()

    if not force_recreate and cert_path.exists() and key_path.exists():
        try:
            cert_bytes = cert_path.read_bytes()
            key_bytes = key_path.read_bytes()

            cert = x509.load_pem_x509_certificate(cert_bytes)
            # Weryfikacja klucza
            serialization.load_pem_private_key(key_bytes, password=None)

            # Sprawdzenie wygasania (odnawiamy jeśli zostało mniej niż 7 dni)
            now = datetime.now(timezone.utc)
            expiry = cert.not_valid_after_utc
            if now < expiry - timedelta(days=7):
                # Sprawdzenie czy IP LAN jest w SAN
                has_ip = False
                try:
                    san_ext = cert.extensions.get_extension_for_oid(
                        x509.OID_SUBJECT_ALTERNATIVE_NAME
                    )
                    san = san_ext.value
                    if isinstance(san, x509.SubjectAlternativeName):
                        for item in san:
                            if isinstance(item, x509.IPAddress) and str(item.value) == resolved_ip:
                                has_ip = True
                                break
                except Exception:
                    has_ip = True  # Jeśli brak SAN lub błąd, zachowaj certyfikat

                if has_ip or resolved_ip == "127.0.0.1":
                    fp = fingerprint_sha256(cert)
                    return TlsCredentials(
                        cert_path=cert_path,
                        key_path=key_path,
                        fingerprint=fp,
                    )
        except Exception:
            # W razie jakiegokolwiek uszkodzenia regenerujemy
            pass

    # Generowanie nowej pary
    san_list = ["localhost", "127.0.0.1", "::1"]
    if resolved_ip and resolved_ip not in san_list:
        san_list.append(resolved_ip)

    cert_pem, key_pem, fp = generate_self_signed_cert(san_hosts=san_list)

    # Zapis klucza z uprawnieniami 0600 (tylko odczyt/zapis właściciela)
    _atomic_write_secure(key_path, key_pem, mode=0o600)
    # Zapis certyfikatu (publiczny, 0644)
    _atomic_write_secure(cert_path, cert_pem, mode=0o644)

    return TlsCredentials(
        cert_path=cert_path,
        key_path=key_path,
        fingerprint=fp,
    )


# Alias dla kompatybilności wstecznej
get_or_create_tls_credentials = get_or_create_server_tls
