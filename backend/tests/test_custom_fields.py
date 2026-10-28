"""Custom fields: who defines them, the values on customers and projects (sealed with
the customer's details), and the names templates read them by."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.audit import AuditEntry
from app.cel.engine import Engine, ExpressionError
from app.custom_fields import custom_names
from app.customers import Customer
from app.roles import Role, grant_role
from app.templates.names import CONTEXT

FIELDS = "/api/custom-fields"
CUSTOMERS = "/api/customers"


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
    return person("dagny", "report_designer")[1]


@pytest.fixture
def manager(person):
    return person("maja", "manager")[1]


def define(client, headers, applies_to, key, type_, label=None, **more):
    return client.post(FIELDS, headers=headers, json={
        "applies_to": applies_to, "key": key, "label": label or key.replace("_", " ").title(),
        "type": type_, **more})


@pytest.fixture
def fields(client, designer):
    made = {
        "agreement": define(client, designer, "customer", "agreement", "dropdown",
                            "Support agreement", options=["Gold", "Silver"]),
        "hours": define(client, designer, "customer", "hours", "number", "Hours a month"),
        "renewal": define(client, designer, "customer", "renewal", "date"),
        "onsite": define(client, designer, "customer", "onsite", "yes_no"),
        "desk": define(client, designer, "customer", "desk", "email", "Service desk"),
        "hotline": define(client, designer, "customer", "hotline", "phone"),
        "ticket": define(client, designer, "project", "ticket", "text", "Ticket number"),
        "notes": define(client, designer, "project", "notes", "long_text"),
    }
    assert all(r.status_code == 201 for r in made.values()), [r.text for r in made.values()]
    return {key: r.json() for key, r in made.items()}


def test_designers_define_fields_and_everyone_reads_them(client, designer, manager, person,
                                                         fields, session) -> None:
    listed = client.get(FIELDS, headers=manager).json()
    assert [f["key"] for f in listed] == ["agreement", "hours", "renewal", "onsite", "desk",
                                          "hotline", "ticket", "notes"]
    assert listed[0]["options"] == ["Gold", "Silver"]
    _, tech = person("tove", "technician")
    assert client.get(FIELDS, headers=tech).status_code == 200
    assert define(client, tech, "customer", "x", "text").status_code == 403
    assert define(client, manager, "customer", "x", "text").status_code == 403
    assert define(client, designer, "customer", "agreement", "text").status_code == 409
    assert define(client, designer, "customer", "tier", "dropdown").status_code == 422
    assert define(client, designer, "customer", "Bad-Key", "text").status_code == 422
    assert define(client, designer, "project", "agreement", "text").status_code == 201
    logged = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "custom_field.created")).all()
    assert len(logged) == 9


def test_a_field_keeps_its_key_and_type(client, designer, fields) -> None:
    agreement = fields["agreement"]
    changed = client.put(f"{FIELDS}/{agreement['id']}", headers=designer, json={
        "label": "Agreement", "help": "From the contract.", "options": ["Gold", "Silver", "Bronze"],
        "position": 5, "key": "renamed", "type": "text"})
    assert changed.status_code == 200
    body = changed.json()
    assert (body["key"], body["type"], body["label"], body["options"], body["position"]) == (
        "agreement", "dropdown", "Agreement", ["Gold", "Silver", "Bronze"], 5)
    assert client.put(f"{FIELDS}/{agreement['id']}", headers=designer, json={
        "label": "Agreement", "options": []}).status_code == 400
    assert client.put(f"{FIELDS}/9999", headers=designer, json={"label": "x"}).status_code == 404


def test_values_are_checked_and_sealed_with_the_customer(client, admin, manager, fields,
                                                         session) -> None:
    made = client.post(CUSTOMERS, headers=manager, json={
        "name": "Fjordvik Logistik A/S", "custom": {
            "agreement": "Gold", "hours": 12, "renewal": "2027-03-01", "onsite": True,
            "desk": "it@fjordvik.example", "hotline": "+45 70 20 30 40"}})
    assert made.status_code == 200, made.text
    customer = made.json()
    assert customer["custom"] == {"agreement": "Gold", "hours": 12.0, "renewal": "2027-03-01",
                                  "onsite": True, "desk": "it@fjordvik.example",
                                  "hotline": "+45 70 20 30 40"}
    row = session.get(Customer, customer["id"])
    assert b"it@fjordvik.example" not in row.sealed and b"Gold" not in row.sealed
    session.rollback()

    url = f"{CUSTOMERS}/{customer['id']}"
    for wrong, message in (({"agreement": "Platinum"}, "options"), ({"hours": "many"}, "number"),
                           ({"hours": True}, "number"), ({"renewal": "soon"}, "date"),
                           ({"onsite": "yes"}, "yes or no"), ({"desk": "nobody"}, "email"),
                           ({"hotline": "call me"}, "phone"), ({"ticket": "X-1"}, "no custom")):
        refused = client.patch(url, headers=manager, json={"custom": wrong})
        assert refused.status_code == 400, wrong
        assert message in refused.json()["detail"], refused.json()
    changed = client.patch(url, headers=manager, json={"custom": {"hours": 8, "desk": ""}})
    assert changed.json()["custom"]["hours"] == 8.0
    assert "desk" not in changed.json()["custom"]
    assert changed.json()["custom"]["agreement"] == "Gold"
    renamed = client.patch(url, headers=manager, json={"name": "Fjordvik A/S"}).json()
    assert renamed["custom"]["agreement"] == "Gold"
    updates = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "customer.updated")).all()
    assert [u.details for u in updates][0].count("custom") == 1
    assert "Gold" not in "".join(u.details for u in updates)


def test_archiving_a_field_keeps_its_values(client, designer, manager, fields) -> None:
    customer = client.post(CUSTOMERS, headers=manager, json={
        "name": "Fjordvik Logistik A/S", "custom": {"agreement": "Silver"}}).json()
    field = fields["agreement"]
    archived = client.put(f"{FIELDS}/{field['id']}", headers=designer, json={
        "label": field["label"], "options": field["options"], "archived": True})
    assert archived.json()["archived"] is True
    url = f"{CUSTOMERS}/{customer['id']}"
    assert "agreement" not in client.get(url, headers=manager).json()["custom"]
    assert client.patch(url, headers=manager,
                        json={"custom": {"agreement": "Gold"}}).status_code == 400
    assert "agreement" not in [f["key"] for f in client.get(FIELDS, headers=manager).json()]
    every = client.get(f"{FIELDS}?archived=true", headers=manager).json()
    assert "agreement" in [f["key"] for f in every]
    client.put(f"{FIELDS}/{field['id']}", headers=designer, json={
        "label": field["label"], "options": field["options"], "archived": False})
    assert client.get(url, headers=manager).json()["custom"] == {"agreement": "Silver"}


def test_projects_have_custom_fields_too(client, manager, fields) -> None:
    customer = client.post(CUSTOMERS, headers=manager, json={"name": "Fjordvik"}).json()
    made = client.post(f"{CUSTOMERS}/{customer['id']}/projects", headers=manager, json={
        "name": "Firewall incident", "custom": {"ticket": "INC-4711"}})
    assert made.status_code == 200, made.text
    project = made.json()
    assert project["custom"] == {"ticket": "INC-4711"}
    url = f"/api/projects/{project['id']}"
    assert client.patch(url, headers=manager,
                        json={"custom": {"agreement": "Gold"}}).status_code == 400
    changed = client.patch(url, headers=manager,
                           json={"custom": {"notes": "Call before visiting."}}).json()
    assert changed["custom"] == {"ticket": "INC-4711", "notes": "Call before visiting."}
    renamed = client.patch(url, headers=manager, json={"name": "Firewall"}).json()
    assert renamed["custom"]["ticket"] == "INC-4711"


def test_templates_read_them_by_name(client, fields, session) -> None:
    names = custom_names(session)
    assert names == {
        "customer.custom.agreement": "string", "customer.custom.hours": "double",
        "customer.custom.renewal": "timestamp", "customer.custom.onsite": "bool",
        "customer.custom.desk": "string", "customer.custom.hotline": "string",
        "project.custom.ticket": "string", "project.custom.notes": "string",
    }
    engine = Engine({**CONTEXT, **names})
    assert engine.check('customer.custom.hours > 10.0 && customer.custom.agreement == "Gold"') \
        == "bool"
    assert engine.check("days_between(report.date, customer.custom.renewal)") == "int"
    with pytest.raises(ExpressionError):
        engine.check("customer.custom.nope")
    with pytest.raises(ExpressionError):
        engine.check("customer.custom")
