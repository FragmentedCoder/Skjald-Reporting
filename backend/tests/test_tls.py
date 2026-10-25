from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select

from app import tls
from app.audit import AuditEntry
from app.settings import settings
from app.tls import TlsError, TlsSettings
from tests.conftest import PASSWORD

TLS = "/api/admin/tls"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def _key_pem(key) -> str:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def make_certificate(*names: str, days: int = 90, starts: int = -1,
                     key=None) -> tuple[str, str]:
    """A self-signed certificate for the names, and its key, as PEM."""
    key = key or ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0] if names else "x")])
    builder = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(NOW + timedelta(days=starts))
        .not_valid_after(NOW + timedelta(days=days))
    )
    if names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM).decode(), _key_pem(key)


@pytest.fixture
def tls_dir(monkeypatch, tmp_path, data_dir):
    folder = tmp_path / "tls"
    monkeypatch.setattr(settings, "tls_dir", str(folder))
    monkeypatch.setattr(settings, "data_dir", str(data_dir))
    monkeypatch.setattr(settings, "address", "https://skjald.nordlys.example")
    monkeypatch.setattr(tls, "served_certificate", lambda: None)
    return folder


def test_a_matching_certificate_for_the_address_is_described() -> None:
    chain, key = make_certificate("skjald.nordlys.example", "alt.nordlys.example")
    described = tls.check_certificate(chain, key, "skjald.nordlys.example", NOW)
    assert described.subject == "skjald.nordlys.example"
    assert described.names == ["skjald.nordlys.example", "alt.nordlys.example"]
    assert described.not_after == NOW + timedelta(days=90)


@pytest.mark.parametrize(("name", "host", "covers"), [
    ("*.nordlys.example", "skjald.nordlys.example", True),
    ("*.nordlys.example", "a.skjald.nordlys.example", False),
    ("*.nordlys.example", "nordlys.example", False),
    ("SKJALD.nordlys.example", "skjald.nordlys.example", True),
    ("skjald.nordlys.example", "skjald.nordlys.example.evil", False),
])
def test_wildcards_cover_one_level(name, host, covers) -> None:
    assert tls._covers(name, host) is covers


@pytest.mark.parametrize(("certificate", "said"), [
    (lambda: make_certificate("other.example"), "is for other.example, not"),
    (lambda: make_certificate("skjald.nordlys.example", days=-1, starts=-30), "has expired"),
    (lambda: make_certificate("skjald.nordlys.example", starts=2), "isn't valid yet"),
    (lambda: make_certificate(), "is for x, not"),
])
def test_a_certificate_that_wont_do_is_refused_plainly(certificate, said) -> None:
    chain, key = certificate()
    with pytest.raises(TlsError, match=said):
        tls.check_certificate(chain, key, "skjald.nordlys.example", NOW)


def test_a_key_from_another_certificate_is_refused() -> None:
    chain, _ = make_certificate("skjald.nordlys.example")
    _, other_key = make_certificate("skjald.nordlys.example")
    with pytest.raises(TlsError, match="isn't this certificate's key"):
        tls.check_certificate(chain, other_key, "skjald.nordlys.example", NOW)


def test_what_isnt_pem_is_refused() -> None:
    chain, key = make_certificate("skjald.nordlys.example")
    with pytest.raises(TlsError, match="isn't a certificate"):
        tls.check_certificate("hello", key, "skjald.nordlys.example", NOW)
    with pytest.raises(TlsError, match="isn't an unencrypted private key"):
        tls.check_certificate(chain, "hello", "skjald.nordlys.example", NOW)
    locked = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"secret")).decode()
    with pytest.raises(TlsError, match="isn't an unencrypted private key"):
        tls.check_certificate(chain, locked, "skjald.nordlys.example", NOW)


