"""Report styles: how layers stack, what a style may hold, the API's roles, sealing,
and the styles customers' reports use.

shared/styles/cases.json runs here and in the browser's tests (resolve.test.ts).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app import backgrounds, jobs
from app.audit import AuditEntry
from app.customers import Customer
from app.roles import Role, grant_role
from app.styles import artwork
from app.styles.content import DEFAULT, StyleContent, problems, resolve
from app.styles.models import CustomerStyles, Style, StyleAsset, StyleUpload, StyleVersion

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "shared" / "styles"
CASES = json.loads((SHARED / "cases.json").read_text())["cases"]
STYLES = "/api/styles"


def at(value: Any, path: str) -> Any:
    for part in path.split("."):
        if part == "length":
            return len(value)
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_stacking_cases(case: dict[str, Any]) -> None:
    resolved = resolve([StyleContent.model_validate(layer) for layer in case["layers"]])
    data = resolved.model_dump(mode="json")
    for path, expected in case["expect"].items():
        assert at(data, path) == expected, path


def test_the_server_holds_the_shared_default() -> None:
    shared = json.loads((SHARED / "default.json").read_text())
    packaged = json.loads((ROOT / "backend" / "app" / "styles" / "default.json").read_text())
    assert packaged == shared
    tokens = {t["name"]: t["value"] for t in
              json.loads((ROOT / "docs" / "brand" / "tokens.json").read_text())["color"]["tokens"]}
    light = {name: value["light"] if isinstance(value, dict) else value
             for name, value in tokens.items()}
    assert DEFAULT["colours"]["text"] == light["text"]
    assert DEFAULT["colours"]["muted"] == light["text-muted"]
    assert DEFAULT["colours"]["link"] == light["link"]
    assert DEFAULT["colours"]["accent"] == light["accent"]
    assert DEFAULT["colours"]["line"] == light["border"]
    for tone in ("info", "warning", "critical"):
        assert DEFAULT["tones"][tone] == {"fill": light[f"{tone}-bg"], "ink": light[f"{tone}-text"]}
    assert DEFAULT["tones"]["success"] == {"fill": light["ok-bg"], "ink": light["ok-text"]}


def element(**changes: Any) -> dict[str, Any]:
    return {"id": "e_test1", "kind": "text", "x": 18, "y": 8, "w": 60, "h": 6, **changes}


def content(*elements: dict[str, Any], page: str = "first") -> StyleContent:
    return StyleContent.model_validate({"pages": {page: {"elements": list(elements)}}})


@pytest.mark.parametrize("bad", [
    {"pages": {"first": {"elements": [element(x=180, w=40)]}}},
    {"pages": {"first": {"elements": [element(kind="image")]}}},
    {"pages": {"first": {"elements": [element(), element()]}}},
    {"pages": {"first": {"elements": [element(colour="red")]}}},
    {"pages": {"first": {"elements": [element(script="x")]}}},
    {"colours": {"text": "black"}},
    {"fonts": {"body": "Comic Sans"}},
    {"margins": {"top": 2}},
    {"tones": {"info": {"fill": "#FFFFFF"}}},
])
def test_what_a_style_may_not_hold(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        StyleContent.model_validate(bad)


def test_colours_are_kept_in_capitals() -> None:
    assert StyleContent.model_validate({"colours": {"text": "#0f1b2d"}}).colours.text == "#0F1B2D"


def test_text_elements_read_the_context_and_the_library() -> None:
    fine = content(element(text="{{ customer.name }} · {{ vars.phone }}"))
    assert problems(fine, timezone="Europe/Copenhagen", library={"vars.phone": "string"}) == []
    found = problems(content(element(text="{{ answers.cvss }} and {{ customer.nam }}"),
                             page="other"),
                     timezone="Europe/Copenhagen")
    assert len(found) == 2
    assert all(f.startswith("Element 1 on the other pages: ") for f in found)
    unclosed = problems(content(element(text="{{ customer.name")), timezone="Europe/Copenhagen")
    assert unclosed == ["Element 1 on the first page: a {{ has no }} to close it."]


# The API


@pytest.fixture
def person(make_user, session, full_session):
    def make(username, *roles):
        user = make_user(username, display_name=username.title())
        for role in roles:
            grant_role(session, user, Role(role), actor=None, ip=None)
        session.commit()
        return user, full_session(user)

    return make


@pytest.fixture
def designer(person):
    return person("dagny", "report_designer")


@pytest.fixture
def customer(client, admin):
    _, headers = admin
    return client.post("/api/customers", headers=headers,
                       json={"name": "Fjordvik Logistik A/S"}).json()


def picture(width: int, height: int, colour: str = "#2B5D8A") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format="PNG")
    return out.getvalue()


def post_file(client, headers, style_id, data, use="image"):
    return client.post(f"{STYLES}/{style_id}/assets?use={use}", content=data,
                       headers={**headers, "Content-Type": "application/octet-stream"})


def save(client, headers, style, **changes):
    body = {"name": style["name"], "based_on": style["based_on"], "content": style["content"],
            "version": style["version"], **changes}
    return client.put(f"{STYLES}/{style['id']}", headers=headers, json=body)


def actions(session, prefix: str) -> list[str]:
    return [e.action for e in session.scalars(
        select(AuditEntry).where(AuditEntry.action.like(f"{prefix}%")).order_by(AuditEntry.seq))]


def test_designers_make_and_change_company_styles(client, designer, session) -> None:
    _, headers = designer
    made = client.post(STYLES, headers=headers, json={"name": "Nordlys brand"})
    assert made.status_code == 201
    style = made.json()
    assert (style["version"], style["customer_id"], style["below"]) == (1, None, [])
    assert client.post(STYLES, headers=headers,
                       json={"name": "nordlys BRAND"}).status_code == 409
    changed = dict(style["content"], colours={**style["content"]["colours"], "heading": "#1d3a5f"})
    saved = save(client, headers, style, content=changed)
    assert saved.status_code == 200, saved.text
    assert (saved.json()["version"], saved.json()["content"]["colours"]["heading"]) == (
        2, "#1D3A5F")
    assert save(client, headers, style, content=changed).status_code == 409
    versions = client.get(f"{STYLES}/{style['id']}/versions", headers=headers).json()
    assert [v["number"] for v in versions] == [2, 1]
    first = client.get(f"{STYLES}/{style['id']}/versions/1", headers=headers).json()
    assert first["colours"]["heading"] is None
    assert actions(session, "style.") == ["style.created", "style.changed"]


def test_who_sees_and_changes_styles(client, person, designer) -> None:
    _, design = designer
    style = client.post(STYLES, headers=design, json={"name": "Nordlys brand"}).json()
    _, tech = person("tove", "technician")
    assert client.get(STYLES, headers=tech).status_code == 403
    assert client.get(f"{STYLES}/{style['id']}", headers=tech).status_code == 403
    _, manager = person("maja", "manager")
    assert [s["name"] for s in client.get(STYLES, headers=manager).json()] == ["Nordlys brand"]
    assert client.post(STYLES, headers=manager, json={"name": "Mine"}).status_code == 403
    assert save(client, manager, style).status_code == 403
    assert client.delete(f"{STYLES}/{style['id']}", headers=manager).status_code == 403


def test_a_style_saves_only_what_it_can_print(client, designer) -> None:
    _, headers = designer
    style = client.post(STYLES, headers=headers, json={"name": "Nordlys brand"}).json()
    bad = {"pages": {"first": {"elements": [element(text="{{ answers.cvss }}")]}}}
    refused = save(client, headers, style, content=bad)
    assert refused.status_code == 400
    assert "Element 1 on the first page" in refused.json()["detail"]
    missing = {"pages": {"first": {"elements": [element(kind="image", asset="a" * 64)]}}}
    assert "doesn't have" in save(client, headers, style, content=missing).json()["detail"]


def test_images_and_artwork(client, designer, session, monkeypatch) -> None:
    _, headers = designer
    style = client.post(STYLES, headers=headers, json={"name": "Nordlys brand"}).json()
    logo = post_file(client, headers, style["id"], picture(300, 100))
    assert logo.status_code == 200
    [sha] = logo.json()["pages"]
    again = post_file(client, headers, style["id"], picture(300, 100))
    assert again.json()["pages"] == [sha]
    used = {"pages": {"first": {"elements": [element(kind="image", asset=sha)]}}}
    assert save(client, headers, style, content=used).status_code == 200
    shown = client.get(f"{STYLES}/{style['id']}/assets/{sha}", headers=headers)
    assert shown.headers["content-type"] == "image/png"
    assert "immutable" in shown.headers["cache-control"]
    assert "private" not in shown.headers["cache-control"]
    assert post_file(client, headers, style["id"], b"GIF89a", use="image").status_code == 400

    page = post_file(client, headers, style["id"], picture(420, 594), use="artwork")
    assert (page.json()["status"], len(page.json()["pages"])) == ("ready", 1)
    assert post_file(client, headers, style["id"], picture(600, 400),
                     use="artwork").status_code == 400

    started = post_file(client, headers, style["id"], b"%PDF-1.4 letterhead", use="artwork")
    assert started.json()["status"] == "converting"
    upload_id = started.json()["upload"]
    [job] = session.scalars(select(jobs.Job).where(jobs.Job.kind == "style.artwork"))
    session.commit()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 595 842">'
           '<rect width="595" height="40" style="fill:#2B5D8A"/></svg>')
    second = svg.replace("40", "20")
    monkeypatch.setattr(backgrounds, "render_pdf", lambda pdf: [svg, second])
    assert artwork.convert(session, job) == {"status": "ready", "pages": 2}
    session.commit()
    done = client.get(f"{STYLES}/{style['id']}/uploads/{upload_id}", headers=headers).json()
    assert done["status"] == "ready" and len(done["pages"]) == 2
    assert session.get(StyleUpload, upload_id).original == b""
    session.rollback()  # every transaction here takes the write lock: end it
    letterhead = client.get(f"{STYLES}/{style['id']}/assets/{done['pages'][0]}", headers=headers)
    assert letterhead.headers["content-type"] == "image/svg+xml"
    assert b'fill="#2B5D8A"' in letterhead.content and b"style=" not in letterhead.content
    assert "sandbox" in letterhead.headers["content-security-policy"]
    latest = client.get(f"{STYLES}/{style['id']}", headers=headers).json()
    art = {"artwork": {"first": done["pages"][0], "other": done["pages"][1]}}
    assert save(client, headers, latest, content=art).status_code == 200
    assert "style.picture_added" in actions(session, "style.")


def test_customer_styles_are_sealed_and_go_with_the_customer(client, designer, customer,
                                                              session, engine) -> None:
    _, headers = designer
    company = client.post(STYLES, headers=headers, json={"name": "Nordlys brand"}).json()
    made = client.post(STYLES, headers=headers, json={
        "name": "Fjordvik look", "customer_id": customer["id"], "based_on": company["id"]})
    assert made.status_code == 201, made.text
    style = made.json()
    assert (style["customer_name"], style["based_on"]) == ("Fjordvik Logistik A/S", company["id"])
    look = {"colours": {"heading": "#0B4F6C"}}
    saved = save(client, headers, style, content=look).json()
    assert saved["content"]["colours"]["heading"] == "#0B4F6C"
    company_look = {"colours": {"accent": "#B5652B"}}
    save(client, headers, company, content=company_look)
    below = client.get(f"{STYLES}/{style['id']}", headers=headers).json()["below"]
    assert below[0]["colours"]["accent"] == "#B5652B"
    post_file(client, headers, style["id"], picture(120, 40))

    row = session.get(Style, style["id"])
    assert row.name is None and b"Fjordvik" not in row.sealed_name
    versions = session.scalars(select(StyleVersion).where(StyleVersion.style_id == row.id)).all()
    assert all(v.content is None and b"0B4F6C" not in v.sealed_content for v in versions)
    asset = session.scalars(select(StyleAsset).where(StyleAsset.style_id == row.id)).one()
    assert not asset.data.startswith(b"\x89PNG")
    company_row = session.get(Style, company["id"])
    assert company_row.name == "Nordlys brand"
    session.rollback()

    bad = client.post(STYLES, headers=headers, json={
        "name": "Wrong", "customer_id": customer["id"], "based_on": style["id"]})
    assert bad.status_code == 400
    assert client.post(STYLES, headers=headers, json={
        "name": "Nobody's", "customer_id": 9999}).status_code == 404

    for statement in ("UPDATE style_versions SET number = number + 10",
                      "DELETE FROM style_versions"):
        with engine.connect() as conn, pytest.raises(DBAPIError, match="kept as they were"):
            conn.execute(text(statement))

    session.delete(session.get(Customer, customer["id"]))
    session.commit()
    assert session.get(Style, style["id"]) is None
    assert session.scalars(select(StyleVersion).where(
        StyleVersion.style_id == style["id"])).all() == []
    assert session.scalars(select(StyleAsset).where(
        StyleAsset.style_id == style["id"])).all() == []
    assert session.get(Style, company["id"]) is not None


def test_the_company_default_and_customers_choices(client, designer, person, customer,
                                                   session) -> None:
    _, headers = designer
    brand = client.post(STYLES, headers=headers, json={"name": "Nordlys brand"}).json()
    plain = client.post(STYLES, headers=headers, json={"name": "Nordlys plain"}).json()
    own = client.post(STYLES, headers=headers, json={
        "name": "Fjordvik look", "customer_id": customer["id"]}).json()
    listed = client.put(f"{STYLES}/company-default", headers=headers,
                        json={"style_id": brand["id"]}).json()
    assert [s["name"] for s in listed if s["is_default"]] == ["Nordlys brand"]
    assert client.put(f"{STYLES}/company-default", headers=headers,
                      json={"style_id": own["id"]}).status_code == 400

    _, manager = person("maja", "manager")
    url = f"/api/customers/{customer['id']}/report-style"
    start = client.get(url, headers=manager).json()
    assert (start["default_style_id"], start["allowed"], start["company_default"]) == (
        None, [], brand["id"])
    assert {c["name"] for c in start["choices"]} == {"Nordlys brand", "Nordlys plain",
                                                     "Fjordvik look"}
    chosen = client.put(url, headers=manager, json={"default_style_id": own["id"],
                                                    "allowed": [plain["id"], own["id"]]})
    assert chosen.status_code == 200, chosen.text
    assert (chosen.json()["default_style_id"], chosen.json()["allowed"]) == (own["id"],
                                                                             [plain["id"]])
    other = client.post("/api/customers", headers=person("ivar", "administrator")[1],
                        json={"name": "Nordlys IT ApS"}).json()
    theirs = client.post(STYLES, headers=headers, json={
        "name": "Theirs", "customer_id": other["id"]}).json()
    assert client.put(url, headers=manager, json={"default_style_id": theirs["id"],
                                                  "allowed": []}).status_code == 400
    _, tech = person("tove", "technician")
    assert client.put(url, headers=tech, json={"default_style_id": None,
                                               "allowed": []}).status_code == 403

    client.delete(f"{STYLES}/{plain['id']}", headers=headers)
    after = client.get(url, headers=manager).json()
    assert after["allowed"] == []
    client.delete(f"{STYLES}/{brand['id']}", headers=headers)
    assert client.get(url, headers=manager).json()["company_default"] is None
    assert actions(session, "customer.report_style") == ["customer.report_style_changed"]
    assert session.get(CustomerStyles, customer["id"]) is not None


def test_branding_switches_off_made_with_skjald_and_sets_the_time_zone(client, admin) -> None:
    _, headers = admin
    shown = client.get("/api/branding").json()
    assert (shown["made_with_skjald"], shown["time_zone"]) == (True, "Europe/Copenhagen")
    base = {"site_name": "Skjald", "company_name": "Nordlys IT ApS"}
    saved = client.put("/api/admin/branding", headers=headers,
                       json={**base, "made_with_skjald": False, "time_zone": "Atlantic/Faroe"})
    assert saved.status_code == 200, saved.text
    assert (saved.json()["made_with_skjald"], saved.json()["time_zone"]) == (False,
                                                                             "Atlantic/Faroe")
    assert client.put("/api/admin/branding", headers=headers,
                      json={**base, "time_zone": "Mars/Olympus"}).status_code == 422
