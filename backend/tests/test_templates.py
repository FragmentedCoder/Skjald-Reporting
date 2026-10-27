"""The templates API: who may build templates, drafts, publishing and images."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit import AuditEntry
from app.roles import Role, grant_role

TEMPLATES = "/api/templates"
INCIDENT = json.loads((Path(__file__).resolve().parents[2] / "shared" / "templates"
                       / "incident.json").read_text())


def entries(session, action):
    found = list(session.scalars(select(AuditEntry).where(AuditEntry.action == action)))
    session.commit()
    return found


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
def template(client, designer):
    _, headers = designer
    return client.post(TEMPLATES, headers=headers, json={
        "name": "Security incident report", "description": "For NIS2 incidents."}).json()


def save(client, headers, template_id, content, revision):
    return client.put(f"{TEMPLATES}/{template_id}/draft", headers=headers,
                      json={"content": content, "revision": revision})


@pytest.mark.parametrize("role", ["technician", "reviewer", "manager", "auditor"])
def test_only_designers_and_administrators_build_templates(client, person, session, role,
                                                           template) -> None:
    _, headers = person(f"someone_{role}", role)
    for method, path in [("get", TEMPLATES), ("post", TEMPLATES),
                         ("get", f"{TEMPLATES}/{template['id']}/draft")]:
        response = client.request(method, path, headers=headers, json={"name": "x"})
        assert response.status_code == 403, (role, path)
    assert entries(session, "auth.access_denied")


def test_administrators_build_templates_too(client, admin, template) -> None:
    _, headers = admin
    assert [t["name"] for t in client.get(TEMPLATES, headers=headers).json()] == [
        "Security incident report"]


def test_a_new_template_has_a_starter_draft(client, designer, template, session) -> None:
    _, headers = designer
    assert template["latest_version"] is None
    assert template["draft"]["revision"] == 1
    assert template["draft"]["saved_by"] == "Dagny"
    draft = client.get(f"{TEMPLATES}/{template['id']}/draft", headers=headers).json()
    assert draft["content"]["form"][0]["title"] == "Step 1"
    assert draft["problems"] == []
    [created] = entries(session, "template.created")
    assert created.target_id == str(template["id"])


def test_saving_a_draft_reports_its_problems_and_counts_revisions(client, designer, template,
                                                                  frozen_clock) -> None:
    _, headers = designer
    content = json.loads(json.dumps(INCIDENT))
    content["form"][0]["questions"][2]["visible_when"] = "answers.nope"
    saved = save(client, headers, template["id"], content, 1)
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert saved.json()["problems"] == [{
        "element": "q_cvss", "field": "visible_when",
        "message": "answers.nope isn't a name this template has."}]
    # The same content again changes nothing.
    assert save(client, headers, template["id"], content, 2).json()["revision"] == 2


def test_a_save_over_someone_elses_newer_one_is_refused(client, designer, person, template
                                                        ) -> None:
    _, mine = designer
    _, theirs = person("astrid", "report_designer")
    content = json.loads(json.dumps(INCIDENT))
    assert save(client, theirs, template["id"], content, 1).status_code == 200
    content["settings"]["prefix"] = "SEC"
    refused = save(client, mine, template["id"], content, 1)
    assert refused.status_code == 409
    assert "Astrid saved this template" in refused.json()["detail"]


def test_saves_are_logged_once_every_few_minutes_per_person(client, designer, person, template,
                                                            session, frozen_clock) -> None:
    _, mine = designer
    _, theirs = person("astrid", "report_designer")
    content = json.loads(json.dumps(INCIDENT))
    revision = 1
    for prefix in ("AAA", "BBB", "CCC"):
        content["settings"]["prefix"] = prefix
        revision = save(client, mine, template["id"], content, revision).json()["revision"]
        frozen_clock.advance(minutes=2)
    assert len(entries(session, "template.draft_saved")) == 1
    content["settings"]["prefix"] = "DDD"
    revision = save(client, theirs, template["id"], content, revision).json()["revision"]
    assert len(entries(session, "template.draft_saved")) == 2
    frozen_clock.advance(minutes=11)
    content["settings"]["prefix"] = "EEE"
    save(client, theirs, template["id"], content, revision)
    assert len(entries(session, "template.draft_saved")) == 3


@pytest.mark.parametrize(("change", "message"), [
    (lambda c: c.update(extra=True), "The template isn't valid at extra: Extra inputs"),
    (lambda c: c["form"][0]["questions"][0].update(type="teleport"),
     "The template isn't valid at form.0.questions.0: 'teleport' isn't a field type."),
    (lambda c: c["layout"].append({"id": "b_big0", "kind": "text", "content": {
        "type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "x" * (2 * 1024 * 1024)}]}]}}),
     "The template is larger than 2 MB."),
])
def test_a_draft_must_have_the_right_shape(client, designer, template, change, message) -> None:
    _, headers = designer
    content = json.loads(json.dumps(INCIDENT))
    change(content)
    refused = save(client, headers, template["id"], content, 1)
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith(message)


def test_publishing_freezes_the_draft_as_the_next_version(client, designer, template, session
                                                          ) -> None:
    _, headers = designer
    tid = template["id"]
    broken = json.loads(json.dumps(INCIDENT))
    broken["layout"][1]["blocks"][0]["question"] = "q_gone"
    save(client, headers, tid, broken, 1)
    refused = client.post(f"{TEMPLATES}/{tid}/publish", headers=headers, json={"revision": 2})
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Fix the 1 problem first")
    save(client, headers, tid, INCIDENT, 2)
    stale = client.post(f"{TEMPLATES}/{tid}/publish", headers=headers, json={"revision": 2})
    assert stale.status_code == 409
    published = client.post(f"{TEMPLATES}/{tid}/publish", headers=headers,
                            json={"revision": 3, "note": "First version"})
    assert published.status_code == 200
    assert published.json()["number"] == 1
    detail = client.get(f"{TEMPLATES}/{tid}", headers=headers).json()
    assert detail["latest_version"] == 1
    assert detail["draft"] is None
    assert detail["versions"][0]["note"] == "First version"
    [logged] = entries(session, "template.published")
    assert json.loads(logged.details) == {
        "version": 1, "sha256": published.json()["content_sha256"]}
    version = client.get(f"{TEMPLATES}/{tid}/versions/1", headers=headers).json()
    assert version["content"]["settings"]["prefix"] == "INC"
    # No draft now: a new one starts from the newest version.
    assert client.get(f"{TEMPLATES}/{tid}/draft", headers=headers).status_code == 404
    started = client.post(f"{TEMPLATES}/{tid}/draft", headers=headers)
    assert started.status_code == 201
    assert started.json()["content"] == version["content"]
    assert client.post(f"{TEMPLATES}/{tid}/draft", headers=headers).status_code == 409


def test_the_database_refuses_to_change_or_remove_a_published_version(
        client, designer, template, engine) -> None:
    _, headers = designer
    tid = template["id"]
    save(client, headers, tid, INCIDENT, 1)
    client.post(f"{TEMPLATES}/{tid}/publish", headers=headers, json={"revision": 2})
    for statement in ("UPDATE template_versions SET content = '{}' WHERE number = 1",
                      "UPDATE template_versions SET note = 'edited' WHERE number = 1",
                      "DELETE FROM template_versions WHERE number = 1"):
        with engine.connect() as conn, pytest.raises(DBAPIError, match="published template"):
            conn.execute(text(statement))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT note FROM template_versions")).scalar() == ""
    # Nor can the template be deleted from under it.
    refused = client.delete(f"{TEMPLATES}/{tid}", headers=headers)
    assert refused.status_code == 409
    assert "retire it instead" in refused.json()["detail"]


def test_the_database_refuses_to_change_an_image(client, designer, template, engine) -> None:
    _, headers = designer
    client.post(f"{TEMPLATES}/{template['id']}/assets", content=png(),
                headers={**headers, "Content-Type": "application/octet-stream"})
    with engine.connect() as conn, pytest.raises(DBAPIError, match="never change"):
        conn.execute(text("UPDATE template_assets SET data = x'00'"))


def test_a_draft_is_discarded_and_a_never_published_template_deleted(client, designer, template,
                                                                     session) -> None:
    _, headers = designer
    tid = template["id"]
    assert client.delete(f"{TEMPLATES}/{tid}/draft", headers=headers).status_code == 409
    assert client.delete(f"{TEMPLATES}/{tid}", headers=headers).status_code == 204
    assert client.get(f"{TEMPLATES}/{tid}", headers=headers).status_code == 404
    assert entries(session, "template.deleted")


def test_retiring_and_restoring(client, designer, template) -> None:
    _, headers = designer
    tid = template["id"]
    assert client.post(f"{TEMPLATES}/{tid}/retire", headers=headers).json()["retired"] is True
    assert client.post(f"{TEMPLATES}/{tid}/restore", headers=headers).json()["retired"] is False


def test_changes_since_the_newest_version(client, designer, template) -> None:
    _, headers = designer
    tid = template["id"]
    first = client.get(f"{TEMPLATES}/{tid}/changes", headers=headers).json()
    assert first["questions_added"] == []  # the starter has none
    save(client, headers, tid, INCIDENT, 1)
    client.post(f"{TEMPLATES}/{tid}/publish", headers=headers, json={"revision": 2})
    client.post(f"{TEMPLATES}/{tid}/draft", headers=headers)
    content = json.loads(json.dumps(INCIDENT))
    content["form"][0]["questions"][0]["label"] = "Summary"
    save(client, headers, tid, content, 1)
    found = client.get(f"{TEMPLATES}/{tid}/changes", headers=headers).json()
    assert found["questions_changed"] == [{"id": "q_summary", "label": "Summary",
                                           "parts": ["label"]}]


def png(width=40, height=20) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "#C8862A").save(out, format="PNG")
    return out.getvalue()


def test_images_are_cleaned_kept_by_hash_and_served_safely(client, designer, template, session
                                                           ) -> None:
    _, headers = designer
    tid = template["id"]
    upload = {**headers, "Content-Type": "application/octet-stream"}
    added = client.post(f"{TEMPLATES}/{tid}/assets?name=net<script>.png", headers=upload,
                        content=png())
    assert added.status_code == 201
    asset = added.json()
    assert (asset["width"], asset["height"], asset["content_type"]) == (40, 20, "image/png")
    assert asset["name"] == "net_script_.png"
    again = client.post(f"{TEMPLATES}/{tid}/assets", headers=upload, content=png())
    assert again.json()["sha256"] == asset["sha256"]
    assert len(entries(session, "template.image_added")) == 1
    served = client.get(asset["url"], headers=headers)
    assert served.headers["content-type"] == "image/png"
    assert "sandbox" in served.headers["content-security-policy"]
    assert served.headers["x-content-type-options"] == "nosniff"
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 5" onload="alert(1)">'
           b'<script>alert(1)</script><rect width="10" height="5"/></svg>')
    cleaned = client.post(f"{TEMPLATES}/{tid}/assets?name=a.svg", headers=upload, content=svg)
    assert cleaned.json()["content_type"] == "image/svg+xml"
    body = client.get(cleaned.json()["url"], headers=headers).content
    assert b"script" not in body and b"onload" not in body
    refused = client.post(f"{TEMPLATES}/{tid}/assets", headers=upload, content=b"MZ\x90\x00")
    assert refused.status_code == 400
    # The image's block is happy once it's there.
    content = json.loads(json.dumps(INCIDENT))
    content["layout"][2]["blocks"].append({"id": "b_netimg", "kind": "image", "source": "template",
                                           "asset": asset["sha256"]})
    assert save(client, headers, tid, content, 1).json()["problems"] == []


def test_a_copy_starts_from_the_draft_and_keeps_the_images(client, designer, template) -> None:
    _, headers = designer
    tid = template["id"]
    save(client, headers, tid, INCIDENT, 1)
    client.post(f"{TEMPLATES}/{tid}/assets", content=png(),
                headers={**headers, "Content-Type": "application/octet-stream"})
    copied = client.post(f"{TEMPLATES}/{tid}/copy", headers=headers,
                         json={"name": "Security incident report (DA)"})
    assert copied.status_code == 201
    copy = copied.json()
    assert copy["uuid"] != template["uuid"]
    assert len(copy["assets"]) == 1
    draft = client.get(f"{TEMPLATES}/{copy['id']}/draft", headers=headers).json()
    assert draft["content"]["settings"]["prefix"] == "INC"
