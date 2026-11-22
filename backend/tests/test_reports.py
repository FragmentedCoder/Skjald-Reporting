"""Reports: who reads and writes them, numbers, pinned templates, sealed answers,
checkouts and secrets."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select, text

from app import jobs, mail
from app.audit import AuditEntry
from app.customers import Customer, Keyring
from app.mail import MailServer
from app.reports import routes as report_routes
from app.reports.models import Report, ReportCheckout
from app.roles import Role, grant_role
from app.sealed_settings import save_secrets
from tests.conftest import PASSWORD
from tests.test_mail import SERVER

CUSTOMERS = "/api/customers"
TEMPLATES = "/api/templates"

OPTIONS = [{"value": "low", "label": "Low"}, {"value": "high", "label": "High"}]
CONTENT = {
    "schema": 1,
    "settings": {"prefix": "INC"},
    "form": [
        {"id": "s_details", "title": "Details", "questions": [
            {"id": "q_title", "key": "title", "type": "text", "label": "What happened",
             "required": True},
            {"id": "q_when", "key": "found", "type": "datetime", "label": "When it was found"},
            {"id": "q_severity", "key": "severity", "type": "dropdown", "label": "Severity",
             "default": '"low"', "settings": {"options": OPTIONS}},
            {"id": "q_areas", "key": "areas", "type": "multi_select", "label": "Areas",
             "settings": {"options": OPTIONS}},
            {"id": "q_note", "key": "note", "type": "rich_text", "label": "Notes"},
            {"id": "q_count", "key": "count", "type": "number", "label": "Hosts hit",
             "settings": {"whole": True}},
            {"id": "q_confirmed", "key": "confirmed", "type": "yes_no", "label": "Confirmed"},
            {"id": "q_cvss", "key": "cvss", "type": "cvss", "label": "CVSS"},
        ]},
        {"id": "s_access", "title": "Access", "questions": [
            {"id": "q_password", "key": "password", "type": "secret", "label": "Password found"},
            {"id": "q_lead", "key": "lead", "type": "person", "label": "Who led the work",
             "settings": {"who": "team"}},
            {"id": "q_witness", "key": "witness", "type": "signature", "label": "Witness"},
            {"id": "q_hosts", "key": "hosts", "type": "repeating", "label": "Hosts", "settings": {
                "columns": [
                    {"key": "name", "label": "Name", "type": "hostname"},
                    {"key": "port", "label": "Port", "type": "number", "settings": {"whole": True}},
                    {"key": "open", "label": "Open", "type": "yes_no"},
                    {"key": "level", "label": "Level", "type": "dropdown",
                     "settings": {"options": OPTIONS}},
                    {"key": "seen", "label": "Seen", "type": "datetime"},
                ]}},
            {"id": "q_total", "key": "total", "type": "calculated", "label": "Hosts listed",
             "value": "size(answers.hosts)", "settings": {"result": "whole"}},
            {"id": "q_proof", "key": "proof", "type": "photo", "label": "Photo"},
        ]},
    ],
    "layout": [{"id": "b_summary", "kind": "section", "title": "Summary", "new_page": False,
                "blocks": [{"id": "b_title", "kind": "answer", "question": "q_title"}]}],
}


@pytest.fixture(autouse=True)
def no_views_remembered():
    """Which views were logged is remembered in the process: each test starts afresh."""
    report_routes._VIEWS_LOGGED.clear()


def entries(session, action):
    found = list(session.scalars(select(AuditEntry).where(AuditEntry.action == action)))
    session.commit()
    return found


def details(entry):
    return json.loads(entry.details)


@pytest.fixture
def person(make_user, session, full_session):
    """Someone with the given roles, signed in. Returns (user, headers)."""

    def make(username, *roles, **fields):
        user = make_user(username, display_name=fields.pop("display_name", username.title()))
        for field, value in fields.items():
            setattr(user, field, value)
        for role in roles:
            grant_role(session, user, Role(role), actor=None, ip=None)
        session.commit()
        return user, full_session(user)

    return make


def publish(client, headers, name="Security incident report", content=CONTENT):
    """A template with one published version. Returns its detail."""
    template = client.post(TEMPLATES, headers=headers, json={"name": name}).json()
    saved = client.put(f"{TEMPLATES}/{template['id']}/draft", headers=headers,
                       json={"content": content, "revision": 1})
    assert saved.status_code == 200 and saved.json()["problems"] == [], saved.text
    published = client.post(f"{TEMPLATES}/{template['id']}/publish", headers=headers,
                            json={"revision": saved.json()["revision"], "note": "First"})
    assert published.status_code == 200, published.text
    return client.get(f"{TEMPLATES}/{template['id']}", headers=headers).json()


@pytest.fixture
def world(client, admin, person, full_session):
    """A customer with a project and a published template, and the people around it:
    Astrid (its responsible technician), Bo (a technician on its team), Rasmus (its
    reviewer), Tor (a technician on the customer but not the project), Mona (a
    Manager) and Ulla (an Auditor)."""
    _, boss = admin
    customer = client.post(CUSTOMERS, headers=boss, json={
        "name": "Fjordvik Logistik A/S", "cvr": "3141 5926", "address": "Havnegade 12"}).json()
    cid = customer["id"]
    site = client.post(f"{CUSTOMERS}/{cid}/sites", headers=boss,
                       json={"name": "Terminal 3", "address": "Kajvej 4"}).json()["sites"][0]
    contact = client.post(f"{CUSTOMERS}/{cid}/contacts", headers=boss, json={
        "name": "Mette Lund", "role": "IT manager", "email": "mette@fjordvik.example",
        "phone": "+45 76 10 20 30"}).json()["contacts"][0]
    astrid = person("astrid", "technician", display_name="Astrid Fjeld",
                    email="astrid@nordlys.example", job_title="Security consultant")
    bo = person("bo", "technician", display_name="Bo Berg")
    rasmus = person("rasmus", "reviewer", display_name="Rasmus Holm")
    tor = person("tor", "technician", display_name="Tor Dahl")
    mona = person("mona", "manager", display_name="Mona Lind")
    ulla = person("ulla", "auditor", display_name="Ulla Krog")
    assigned = client.put(f"{CUSTOMERS}/{cid}/assignments", headers=boss, json={
        "technicians": [astrid[0].id, bo[0].id, tor[0].id], "reviewers": [rasmus[0].id]})
    assert assigned.status_code == 200, assigned.text
    project = client.post(f"{CUSTOMERS}/{cid}/projects", headers=boss, json={
        "name": "Portal brute force", "start_date": "2026-10-20",
        "responsible_id": astrid[0].id, "reviewer_id": rasmus[0].id,
        "contact_id": contact["id"], "site_ids": [site["id"]]}).json()
    team = client.put(f"/api/projects/{project['id']}/team", headers=boss,
                      json={"technicians": [bo[0].id]})
    assert team.status_code == 200, team.text
    template = publish(client, boss)
    return SimpleNamespace(customer=customer, site=site, contact=contact, project=project,
                           template=template, boss=boss, astrid=astrid, bo=bo, rasmus=rasmus,
                           tor=tor, mona=mona, ulla=ulla, admin=admin[0],
                           # Signs someone in again, after the clock moved past their session.
                           sign_in=full_session,
                           reports=f"/api/projects/{project['id']}/reports")


def start(client, world, headers=None, **fields):
    response = client.post(world.reports, headers=headers or world.astrid[1],
                           json={"template_id": world.template["id"], **fields})
    assert response.status_code == 201, response.text
    return response.json()


def check_out(client, headers, report, step=None):
    return client.post(f"/api/reports/{report['id']}/checkouts", headers=headers,
                       json={"step": step})


def save(client, headers, report, **answers):
    return client.patch(f"/api/reports/{report['id']}/answers", headers=headers,
                        json={"answers": answers})


def opened(client, headers, report):
    response = client.get(f"/api/reports/{report['id']}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# Starting reports


def test_a_technician_on_the_project_starts_a_numbered_report(frozen_clock, client, world,
                                                              session) -> None:
    first = start(client, world)
    assert first["number"] == "INC-2026-0001"
    assert first["title"] == "Security incident report"
    assert first["status"] == "draft" and first["revision"] == 1
    assert first["template"]["version"] == 1
    assert first["template"]["content"]["form"][0]["id"] == "s_details"
    assert "sample" not in first["template"]["content"]
    assert first["author"]["name"] == "Astrid Fjeld"
    assert first["answers"] == {} and first["saves"] == 0
    assert first["may_edit"] and first["may_discard"] and not first["may_break"]
    second = start(client, world, headers=world.bo[1], title="  The second one  ")
    assert second["number"] == "INC-2026-0002"
    assert second["title"] == "The second one"
    [created, _] = entries(session, "report.created")
    assert details(created) == {"number": "INC-2026-0001", "project": world.project["number"],
                                "template": world.template["id"], "version": 1}
    listed = client.get(world.reports, headers=world.astrid[1]).json()
    assert [r["number"] for r in listed["reports"]] == ["INC-2026-0002", "INC-2026-0001"]
    assert listed["may_create"]


def test_a_number_is_never_used_twice(client, world) -> None:
    first = start(client, world)
    gone = client.request("DELETE", f"/api/reports/{first['id']}", headers=world.astrid[1],
                          json={"confirm_number": first["number"]})
    assert gone.status_code == 204
    assert start(client, world)["number"].endswith("-0002")
    # Each prefix counts on its own.
    other = publish(client, world.boss, "Destruction certificate",
                    {**CONTENT, "settings": {"prefix": "DST"}})
    certificate = client.post(world.reports, headers=world.astrid[1],
                              json={"template_id": other["id"]}).json()
    assert certificate["number"].startswith("DST-") and certificate["number"].endswith("-0001")


def test_the_context_is_the_reports_own(frozen_clock, client, world) -> None:
    context = start(client, world)["context"]
    assert context["customer"]["name"] == "Fjordvik Logistik A/S"
    assert context["customer"]["cvr"] == "31415926"
    assert context["project"]["number"] == world.project["number"]
    # A day is midnight in the company's time zone (Copenhagen, two hours ahead in October).
    assert context["project"]["start_date"] == "2026-10-19T22:00:00.000Z"
    assert context["project"]["end_date"] is None
    assert context["site"] == {"name": "Terminal 3", "address": "Kajvej 4"}  # the only one
    assert context["contact"]["name"] == "Mette Lund"
    assert context["report"]["number"] == "INC-2026-0001"
    assert context["report"]["revision"] == 1
    assert context["report"]["started"] == "2026-10-24T12:00:00.000Z"
    assert context["author"]["display_name"] == "Astrid Fjeld"
    assert context["author"]["job_title"] == "Security consultant"
    assert context["reviewer"]["display_name"] == "Rasmus Holm"


def test_only_published_templates_in_use_start_reports(client, world) -> None:
    astrid = world.astrid[1]
    draft = client.post(TEMPLATES, headers=world.boss, json={"name": "Not ready"}).json()
    choices = client.get(f"/api/projects/{world.project['id']}/report-templates", headers=astrid)
    assert [(c["name"], c["version"], c["prefix"]) for c in choices.json()] == [
        ("Security incident report", 1, "INC")]
    refused = client.post(world.reports, headers=astrid, json={"template_id": draft["id"]})
    assert refused.status_code == 400
    client.post(f"{TEMPLATES}/{world.template['id']}/retire", headers=world.boss)
    retired = client.post(world.reports, headers=astrid,
                          json={"template_id": world.template["id"]})
    assert retired.status_code == 409
    assert client.get(f"/api/projects/{world.project['id']}/report-templates",
                      headers=astrid).json() == []
    elsewhere = client.post(world.reports, headers=astrid,
                            json={"template_id": world.template["id"], "site_id": 9999})
    assert elsewhere.status_code in (400, 409)


def test_a_report_stays_pinned_to_the_version_it_was_written_with(client, world) -> None:
    report = start(client, world)
    tid = world.template["id"]
    draft = client.post(f"{TEMPLATES}/{tid}/draft", headers=world.boss).json()
    changed = json.loads(json.dumps(CONTENT))
    changed["form"][0]["title"] = "The incident"
    saved = client.put(f"{TEMPLATES}/{tid}/draft", headers=world.boss,
                       json={"content": changed, "revision": draft["revision"]}).json()
    client.post(f"{TEMPLATES}/{tid}/publish", headers=world.boss,
                json={"revision": saved["revision"], "note": "Renamed a step"})
    again = opened(client, world.astrid[1], report)
    assert again["template"]["version"] == 1
    assert again["template"]["content"]["form"][0]["title"] == "Details"
    newer = start(client, world)
    assert newer["template"]["version"] == 2
    assert newer["template"]["content"]["form"][0]["title"] == "The incident"
    # A template reports were written with is kept, retired or not.
    client.post(f"{TEMPLATES}/{tid}/retire", headers=world.boss)
    client.post("/api/auth/confirm-password", headers=world.boss, json={"password": PASSWORD})
    kept = client.request("DELETE", f"{TEMPLATES}/{tid}", headers=world.boss,
                          json={"confirm_name": "Security incident report"})
    assert kept.status_code == 409
    assert kept.json()["detail"].startswith("2 reports were written with this template")


# Who reads and who writes


def test_who_reads_and_who_writes_follows_the_project(client, world, person, session) -> None:
    report = start(client, world)
    url = f"/api/reports/{report['id']}"
    # Everyone who may open the project reads its reports.
    for who in (world.astrid, world.bo, world.rasmus, world.tor, world.mona):
        assert client.get(url, headers=who[1]).status_code == 200
        assert client.get(world.reports, headers=who[1]).status_code == 200
    # Only its technicians, and Administrators, write them.
    for who in (world.rasmus, world.tor, world.mona):
        assert not client.get(url, headers=who[1]).json()["may_edit"]
        assert not client.get(world.reports, headers=who[1]).json()["may_create"]
        assert client.post(world.reports, headers=who[1],
                           json={"template_id": world.template["id"]}).status_code == 403
        assert check_out(client, who[1], report).status_code == 403
        assert save(client, who[1], report, q_title="x").status_code == 403
    assert check_out(client, world.bo[1], report).status_code == 200
    assert client.get(url, headers=world.boss).json()["may_edit"]
    # Someone who can't see the customer gets what a report that doesn't exist gets.
    _, designer = person("dagny", "report_designer")
    _, stranger = person("stig", "technician")
    for headers in (world.ulla[1], designer, stranger):
        hidden = client.get(url, headers=headers)
        assert hidden.status_code == 404
        assert hidden.json()["detail"] == "That report doesn't exist."
        assert client.get(world.reports, headers=headers).status_code == 404
    assert client.get("/api/reports/9999", headers=world.boss).status_code == 404
    assert entries(session, "customer.access_denied")


def test_a_tlp_red_project_keeps_its_reports_to_its_team(client, world) -> None:
    report = start(client, world)
    client.patch(f"/api/projects/{world.project['id']}", headers=world.boss,
                 json={"classification": "TLP:RED"})
    assert client.get(f"/api/reports/{report['id']}", headers=world.tor[1]).status_code == 404
    assert client.get(f"/api/reports/{report['id']}", headers=world.bo[1]).status_code == 200
    assert client.get(f"/api/reports/{report['id']}", headers=world.mona[1]).status_code == 200


def test_an_archived_projects_reports_are_read_only(client, world) -> None:
    report = start(client, world)
    check_out(client, world.astrid[1], report)
    client.post(f"/api/projects/{world.project['id']}/archive", headers=world.boss)
    astrid = world.astrid[1]
    assert opened(client, astrid, report)["may_edit"] is False
    for response in (save(client, astrid, report, q_title="Late"),
                     check_out(client, astrid, report, "s_access"),
                     client.post(world.reports, headers=astrid,
                                 json={"template_id": world.template["id"]})):
        assert response.status_code == 409
        assert response.json()["detail"] == "Archived projects are read-only."
    # A checkout left behind can still be released.
    [held] = opened(client, astrid, report)["checkouts"]
    assert client.delete(f"/api/reports/{report['id']}/checkouts/{held['id']}",
                         headers=astrid).status_code == 200


# What's kept


def test_the_title_and_the_answers_are_sealed_with_the_customers_key(client, world, session,
                                                                     engine) -> None:
    report = start(client, world, title="Ransomware at Terminal 3")
    check_out(client, world.astrid[1], report)
    saved = save(client, world.astrid[1], report, q_title="The portal was hammered")
    assert saved.status_code == 200
    with engine.connect() as conn:
        row = conn.execute(text("SELECT sealed_title, sealed_answers FROM reports")).one()
    for sealed in row:
        assert b"Ransomware" not in sealed and b"hammered" not in sealed
    kept = session.get(Report, report["id"])
    customer = session.get(Customer, world.customer["id"])
    sealer = Keyring().sealer(customer)
    assert sealer.open("report-title", kept.id, kept.sealed_title) == {
        "title": "Ransomware at Terminal 3"}
    assert sealer.open("report-answers", kept.id, kept.sealed_answers) == {
        "answers": {"q_title": "The portal was hammered"}}
    # Bound to the report: it opens nowhere else.
    with pytest.raises(InvalidTag):
        sealer.open("report-answers", kept.id + 1, kept.sealed_answers)
    with pytest.raises(InvalidTag):
        sealer.open("report-title", kept.id, kept.sealed_answers)
    session.commit()


def test_deleting_the_customer_takes_its_reports(client, world, session) -> None:
    report = start(client, world)
    check_out(client, world.astrid[1], report)
    client.post("/api/auth/confirm-password", headers=world.boss, json={"password": PASSWORD})
    gone = client.request("DELETE", f"{CUSTOMERS}/{world.customer['id']}", headers=world.boss,
                          json={"confirm_name": "Fjordvik Logistik A/S"})
    assert gone.status_code in (200, 204), gone.text
    assert session.scalars(select(Report)).all() == []
    assert session.scalars(select(ReportCheckout)).all() == []
    session.commit()


def test_answers_are_kept_as_the_server_reads_them(frozen_clock, client, world, session) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    check_out(client, astrid, report)
    saved = save(client, astrid, report, **{
        "q_title": "Portal brute force",
        "q_when": "2026-10-21T05:14:00+02:00",
        "q_severity": "high",
        "q_areas": ["low", "high"],
        "q_note": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Seen at night."}]}]},
        "q_count": 12,
        "q_confirmed": False,
        # The browser's score isn't taken: the server works it out.
        "q_cvss": {"vector": " CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H ", "score": 1,
                   "severity": "Low"},
        "q_lead": {"id": str(world.bo[0].id), "display_name": "Somebody Else"},
        "q_witness": {"name": "  Mette Lund ", "confirmed": True, "at": "1999-01-01T00:00:00Z"},
        "q_hosts": [{"name": "srv-01", "port": 443, "open": True, "level": "high",
                     "seen": "2026-10-21T03:14:00Z"}, {"name": "srv-02"}, None],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["saves"] == 1 and saved.json()["forgotten"] == []
    answers = opened(client, astrid, report)["answers"]
    assert answers["q_when"] == "2026-10-21T03:14:00.000Z"
    assert answers["q_confirmed"] is False
    assert answers["q_cvss"] == {
        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "score": 9.8,
        "severity": "Critical"}
    assert answers["q_lead"]["display_name"] == "Bo Berg"
    assert answers["q_lead"]["id"] == str(world.bo[0].id)
    assert answers["q_witness"] == {"name": "Mette Lund", "confirmed": True,
                                    "at": "2026-10-24T12:00:00.000Z"}
    assert answers["q_hosts"] == [
        {"name": "srv-01", "port": 443, "open": True, "level": "high",
         "seen": "2026-10-21T03:14:00.000Z"},
        {"name": "srv-02", "port": None, "open": None, "level": None, "seen": None},
        {"name": None, "port": None, "open": None, "level": None, "seen": None}]
    [signed] = entries(session, "report.signature_recorded")
    assert details(signed) == {"number": report["number"], "questions": ["q_witness"]}
    # A signature keeps its moment while its name stays the same.
    frozen_clock.advance(hours=1)
    astrid = world.sign_in(world.astrid[0])
    save(client, astrid, report, q_witness={"name": "Mette Lund", "confirmed": True})
    assert opened(client, astrid, report)["answers"]["q_witness"]["at"] == (
        "2026-10-24T12:00:00.000Z")
    save(client, astrid, report, q_witness={"name": "Mette M. Lund", "confirmed": True})
    assert opened(client, astrid, report)["answers"]["q_witness"]["at"] == (
        "2026-10-24T13:00:00.000Z")
    # The same person stays as they were when picked.
    client.patch(f"/api/admin/users/{world.bo[0].id}", headers=world.boss,
                 json={"display_name": "Bo Bergstrøm"})
    save(client, astrid, report, q_lead={"id": str(world.bo[0].id)})
    assert opened(client, astrid, report)["answers"]["q_lead"]["display_name"] == "Bo Berg"


@pytest.mark.parametrize(("question", "value", "says"), [
    ("q_title", 12, "takes text"),
    pytest.param("q_title", "x" * 10_001, "at most 10,000 characters", id="too long"),
    ("q_when", "yesterday", "takes a date"),
    ("q_when", "2026-10-21T05:14:00", "with its time zone"),
    ("q_severity", "critical", "choose one of its options"),
    ("q_areas", ["low", "low"], "each once"),
    ("q_areas", ["low", "odd"], "choose one of its options"),
    ("q_note", "plain words", "Rich text must be a document"),
    ("q_note", {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "variable", "attrs": {"expr": "customer.name"}}]}]}, "they're for templates"),
    ("q_count", "12", "takes a number"),
    ("q_count", True, "takes a number"),
    ("q_count", 1e300, "no larger than"),
    ("q_confirmed", "yes", "is yes or no"),
    ("q_cvss", "CVSS:3.1/AV:N", "takes text"),
    ("q_password", {"masked": True, "printed": "••••••"}, "type a new value"),
    ("q_lead", {"id": "9999"}, "can't be chosen here"),
    ("q_lead", "Bo", "choose a person"),
    pytest.param("q_lead", {"id": "9" * 5000}, "can't be chosen here", id="a huge id"),
    pytest.param("q_note", json.loads("[" * 60 + "]" * 60), "nested deeper", id="deep"),
    pytest.param("q_title", "cut\x00here", "null character", id="a null character"),
    ("q_hosts", {"name": "srv-01"}, "takes rows"),
    ("q_hosts", [{"owner": "x"}], "a row holds its columns' cells"),
    ("q_hosts", [{"port": "443"}], "Hosts, row 1, Port takes a number"),
    ("q_hosts", [{"level": "odd"}], "choose one of its options"),
    pytest.param("q_hosts", [{}] * 501, "at most 500 rows", id="too many rows"),
    ("q_total", 3, "Skjald works it out"),
    ("q_proof", ["photo.jpg"], "can't be added to a report yet"),
    ("q_gone", "x", "isn't in this report's template"),
])
def test_an_answer_of_the_wrong_shape_is_refused(client, world, question, value, says) -> None:
    report = start(client, world)
    check_out(client, world.astrid[1], report)
    refused = save(client, world.astrid[1], report, **{question: value})
    assert refused.status_code == 400, refused.text
    assert says in refused.json()["detail"]
    assert opened(client, world.astrid[1], report)["answers"] == {}


@pytest.mark.parametrize("sent", [
    '{"answers": {"q_title": "half \\ud83d"}}',
    '{"answers": {"q_hosts": [{"name": "\\udc00"}]}}',
])
def test_half_a_character_is_refused_before_it_is_kept(client, world, sent) -> None:
    # Half of a character pair could be kept, but never sent back: the report would
    # stop opening.
    report = start(client, world)
    check_out(client, world.astrid[1], report)
    refused = client.patch(f"/api/reports/{report['id']}/answers", content=sent,
                           headers={**world.astrid[1], "Content-Type": "application/json"})
    assert refused.status_code == 400, refused.text
    assert "half of a character" in refused.json()["detail"]
    assert opened(client, world.astrid[1], report)["answers"] == {}


def test_a_person_must_be_one_the_question_offers(client, world) -> None:
    report = start(client, world)
    check_out(client, world.astrid[1], report)
    people = {p["display_name"]: p for p in opened(client, world.astrid[1], report)["people"]}
    # The question asks for the project's team: nobody else is offered, or taken.
    assert sorted(people) == ["Astrid Fjeld", "Bo Berg", "Rasmus Holm"]
    assert people["Astrid Fjeld"]["technician"] and people["Astrid Fjeld"]["on_team"]
    assert people["Rasmus Holm"]["reviewer"] and not people["Rasmus Holm"]["technician"]
    assert people["Astrid Fjeld"]["email"] == "astrid@nordlys.example"
    off_team = save(client, world.astrid[1], report, q_lead={"id": str(world.tor[0].id)})
    assert off_team.status_code == 400
    on_team = save(client, world.astrid[1], report, q_lead={"id": str(world.rasmus[0].id)})
    assert on_team.status_code == 200


def test_an_empty_answer_is_forgotten_or_kept_as_cleared(client, world) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    check_out(client, astrid, report)
    save(client, astrid, report, q_title="Something", q_severity="high", q_areas=["low"],
         q_cvss={"vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
         q_witness={"name": "Mette Lund", "confirmed": True})
    cleared = save(client, astrid, report, q_title="", q_severity=None, q_areas=[],
                   q_cvss={"vector": " "}, q_witness={"name": "Mette Lund", "confirmed": False})
    assert cleared.status_code == 200, cleared.text
    # Severity starts as "low" by its rule: cleared on purpose, it's kept as empty.
    assert cleared.json()["answers"] == {"q_severity": None}
    assert sorted(cleared.json()["forgotten"]) == ["q_areas", "q_cvss", "q_title", "q_witness"]
    assert opened(client, astrid, report)["answers"] == {"q_severity": None}
    # Saving what's there already changes nothing.
    same = save(client, astrid, report, q_severity=None, q_title="")
    assert same.json()["saves"] == cleared.json()["saves"] and same.json()["answers"] == {}
    # Spaces alone, and a long text with every word deleted, are no answers either:
    # kept, they would pass for one where the question is required.
    emptied = {"type": "doc", "content": [{"type": "paragraph"}, {"type": "paragraph",
               "content": [{"type": "text", "text": "  "}]}]}
    save(client, astrid, report, q_title="Something", q_note={"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Words."}]}]})
    blanked = save(client, astrid, report, q_title=" \t ", q_note=emptied)
    assert sorted(blanked.json()["forgotten"]) == ["q_note", "q_title"]
    assert opened(client, astrid, report)["answers"] == {"q_severity": None}
    assert "q_title" in [m["question"] for m in opened(client, astrid, report)[
        "state"]["missing"]]


# Checkouts


def test_answers_are_saved_only_under_a_checkout(client, world, session) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    without = save(client, astrid, report, q_title="Too early")
    assert without.status_code == 409
    assert without.json()["detail"] == "Check the step out before changing its answers."
    taken = check_out(client, astrid, report, "s_details")
    assert taken.status_code == 200
    [held] = taken.json()["checkouts"]
    assert held["step"] == "s_details" and held["mine"] and not held["stale"]
    assert held["holder"]["name"] == "Astrid Fjeld"
    assert save(client, astrid, report, q_title="In my step").status_code == 200
    # Another step is another checkout; one answer outside it refuses the whole save.
    mixed = save(client, astrid, report, q_title="Changed", q_password="hunter2hunter2")
    assert mixed.status_code == 409
    assert opened(client, astrid, report)["answers"] == {"q_title": "In my step"}
    assert check_out(client, astrid, report, "s_gone").status_code == 400
    # The whole report takes the place of the steps held.
    whole = check_out(client, astrid, report).json()["checkouts"]
    assert [c["step"] for c in whole] == [None]
    assert save(client, astrid, report, q_title="Changed", q_password="hunter2hunter2"
                ).status_code == 200
    # Asking again for what's held already changes nothing.
    assert [c["id"] for c in check_out(client, astrid, report, "s_access").json()["checkouts"]
            ] == [whole[0]["id"]]
    assert len(entries(session, "report.checked_out")) == 2


def test_two_people_work_in_different_steps_without_overwriting_each_other(client, world
                                                                           ) -> None:
    astrid, bo = world.astrid[1], world.bo[1]
    report = start(client, world)
    assert check_out(client, astrid, report, "s_details").status_code == 200
    taken = check_out(client, bo, report, "s_details")
    assert taken.status_code == 409
    assert taken.json()["detail"] == "Astrid Fjeld has the step “Details” checked out."
    assert check_out(client, bo, report).status_code == 409
    assert check_out(client, bo, report, "s_access").status_code == 200
    assert check_out(client, astrid, report).status_code == 409
    assert save(client, astrid, report, q_title="Astrid's").status_code == 200
    assert save(client, bo, report, q_password="bo's secret value").status_code == 200
    assert save(client, bo, report, q_title="Bo's").status_code == 409
    answers = opened(client, bo, report)["answers"]
    assert answers["q_title"] == "Astrid's" and answers["q_password"]["masked"]
    activity = client.get(f"/api/reports/{report['id']}/activity", headers=bo).json()
    assert activity["saves"] == 2
    assert [(c["step"], c["holder"]["name"], c["mine"]) for c in activity["checkouts"]] == [
        ("s_details", "Astrid Fjeld", False), ("s_access", "Bo Berg", True)]
    # Only its holder releases a checkout.
    theirs, mine = activity["checkouts"]
    url = f"/api/reports/{report['id']}/checkouts"
    assert client.delete(f"{url}/{theirs['id']}", headers=bo).status_code == 403
    assert client.delete(f"{url}/{mine['id']}", headers=bo).status_code == 200
    assert client.delete(f"{url}/{mine['id']}", headers=bo).status_code == 404
    assert check_out(client, astrid, report).status_code == 200


def test_an_administrator_ends_a_checkout_and_its_holder_is_told(frozen_clock, client, world,
                                                                  session) -> None:
    mail.save_server(session, MailServer(**SERVER))
    save_secrets(session, mail.SECRETS, {"password": "mail-secret"})
    session.commit()
    report = start(client, world)
    [held] = check_out(client, world.astrid[1], report).json()["checkouts"]
    url = f"/api/reports/{report['id']}/checkouts/{held['id']}/break"
    # Stale after eight hours unused, unless an Administrator set another time.
    frozen_clock.advance(hours=9)
    boss = world.sign_in(world.admin)
    assert opened(client, world.sign_in(world.bo[0]), report)["checkouts"][0]["stale"]
    for who in (world.bo, world.mona, world.rasmus):
        assert client.post(url, headers=world.sign_in(who[0])).status_code == 403
    assert opened(client, boss, report)["may_break"]
    broken = client.post(url, headers=boss)
    assert broken.status_code == 200 and broken.json()["checkouts"] == []
    [logged] = entries(session, "report.checkout_broken")
    assert details(logged) == {"number": report["number"], "step": None,
                               "holder": world.astrid[0].id, "stale": True, "holder_told": True}
    [queued] = session.scalars(select(jobs.Job).where(jobs.Job.kind == "mail")).all()
    message = json.loads(queued.payload)
    session.commit()
    assert message["to"] == ["astrid@nordlys.example"]
    assert message["subject"] == f"Your checkout of {report['number']} was ended"
    assert "Fjordvik" not in message["body"] and "Security incident" not in message["body"]
    astrid = world.sign_in(world.astrid[0])
    assert save(client, astrid, report, q_title="After").status_code == 409


def test_how_long_until_a_checkout_is_stale_is_an_administrators_setting(frozen_clock, client,
                                                                          world, session
                                                                          ) -> None:
    url = "/api/admin/report-settings"
    assert client.get(url, headers=world.boss).json() == {"checkout_stale_hours": 8}
    assert client.get(url, headers=world.astrid[1]).status_code == 403
    assert client.put(url, headers=world.astrid[1],
                      json={"checkout_stale_hours": 1}).status_code == 403
    for hours in (0, 721):
        assert client.put(url, headers=world.boss,
                          json={"checkout_stale_hours": hours}).status_code == 422
    report = start(client, world)
    check_out(client, world.astrid[1], report)
    frozen_clock.advance(hours=9)
    astrid = world.sign_in(world.astrid[0])
    assert opened(client, astrid, report)["checkouts"][0]["stale"]
    assert client.put(url, headers=world.sign_in(world.admin),
                      json={"checkout_stale_hours": 12}).json() == {"checkout_stale_hours": 12}
    assert not opened(client, astrid, report)["checkouts"][0]["stale"]
    # Saving under it is using it.
    frozen_clock.advance(hours=11)
    astrid = world.sign_in(world.astrid[0])
    assert save(client, astrid, report, q_title="Still here").status_code == 200
    frozen_clock.advance(hours=11)
    astrid = world.sign_in(world.astrid[0])
    assert not opened(client, astrid, report)["checkouts"][0]["stale"]
    [changed] = entries(session, "admin.report_settings_changed")
    assert details(changed) == {"checkout_stale_hours": 12}


# Secrets


def test_a_secret_leaves_only_masked_and_is_seen_after_a_fresh_confirmation(client, world,
                                                                            session) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    check_out(client, astrid, report)
    saved = save(client, astrid, report, q_password="Sommer2026!Fjord")
    assert saved.json()["answers"] == {"q_password": {"masked": True, "printed": "So••••••rd"}}
    for reader in (astrid, world.rasmus[1], world.mona[1], world.boss):
        text_ = client.get(f"/api/reports/{report['id']}", headers=reader).text
        assert "Sommer2026" not in text_ and "masked" in text_
    url = f"/api/reports/{report['id']}/answers/q_password/reveal"
    unconfirmed = client.post(url, headers=astrid)
    assert unconfirmed.status_code == 403
    assert unconfirmed.headers["X-Skjald-Reason"] == "step_up_required"
    client.post("/api/auth/confirm-password", headers=astrid, json={"password": PASSWORD})
    revealed = client.post(url, headers=astrid)
    assert revealed.json() == {"value": "Sommer2026!Fjord", "seconds": 30}
    # The confirmation is used up: the next look asks again.
    assert client.post(url, headers=astrid).status_code == 403
    [logged] = entries(session, "report.secret_revealed")
    assert details(logged) == {"number": report["number"], "question": "q_password"}
    assert "Sommer" not in logged.details
    # The project's reviewer may look; a Manager and a technician off the project may not.
    client.post("/api/auth/confirm-password", headers=world.rasmus[1],
                json={"password": PASSWORD})
    assert client.post(url, headers=world.rasmus[1]).status_code == 200
    for who in (world.mona, world.tor):
        client.post("/api/auth/confirm-password", headers=who[1], json={"password": PASSWORD})
        refused = client.post(url, headers=who[1])
        assert refused.status_code == 403
        assert "X-Skjald-Reason" not in refused.headers
    assert len(entries(session, "report.secret_refused")) == 2
    client.post("/api/auth/confirm-password", headers=astrid, json={"password": PASSWORD})
    for question in ("q_title", "q_gone"):
        nothing = client.post(f"/api/reports/{report['id']}/answers/{question}/reveal",
                              headers=astrid)
        assert nothing.status_code == 404
    # The audit log never holds the secret.
    for entry in session.scalars(select(AuditEntry)):
        assert "Sommer2026" not in (entry.details or "")
    session.commit()


# The record


def test_opening_a_report_is_logged_and_saves_once_in_a_while(frozen_clock, client, world,
                                                              session) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    opened(client, world.rasmus[1], report)
    client.get(f"/api/reports/{report['id']}/activity", headers=world.rasmus[1])
    [viewed] = entries(session, "report.viewed")
    assert viewed.actor_name == "rasmus"
    assert details(viewed) == {"number": report["number"]}
    # Opened again in the same sitting (the page fetches it whenever someone else
    # saves), it isn't logged again; later, or by someone else, it is.
    opened(client, world.rasmus[1], report)
    assert len(entries(session, "report.viewed")) == 1
    opened(client, world.mona[1], report)
    frozen_clock.advance(minutes=11)
    opened(client, world.rasmus[1], report)
    assert [e.actor_name for e in entries(session, "report.viewed")] == [
        "rasmus", "mona", "rasmus"]
    check_out(client, astrid, report)
    for words in ("One", "Two", "Three"):
        save(client, astrid, report, q_title=words)
        frozen_clock.advance(minutes=4)
    assert len(entries(session, "report.answers_saved")) == 1
    frozen_clock.advance(minutes=4)
    save(client, astrid, report, q_title="Four")
    saved = entries(session, "report.answers_saved")
    assert [details(e)["saves"] for e in saved] == [1, 4]
    # Nothing the audit log says about a report says what's in it.
    for entry in session.scalars(select(AuditEntry).where(AuditEntry.target_type == "report")):
        assert "Security incident" not in entry.details and "Four" not in entry.details
    session.commit()


def test_a_draft_is_discarded_by_whoever_started_it(client, world, session) -> None:
    report = start(client, world)
    url = f"/api/reports/{report['id']}"
    assert client.request("DELETE", url, headers=world.bo[1],
                          json={"confirm_number": report["number"]}).status_code == 403
    assert not opened(client, world.bo[1], report)["may_discard"]
    assert client.request("DELETE", url, headers=world.astrid[1],
                          json={"confirm_number": "INC-2026-9999"}).status_code == 400
    check_out(client, world.bo[1], report, "s_access")
    held = client.request("DELETE", url, headers=world.astrid[1],
                          json={"confirm_number": report["number"]})
    assert held.status_code == 409
    [theirs] = opened(client, world.boss, report)["checkouts"]
    client.post(f"{url}/checkouts/{theirs['id']}/break", headers=world.boss)
    assert client.request("DELETE", url, headers=world.astrid[1],
                          json={"confirm_number": report["number"]}).status_code == 204
    assert client.get(url, headers=world.astrid[1]).status_code == 404
    [discarded] = entries(session, "report.discarded")
    assert details(discarded) == {"number": report["number"],
                                  "template": world.template["id"], "version": 1}


def test_the_title_and_the_site_change_under_a_checkout(client, world, session) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    url = f"/api/reports/{report['id']}"
    assert client.patch(url, headers=astrid, json={"title": "Renamed"}).status_code == 409
    check_out(client, astrid, report, "s_details")
    renamed = client.patch(url, headers=astrid,
                           json={"title": " Brute force, October ",
                                 "site_id": world.site["id"]})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Brute force, October"
    assert renamed.json()["site"] == {"id": world.site["id"], "name": "Terminal 3"}
    assert renamed.json()["context"]["report"]["title"] == "Brute force, October"
    assert client.patch(url, headers=astrid, json={"title": "   "}).status_code == 400
    assert client.patch(url, headers=astrid, json={"site_id": 9999}).status_code == 400
    [changed] = entries(session, "report.updated")
    assert details(changed) == {"number": report["number"], "fields": ["title", "site"]}


def test_a_templates_images_reach_the_reports_readers_only(client, world) -> None:
    report = start(client, world)
    missing = "0" * 64
    assert client.get(f"/api/reports/{report['id']}/assets/{missing}",
                      headers=world.astrid[1]).status_code == 404
    assert client.get(f"/api/reports/{report['id']}/assets/not-a-hash",
                      headers=world.astrid[1]).status_code == 404
    assert client.get(f"/api/reports/{report['id']}/assets/{missing}",
                      headers=world.ulla[1]).json()["detail"] == "That report doesn't exist."


def test_what_a_page_asks_on_a_timer_does_not_keep_its_session_alive(frozen_clock, client,
                                                                    world) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    url = f"/api/reports/{report['id']}/activity"
    background = {**astrid, "X-Skjald-Background": "1"}
    # Twenty-nine minutes of nothing but the page's own looks: the session idles out
    # at thirty, as if the page hadn't asked.
    for _ in range(29):
        frozen_clock.advance(minutes=1)
        assert client.get(url, headers=background).status_code == 200
    frozen_clock.advance(minutes=2)
    ended = client.get(url, headers=background)
    assert ended.status_code == 401
    assert ended.headers["X-Skjald-Reason"] == "session_timed_out"
    # Someone at work keeps it: the same looks without the mark count as activity.
    astrid = world.sign_in(world.astrid[0])
    for _ in range(35):
        frozen_clock.advance(minutes=1)
        assert client.get(url, headers=astrid).status_code == 200
    # Only reading can be asked without counting: a change always counts.
    marked = {**astrid, "X-Skjald-Background": "1"}
    for _ in range(35):
        frozen_clock.advance(minutes=1)
        assert check_out(client, marked, report, "s_details").status_code == 200


# The form, as the server reads it


def test_the_server_says_what_keeps_a_report_from_review(client, world) -> None:
    astrid = world.astrid[1]
    report = start(client, world)
    assert {"step": "s_details", "question": "q_title", "message": "is required."} in (
        report["state"]["missing"])
    assert report["state"]["required"] == ["q_title"]
    check_out(client, astrid, report)
    save(client, astrid, report, q_title="Portal brute force",
         q_hosts=[{"name": "not a host name!"}])
    state = client.post(f"/api/reports/{report['id']}/check", headers=astrid).json()
    assert [m["question"] for m in state["missing"]] == ["q_hosts"]
    assert state == opened(client, astrid, report)["state"]
    save(client, astrid, report, q_hosts=[{"name": "srv-01"}])
    assert client.post(f"/api/reports/{report['id']}/check", headers=astrid).json()[
        "missing"] == []
