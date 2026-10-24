import io

import pytest
from cryptography.exceptions import InvalidTag
from PIL import Image
from sqlalchemy import select, text

from app.audit import AuditEntry
from app.crypto.keys import load_master_key, unwrap_key
from app.customers import (
    SEES_CUSTOMERS,
    Customer,
    CustomerContact,
    Sealer,
    bound_to,
)
from app.roles import Role, grant_role
from app.settings import settings
from tests.conftest import PASSWORD

CUSTOMERS = "/api/customers"
A, D, T, R, U = "administrator", "report_designer", "technician", "reviewer", "auditor"


def audit_entries(session, action):
    found = list(session.scalars(select(AuditEntry).where(AuditEntry.action == action)))
    session.commit()
    return found


@pytest.fixture
def person(make_user, session, full_session):
    """Someone with the given roles, signed in. Returns (user, headers)."""

    def make(username, *roles):
        user = make_user(username, display_name=username.title())
        for role in roles:
            grant_role(session, user, Role(role), actor=None, ip=None)
        session.commit()
        return user, full_session(user)

    return make


@pytest.fixture
def nordlys(client, admin):
    """A customer with a site and a contact. Returns its detail."""
    _, headers = admin
    customer = client.post(CUSTOMERS, headers=headers, json={
        "name": "Nordlys IT ApS", "cvr": "1234 5678", "address": "Fjordvej 1, 8000 Aarhus C",
    }).json()
    client.post(f"{CUSTOMERS}/{customer['id']}/sites", headers=headers,
                json={"name": "Head office", "address": "Fjordvej 1"})
    return client.post(f"{CUSTOMERS}/{customer['id']}/contacts", headers=headers, json={
        "name": "Sigrid Holm", "role": "IT manager", "email": "sigrid@nordlys.example",
        "phone": "+45 12 34 56 78",
    }).json()


def assign(client, admin, customer_id, *users):
    _, headers = admin
    response = client.put(f"{CUSTOMERS}/{customer_id}/assignments", headers=headers,
                          json={"user_ids": [u.id for u in users]})
    assert response.status_code == 200, response.text
    return response.json()


# Who sees what


def test_who_sees_customers_follows_the_spec() -> None:
    # The spec's "See customers" row: All, Names only, Assigned, Assigned, Metadata only.
    assert {role.value: sight for role, sight in SEES_CUSTOMERS.items()} == {
        A: "all", D: "names", T: "assigned", R: "assigned", U: "metadata",
    }


def test_technicians_see_only_the_customers_they_are_assigned_to(
    client, admin, nordlys, person, session
) -> None:
    _, headers = admin
    other = client.post(CUSTOMERS, headers=headers, json={"name": "Fjeldstue A/S"}).json()
    astrid, as_astrid = person("astrid", T)
    assign(client, admin, nordlys["id"], astrid)

    listed = client.get(CUSTOMERS, headers=as_astrid).json()
    assert [(c["name"], c["visibility"]) for c in listed] == [("Nordlys IT ApS", "full")]
    detail = client.get(f"{CUSTOMERS}/{nordlys['id']}", headers=as_astrid).json()
    assert detail["contacts"][0]["email"] == "sigrid@nordlys.example"
    assert not detail["may_manage"] and detail["may_create_projects"]

    hidden = client.get(f"{CUSTOMERS}/{other['id']}", headers=as_astrid)
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "That customer doesn't exist."
    assert len(audit_entries(session, "customer.access_denied")) == 1


def test_designers_see_names_and_auditors_see_metadata(
    client, admin, nordlys, person
) -> None:
    _, as_designer = person("dagny", D)
    _, as_auditor = person("ulf", U)

    names = client.get(CUSTOMERS, headers=as_designer).json()
    assert names == [{"id": nordlys["id"], "name": "Nordlys IT ApS", "visibility": "names",
                      "cvr": None, "active_projects": None, "archived_projects": None,
                      "logo_url": None}]
    metadata = client.get(f"{CUSTOMERS}/{nordlys['id']}", headers=as_auditor).json()
    assert metadata["visibility"] == "metadata" and metadata["active_projects"] == 0
    assert metadata["contacts"] is None and metadata["address"] is None
    assert metadata["cvr"] is None


def test_people_without_a_role_see_no_customers(client, admin, nordlys, person) -> None:
    _, headers = person("nobody")
    assert client.get(CUSTOMERS, headers=headers).json() == []
    assert client.get(f"{CUSTOMERS}/{nordlys['id']}", headers=headers).status_code == 404


