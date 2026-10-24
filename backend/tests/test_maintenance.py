import io

import pytest
from PIL import Image
from sqlalchemy import select, text

from app import maintenance
from app.audit import AuditEntry
from app.policy import SecurityPolicy, save_policy
from app.roles import Role, grant_role


def actions(session):
    found = list(session.scalars(select(AuditEntry.action).order_by(AuditEntry.seq)))
    session.commit()
    return found


def logo(fmt="PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (1200, 300), (20, 40, 80, 255)).save(out, format=fmt)
    return out.getvalue()


# Branding


def test_branding_starts_with_the_defaults_and_needs_no_sign_in(client) -> None:
    assert client.get("/api/branding").json() == {
        "site_name": "Skjald", "tagline": "Reports worth keeping.", "company_name": None,
        "logo_url": None,
    }


def test_an_administrator_can_rename_the_site(client, admin, session) -> None:
    _, headers = admin
    saved = client.put("/api/admin/branding", headers=headers, json={
        "site_name": "Nordlys Rapport", "tagline": "", "company_name": "Nordlys IT ApS",
    }).json()
    assert saved["site_name"] == "Nordlys Rapport" and saved["tagline"] == ""
    assert client.get("/api/branding").json()["company_name"] == "Nordlys IT ApS"
    assert "admin.branding_changed" in actions(session)
    blank = client.put("/api/admin/branding", headers=headers,
                       json={"site_name": "", "company_name": "Nordlys IT ApS"})
    assert blank.status_code == 422


def test_a_logo_is_cleaned_and_shown_on_the_sign_in_page(client, admin, new_client) -> None:
    _, headers = admin
    uploaded = client.put("/api/admin/branding/logo", content=logo("WEBP"),
                          headers=headers | {"Content-Type": "application/octet-stream"})
    url = uploaded.json()["logo_url"]
    served = new_client().get(url)
    assert served.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(served.content)) as image:
        assert image.size == (512, 128)

    assert client.delete("/api/admin/branding/logo", headers=headers).json()["logo_url"] is None
    assert new_client().get(url).status_code == 404


def test_only_administrators_change_the_branding(client, make_user, session, full_session):
    technician = make_user()
    grant_role(session, technician, Role.TECHNICIAN, actor=None, ip=None)
    session.commit()
    headers = full_session(technician)
    assert client.put("/api/admin/branding", headers=headers, json={
        "site_name": "Mine now", "company_name": "Mine",
    }).status_code == 403
    assert client.put("/api/admin/branding/logo", content=logo(),
                      headers=headers | {"Content-Type": "application/octet-stream"}
                      ).status_code == 403


# Server health


@pytest.fixture(autouse=True)
def server(monkeypatch, data_dir, master_key_path):
    from app.settings import settings

    monkeypatch.setattr(settings, "data_dir", str(data_dir))
    monkeypatch.setattr(settings, "master_key_path", str(master_key_path))


def health_checks(client, headers):
    health = client.get("/api/admin/health", headers=headers).json()
    return {check["key"]: check for check in health["checks"]}


@pytest.fixture
def reachable(monkeypatch):
    calls = []
    monkeypatch.setattr(maintenance.pwned, "reachable", lambda: calls.append(1) or True)
    return calls


def test_the_health_page_checks_everything_that_matters(client, admin, reachable) -> None:
    _, headers = admin
    health = client.get("/api/admin/health", headers=headers).json()
    checks = {check["key"]: check for check in health["checks"]}
    assert set(checks) == {"database", "audit_chain", "keys", "disk", "breach_check"}
    assert checks["database"]["status"] == "ok"
    assert checks["audit_chain"]["status"] == "ok"
    assert checks["audit_chain"]["detail"].startswith("Chain intact")
    assert checks["breach_check"]["status"] == "ok" and reachable == [1]
    assert health["versions"]["schema_version"] == "0006"
    assert health["versions"]["sqlcipher"]
    assert any(p["name"] == "fastapi" for p in health["packages"])
    assert health["usage"]["users"] == 1 and health["usage"]["sessions"] == 1
    assert health["usage"]["disk_total_bytes"] >= health["usage"]["disk_free_bytes"] > 0


def test_a_broken_audit_chain_shows_on_the_health_page(client, admin, engine, reachable):
    _, headers = admin
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_log_no_update"))
        conn.execute(text("UPDATE audit_log SET actor_name = 'someone else' WHERE seq = 1"))
    checks = health_checks(client, headers)
    assert checks["audit_chain"]["status"] == "problem"
    assert "entry 1" in checks["audit_chain"]["detail"]


def test_the_breach_check_is_not_called_when_switched_off(
    client, admin, session, reachable
) -> None:
    _, headers = admin
    save_policy(session, SecurityPolicy(breach_check_enabled=False))
    session.commit()
    checks = health_checks(client, headers)
    assert checks["breach_check"]["status"] == "off" and reachable == []


GIB = maintenance.GIB


@pytest.mark.parametrize(("total", "free", "status"), [
    (100 * GIB, 50 * GIB, "ok"),
    (100 * GIB, 10 * GIB, "warning"),  # under 15 % free
    (3 * GIB, int(1.5 * GIB), "warning"),  # half free, but under 2 GB
    (100 * GIB, GIB // 2, "problem"),
])
def test_low_disk_space_is_flagged(total, free, status) -> None:
    assert maintenance._disk_check(total, free).status == status


def test_only_administrators_see_server_health(client, make_user, session, full_session):
    auditor = make_user()
    grant_role(session, auditor, Role.AUDITOR, actor=None, ip=None)
    session.commit()
    assert client.get("/api/admin/health", headers=full_session(auditor)).status_code == 403
