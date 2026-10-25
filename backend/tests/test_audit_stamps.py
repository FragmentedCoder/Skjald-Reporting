from datetime import UTC, datetime, timedelta

import pytest
from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko.sign.timestamps import DummyTimeStamper
from pyhanko_certvalidator import ValidationContext
from sqlalchemy import select, text

from app import audit, audit_stamps, jobs
from app.audit import AuditEntry
from app.audit_stamps import AuditStamp, StampError
from app.roles import Role, grant_role

VERIFY = "/api/audit/verify"


def _certificate() -> tuple[asn1_x509.Certificate, asn1_keys.PrivateKeyInfo]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
        .sign(key, hashes.SHA256())
    )
    return (
        asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
        asn1_keys.PrivateKeyInfo.load(key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())),
    )


@pytest.fixture
def tsa(monkeypatch):
    """An in-process timestamp authority, trusted here."""
    cert, key = _certificate()
    monkeypatch.setattr(audit_stamps, "stamper",
                        lambda url: DummyTimeStamper(tsa_cert=cert, tsa_key=key))
    monkeypatch.setattr(audit_stamps, "validation_context",
                        lambda: ValidationContext(trust_roots=[cert]))
    return cert


def _drop_triggers(session) -> None:
    """What someone with the database file and its key can do."""
    names = session.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger' "
                                 "AND tbl_name = 'audit_log'")).scalars().all()
    for name in names:
        session.execute(text(f"DROP TRIGGER {name}"))


def stamp(session):
    job = jobs.enqueue(session, "audit_stamp")
    session.commit()
    jobs.run_one(session)
    return job


def test_the_newest_entry_is_timestamped(tsa, session) -> None:
    for n in range(3):
        audit.append(session, "test.entry", details={"n": n})
    session.commit()
    job = stamp(session)
    assert job.state == "done", job.error
    assert job.outcome()["seq"] == 3 and job.outcome()["trusted"] is True
    record = session.scalar(select(AuditStamp))
    assert record.seq == 3 and record.tsa_url == audit_stamps.DEFAULT_TSA
    assert audit_stamps.check(session).ok
    logged = session.scalar(select(AuditEntry).where(AuditEntry.action == "audit.stamped"))
    assert logged is not None and logged.seq == 4


def test_a_log_cut_short_shows_even_though_its_chain_still_holds(tsa, session) -> None:
    for n in range(5):
        audit.append(session, "test.entry", details={"n": n})
    session.commit()
    stamp(session)  # stamps entry 5; entry 6 says so
    _drop_triggers(session)
    session.execute(text("DELETE FROM audit_log WHERE seq >= 5"))
    session.commit()
    assert audit.verify(session).ok  # the shorter chain is still a valid chain
    result = audit_stamps.check(session)
    assert not result.ok and "Entry 5" in result.problem and "cut short" in result.problem


def test_a_changed_stamped_entry_shows(tsa, session) -> None:
    audit.append(session, "test.entry", details={"n": 1})
    session.commit()
    stamp(session)
    _drop_triggers(session)
    session.execute(text("UPDATE audit_log SET hash = :h WHERE seq = 1"), {"h": "0" * 64})
    session.commit()
    assert "has changed" in audit_stamps.check(session).problem


def test_an_unreachable_authority_fails_the_job_plainly(session, monkeypatch) -> None:
    class Down:
        async def async_timestamp(self, digest, md_algorithm):
            raise ConnectionError("no route to host")

    monkeypatch.setattr(audit_stamps, "stamper", lambda url: Down())
    audit.append(session, "test.entry", details={})
    session.commit()
    job = stamp(session)
    assert job.state == "queued" and "didn't answer usefully" in job.error
    assert session.scalar(select(AuditStamp)) is None
    failed = session.scalar(select(AuditEntry).where(AuditEntry.action == "audit.stamp_failed"))
    assert failed is not None


def test_a_token_for_something_else_is_refused(tsa, session, monkeypatch) -> None:
    original = audit_stamps.stamper("http://tsa.test")

    class Elsewhere:
        async def async_timestamp(self, digest, md_algorithm):
            return await original.async_timestamp(b"\x00" * 32, md_algorithm)

    monkeypatch.setattr(audit_stamps, "stamper", lambda url: Elsewhere())
    audit.append(session, "test.entry", details={})
    session.commit()
    with pytest.raises(StampError):
        audit_stamps.stamp(session)


def test_it_is_due_once_a_day_once_there_is_something_to_stamp(frozen_clock, session) -> None:
    assert audit_stamps._daily(session, frozen_clock.now) == []
    audit.append(session, "test.entry", details={})
    session.commit()
    assert audit_stamps._daily(session, frozen_clock.now) == [
        ("audit_stamp", "audit_stamp/2026-10-24", {})]


# The pages


def test_the_chain_check_includes_the_timestamps(tsa, client, admin, session) -> None:
    _, headers = admin
    stamp(session)
    checked = client.get(VERIFY, headers=headers).json()
    assert checked["ok"] and checked["stamps_ok"] and checked["stamps"] == 1
    assert checked["last_stamped_seq"] is not None
    assert checked["tsa_url"] == audit_stamps.DEFAULT_TSA


def test_administrators_choose_the_authority_and_stamp_now(client, admin, session, make_user,
                                                           full_session) -> None:
    _, headers = admin
    changed = client.put("/api/audit/stamps/authority", headers=headers,
                         json={"tsa_url": "https://freetsa.org/tsr"})
    assert changed.json()["tsa_url"] == "https://freetsa.org/tsr"
    assert client.put("/api/audit/stamps/authority", headers=headers,
                      json={"tsa_url": "ftp://nope"}).status_code == 422
    first = client.post("/api/audit/stamps/run", headers=headers).json()
    again = client.post("/api/audit/stamps/run", headers=headers).json()
    assert first["id"] == again["id"] and first["state"] == "queued"

    auditor = make_user("ulf")
    grant_role(session, auditor, Role.AUDITOR, actor=None, ip=None)
    session.commit()
    as_auditor = full_session(auditor)
    assert client.get(VERIFY, headers=as_auditor).status_code == 200
    assert client.post("/api/audit/stamps/run", headers=as_auditor).status_code == 403


def test_the_health_check_reports_the_timestamp(tsa, frozen_clock, session) -> None:
    from app.maintenance import _run_stamps

    assert _run_stamps(session).status == "warning"  # none yet
    audit.append(session, "test.entry", details={})
    session.commit()
    stamp(session)
    record = session.scalar(select(AuditStamp))
    frozen_clock.now = record.stamped_at + timedelta(hours=1)
    assert _run_stamps(session).status == "ok"
    frozen_clock.now = record.stamped_at + timedelta(days=3)
    assert _run_stamps(session).status == "problem"