def test_caddy_is_told_each_way(tls_dir) -> None:
    tls.write_for_caddy(TlsSettings())
    assert (tls_dir / "tls.caddy").read_text() == "tls internal\n"
    tls.write_for_caddy(TlsSettings(mode="acme", acme_email="it@nordlys.example"))
    assert (tls_dir / "tls.caddy").read_text() == "tls it@nordlys.example\n"
    chain, key = make_certificate("skjald.nordlys.example")
    tls.write_for_caddy(TlsSettings(mode="own"), chain, key)
    assert (tls_dir / "tls.caddy").read_text() == (
        "tls /etc/caddy/skjald/cert.pem /etc/caddy/skjald/key.pem\n")
    assert (tls_dir / "cert.pem").read_text() == chain
    assert (tls_dir / "key.pem").stat().st_mode & 0o777 == 0o600
    assert not list(tls_dir.glob(".*.tmp"))


def test_an_own_certificate_whose_files_are_gone_falls_back(tls_dir, engine, session,
                                                           monkeypatch) -> None:
    from app import db as db_module

    monkeypatch.setattr(db_module, "get_engine", lambda: engine)
    tls.save_tls(session, TlsSettings(mode="own"))
    session.commit()
    tls.main()
    assert (tls_dir / "tls.caddy").read_text() == "tls internal\n"


# The admin panel


def test_uploading_a_certificate_needs_a_fresh_confirmation(client, admin, tls_dir,
                                                           session) -> None:
    _, headers = admin
    status = client.get(TLS, headers=headers).json()
    assert status["settings"]["mode"] == "internal" and status["root_url"] == "/skjald-root.crt"
    chain, key = make_certificate("skjald.nordlys.example", days=400, starts=-400)
    upload = {"mode": "own", "certificate_pem": chain, "key_pem": key}
    refused = client.put(TLS, headers=headers, json=upload)
    assert refused.headers["X-Skjald-Reason"] == "step_up_required"
    assert not (tls_dir / "key.pem").exists()
    client.post("/api/auth/confirm-password", headers=headers, json={"password": PASSWORD})
    saved = client.put(TLS, headers=headers, json=upload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"]["certificate"]["subject"] == "skjald.nordlys.example"
    assert saved.json()["root_url"] is None and "PRIVATE KEY" not in saved.text
    assert (tls_dir / "key.pem").read_text() == key
    logged = session.scalar(select(AuditEntry.details).where(AuditEntry.action == "tls.changed"))
    assert "skjald.nordlys.example" in logged and "PRIVATE" not in logged


def test_a_certificate_for_another_address_is_refused(client, admin, tls_dir) -> None:
    _, headers = admin
    client.post("/api/auth/confirm-password", headers=headers, json={"password": PASSWORD})
    chain, key = make_certificate("intranet.nordlys.example", days=400, starts=-400)
    refused = client.put(TLS, headers=headers,
                         json={"mode": "own", "certificate_pem": chain, "key_pem": key})
    assert refused.status_code == 400
    assert refused.json()["detail"] == (
        "The certificate is for intranet.nordlys.example, not skjald.nordlys.example.")
    # Refused before the confirmation is used up.
    acme = client.put(TLS, headers=headers,
                      json={"mode": "acme", "acme_email": "it@nordlys.example"})
    assert acme.status_code == 200
    assert (tls_dir / "tls.caddy").read_text() == "tls it@nordlys.example\n"


def test_own_mode_without_an_upload_keeps_the_one_uploaded(client, admin, tls_dir) -> None:
    _, headers = admin
    client.post("/api/auth/confirm-password", headers=headers, json={"password": PASSWORD})
    assert client.put(TLS, headers=headers, json={"mode": "own"}).status_code == 400
    chain, key = make_certificate("skjald.nordlys.example", days=400, starts=-400)
    client.put(TLS, headers=headers, json={"mode": "own", "certificate_pem": chain,
                                            "key_pem": key})
    client.post("/api/auth/confirm-password", headers=headers, json={"password": PASSWORD})
    kept = client.put(TLS, headers=headers, json={"mode": "own"})
    assert kept.json()["settings"]["certificate"]["subject"] == "skjald.nordlys.example"


def test_an_acme_email_cannot_inject_caddy_settings(client, admin, tls_dir) -> None:
    _, headers = admin
    for sneaky in ("a@b.example\n}\nimport /etc/passwd", "a@b {", "x"):
        refused = client.put(TLS, headers=headers, json={"mode": "acme", "acme_email": sneaky})
        assert refused.status_code == 422, sneaky