def test_only_administrators_create_and_change_customers(client, nordlys, person) -> None:
    astrid, as_astrid = person("astrid", T)
    assert client.post(CUSTOMERS, headers=as_astrid, json={"name": "Mine"}).status_code == 403
    changed = client.patch(f"{CUSTOMERS}/{nordlys['id']}", headers=as_astrid,
                           json={"name": "Renamed"})
    assert changed.status_code == 403


# What's kept, and how


def test_a_customer_gets_its_own_key_bound_to_it(client, admin, nordlys, session) -> None:
    customer = session.get(Customer, nordlys["id"])
    session.commit()
    master = load_master_key(settings.master_key_path)
    key = unwrap_key(master, customer.wrapped_key,
                     context=f"skjald/customer-key/{customer.id}".encode())
    assert len(key) == 32
    with pytest.raises(InvalidTag):  # moved onto another customer, it won't open
        unwrap_key(master, customer.wrapped_key, context=b"skjald/customer-key/999")


def test_addresses_and_contacts_are_sealed_with_the_customer_key(
    client, admin, nordlys, session
) -> None:
    customer = session.get(Customer, nordlys["id"])
    contact = session.scalars(select(CustomerContact)).one()
    session.commit()
    assert b"Fjordvej" not in customer.sealed
    assert b"sigrid" not in contact.sealed
    sealer = Sealer(customer)
    assert sealer.open("contact", contact.id, contact.sealed)["name"] == "Sigrid Holm"
    with pytest.raises(InvalidTag):  # a sealed value moved to another record won't open
        sealer.open("contact", contact.id + 1, contact.sealed)
    assert bound_to(customer.id, "contact", contact.id) != bound_to(customer.id, "site", contact.id)


def test_the_audit_log_names_contacts_by_id_only(client, admin, nordlys, session) -> None:
    added = audit_entries(session, "customer.contact_added")[0]
    assert "Sigrid" not in added.details and "nordlys.example" not in added.details


def test_a_cvr_number_has_eight_digits(client, admin, nordlys) -> None:
    _, headers = admin
    assert nordlys["cvr"] == "12345678"
    short = client.patch(f"{CUSTOMERS}/{nordlys['id']}", headers=headers, json={"cvr": "1234"})
    assert short.status_code == 422
    cleared = client.patch(f"{CUSTOMERS}/{nordlys['id']}", headers=headers, json={"cvr": ""})
    assert cleared.json()["cvr"] is None


def test_details_change_and_sites_and_contacts_come_and_go(client, admin, nordlys) -> None:
    _, headers = admin
    cid = nordlys["id"]
    changed = client.patch(f"{CUSTOMERS}/{cid}", headers=headers, json={
        "address": "Ny adresse 2", "language": "en", "retention_months": 24,
    }).json()
    assert (changed["address"], changed["language"], changed["retention_months"]) == (
        "Ny adresse 2", "en", 24)
    site = changed["sites"][0]
    renamed = client.put(f"{CUSTOMERS}/{cid}/sites/{site['id']}", headers=headers,
                         json={"name": "Hovedkontor", "address": "Fjordvej 1"}).json()
    assert renamed["sites"][0]["name"] == "Hovedkontor"
    contact = renamed["contacts"][0]
    gone = client.delete(f"{CUSTOMERS}/{cid}/contacts/{contact['id']}", headers=headers).json()
    assert gone["contacts"] == []
    assert client.delete(f"{CUSTOMERS}/{cid}/sites/{site['id']}", headers=headers
                         ).json()["sites"] == []


def test_only_technicians_and_reviewers_are_assigned(
    client, admin, nordlys, person, session
) -> None:
    _, headers = admin
    dagny, _ = person("dagny", D)
    refused = client.put(f"{CUSTOMERS}/{nordlys['id']}/assignments", headers=headers,
                         json={"user_ids": [dagny.id]})
    assert refused.status_code == 400
    astrid, _ = person("astrid", T)
    rolf, _ = person("rolf", R)
    detail = assign(client, admin, nordlys["id"], astrid, rolf)
    assert [p["username"] for p in detail["assigned"]] == ["astrid", "rolf"]
    assert {p["username"] for p in detail["assignable"]} == {"astrid", "rolf"}
    assert len(audit_entries(session, "customer.assigned")) == 2
    assign(client, admin, nordlys["id"], rolf)
    assert len(audit_entries(session, "customer.unassigned")) == 1


def test_a_logo_is_shown_only_to_those_who_see_the_customer(
    client, admin, nordlys, person
) -> None:
    _, headers = admin
    out = io.BytesIO()
    Image.new("RGB", (900, 300), (20, 40, 80)).save(out, format="PNG")
    detail = client.put(f"{CUSTOMERS}/{nordlys['id']}/logo", content=out.getvalue(),
                        headers=headers | {"Content-Type": "application/octet-stream"}).json()
    url = detail["logo_url"]
    assert client.get(url, headers=headers).headers["content-type"] == "image/png"
    _, as_stranger = person("astrid", T)
    assert client.get(url, headers=as_stranger).status_code == 404


# Deleting


def test_deleting_a_customer_takes_its_key_and_everything_with_it(
    client, admin, nordlys, session, frozen_clock
) -> None:
    _, headers = admin
    cid = nordlys["id"]
    client.post(f"{CUSTOMERS}/{cid}/projects", headers=headers, json={"name": "Incident"})

    wrong = client.request("DELETE", f"{CUSTOMERS}/{cid}", headers=headers,
                           json={"confirm_name": "Nordlys"})
    assert wrong.status_code == 400
    unconfirmed = client.request("DELETE", f"{CUSTOMERS}/{cid}", headers=headers,
                                 json={"confirm_name": "Nordlys IT ApS"})
    assert unconfirmed.headers["X-Skjald-Reason"] == "step_up_required"

    client.post("/api/auth/confirm-password", headers=headers, json={"password": PASSWORD})
    gone = client.request("DELETE", f"{CUSTOMERS}/{cid}", headers=headers,
                          json={"confirm_name": "Nordlys IT ApS"})
    assert gone.status_code == 204
    assert client.get(f"{CUSTOMERS}/{cid}", headers=headers).status_code == 404
    for table in ("customers", "customer_sites", "customer_contacts", "projects"):
        assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table
    session.commit()
    deleted = audit_entries(session, "customer.deleted")[0]
    assert deleted.details == '{"name":"Nordlys IT ApS","projects":1}'


def test_deleted_rows_are_overwritten_in_the_database_file(engine) -> None:
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA secure_delete").scalar() == 1


# Projects


@pytest.fixture
def astrid_on_nordlys(client, admin, nordlys, person):
    astrid, headers = person("astrid", T)
    assign(client, admin, nordlys["id"], astrid)
    return astrid, headers


def test_an_assigned_technician_creates_numbered_projects(
    client, nordlys, astrid_on_nordlys, frozen_clock, session
) -> None:
    astrid, headers = astrid_on_nordlys
    cid = nordlys["id"]
    site = nordlys["sites"][0]["id"]
    contact = nordlys["contacts"][0]["id"]
    first = client.post(f"{CUSTOMERS}/{cid}/projects", headers=headers, json={
        "name": "Ransomware incident", "start_date": "2026-10-20", "end_date": "2026-10-24",
        "responsible_id": astrid.id, "contact_id": contact, "site_ids": [site],
        "classification": "TLP:RED",
    }).json()
    assert first["number"] == "P-2026-0001"
    assert first["responsible"]["name"] == "Astrid"
    assert first["contact"]["name"] == "Sigrid Holm" and first["sites"][0]["name"] == "Head office"
    assert first["may_edit"]
    second = client.post(f"{CUSTOMERS}/{cid}/projects", headers=headers,
                         json={"name": "Yearly review"}).json()
    assert (second["number"], second["classification"]) == ("P-2026-0002", "TLP:AMBER")
    assert [p["number"] for p in client.get("/api/projects", headers=headers).json()] == [
        "P-2026-0002", "P-2026-0001"]
    assert len(audit_entries(session, "project.created")) == 2


def test_reviewers_see_projects_but_do_not_create_them(
    client, admin, nordlys, person
) -> None:
    rolf, headers = person("rolf", R)
    assign(client, admin, nordlys["id"], rolf)
    refused = client.post(f"{CUSTOMERS}/{nordlys['id']}/projects", headers=headers,
                          json={"name": "Not mine to make"})
    assert refused.status_code == 403
    assert client.get(f"{CUSTOMERS}/{nordlys['id']}/projects", headers=headers).json() == []


def test_unassigned_technicians_cannot_reach_projects(
    client, admin, nordlys, person
) -> None:
    _, headers = admin
    project = client.post(f"{CUSTOMERS}/{nordlys['id']}/projects", headers=headers,
                          json={"name": "Incident"}).json()
    _, as_bo = person("bo", T)
    assert client.get(f"/api/projects/{project['id']}", headers=as_bo).status_code == 404
    assert client.post(f"{CUSTOMERS}/{nordlys['id']}/projects", headers=as_bo,
                       json={"name": "Sneaky"}).status_code == 404
    assert client.get("/api/projects", headers=as_bo).json() == []


def test_a_project_links_only_to_its_own_customer(
    client, admin, nordlys, astrid_on_nordlys, person
) -> None:
    _, headers = admin
    other = client.post(CUSTOMERS, headers=headers, json={"name": "Fjeldstue A/S"}).json()
    other = client.post(f"{CUSTOMERS}/{other['id']}/contacts", headers=headers,
                        json={"name": "Someone Else"}).json()
    url = f"{CUSTOMERS}/{nordlys['id']}/projects"
    foreign_contact = client.post(url, headers=headers, json={
        "name": "X", "contact_id": other["contacts"][0]["id"]})
    assert foreign_contact.status_code == 400
    bo, _ = person("bo", T)  # a technician, but not on this customer
    not_assigned = client.post(url, headers=headers, json={"name": "X", "responsible_id": bo.id})
    assert not_assigned.status_code == 400
    backwards = client.post(url, headers=headers, json={
        "name": "X", "start_date": "2026-10-24", "end_date": "2026-10-01"})
    assert backwards.status_code == 422


def test_an_archived_project_is_read_only_until_an_administrator_reopens_it(
    client, admin, nordlys, astrid_on_nordlys, session
) -> None:
    _, as_admin = admin
    _, headers = astrid_on_nordlys
    project = client.post(f"{CUSTOMERS}/{nordlys['id']}/projects", headers=headers,
                          json={"name": "Incident"}).json()
    archived = client.post(f"/api/projects/{project['id']}/archive", headers=headers).json()
    assert archived["archived_at"] and not archived["may_edit"]
    assert client.patch(f"/api/projects/{project['id']}", headers=headers,
                        json={"name": "Changed"}).status_code == 409
    listed = client.get(f"{CUSTOMERS}/{nordlys['id']}/projects?archived=true", headers=headers)
    assert [p["id"] for p in listed.json()] == [project["id"]]
    assert client.get("/api/projects", headers=headers).json() == []

    assert client.post(f"/api/projects/{project['id']}/reopen", headers=headers
                       ).status_code == 403
    reopened = client.post(f"/api/projects/{project['id']}/reopen", headers=as_admin).json()
    assert reopened["archived_at"] is None
    changed = client.patch(f"/api/projects/{project['id']}", headers=headers,
                           json={"name": "Changed", "classification": "TLP:GREEN"}).json()
    assert (changed["name"], changed["classification"]) == ("Changed", "TLP:GREEN")
    actions = [e.action for e in session.scalars(select(AuditEntry).where(
        AuditEntry.target_type == "project"))]
    session.commit()
    assert actions == ["project.created", "project.archived", "project.reopened",
                       "project.updated"]


def test_project_numbers_are_never_reused(
    frozen_clock, client, admin, nordlys, full_session
) -> None:
    user, headers = admin
    url = f"{CUSTOMERS}/{nordlys['id']}/projects"
    numbers = [client.post(url, headers=headers, json={"name": f"P{i}"}).json()["number"]
               for i in range(3)]
    assert numbers == ["P-2026-0001", "P-2026-0002", "P-2026-0003"]
    # Even the newest one gone, with its customer, doesn't free its number.
    client.post("/api/auth/confirm-password", headers=headers, json={"password": PASSWORD})
    client.request("DELETE", f"{CUSTOMERS}/{nordlys['id']}", headers=headers,
                   json={"confirm_name": "Nordlys IT ApS"})
    other = client.post(CUSTOMERS, headers=headers, json={"name": "Fjeldstue A/S"}).json()
    assert client.post(f"{CUSTOMERS}/{other['id']}/projects", headers=headers,
                       json={"name": "next"}).json()["number"] == "P-2026-0004"
    frozen_clock.advance(days=70)  # into 2027
    headers = full_session(user)
    assert client.post(f"{CUSTOMERS}/{other['id']}/projects", headers=headers,
                       json={"name": "new year"}).json()["number"] == "P-2027-0001"
