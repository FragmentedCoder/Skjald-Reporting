"""The shared library: who changes it, versions, locks, snippets and imported tables."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit import AuditEntry
from app.library.models import LibraryEntry, LibraryVersion
from app.library.values import library_names, library_values
from app.roles import Role, grant_role

LIBRARY = "/api/library"


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
def tech(person):
    return person("tove", "technician")


def add(client, headers, kind, key, value, description=""):
    return client.post(LIBRARY, headers=headers,
                       json={"kind": kind, "key": key, "value": value, "description": description})


@pytest.mark.parametrize("role", ["reviewer", "manager", "auditor"])
def test_only_designers_technicians_and_administrators_use_the_library(client, person, role,
                                                                       session) -> None:
    _, headers = person(f"someone_{role}", role)
    assert client.get(LIBRARY, headers=headers).status_code == 403
    assert add(client, headers, "variable", "x", {"value": "1"}).status_code == 403


def test_every_change_is_a_version_and_logged(client, tech, person, session) -> None:
    _, headers = tech
    created = add(client, headers, "variable", "support_phone", {"value": "+45 70 20 30 40"},
                  "The service desk")
    assert created.status_code == 201
    entry = created.json()
    assert (entry["version"], entry["updated_by"]) == (1, "Tove")
    changed = client.put(f"{LIBRARY}/{entry['id']}", headers=headers,
                         json={"value": {"value": "+45 70 20 30 41"}, "version": 1})
    assert changed.json()["version"] == 2
    # A change made from version 1 again is refused: someone else's would be lost.
    _, designer = person("dagny", "report_designer")
    stale = client.put(f"{LIBRARY}/{entry['id']}", headers=designer,
                       json={"value": {"value": "+45 00 00 00 00"}, "version": 1})
    assert stale.status_code == 409
    assert "Tove changed this entry" in stale.json()["detail"]
    history = client.get(f"{LIBRARY}/{entry['id']}/versions", headers=headers).json()
    assert [v["value"]["value"] for v in history] == ["+45 70 20 30 41", "+45 70 20 30 40"]
    logged = entries(session, "library.changed")
    assert json.loads(logged[0].details) == {"kind": "variable", "key": "support_phone",
                                             "version": 2}
    assert "+45" not in logged[0].details
    assert add(client, headers, "variable", "support_phone", {"value": "x"}).status_code == 409


def test_administrators_lock_entries_and_nobody_changes_them(client, tech, admin, session) -> None:
    _, headers = tech
    _, boss = admin
    entry = add(client, headers, "variable", "company_cvr", {"value": "12345678"}).json()
    assert client.post(f"{LIBRARY}/{entry['id']}/lock", headers=headers).status_code == 403
    locked = client.post(f"{LIBRARY}/{entry['id']}/lock", headers=boss).json()
    assert (locked["locked"], locked["locked_by"]) == (True, "Ingrid Admin")
    for who in (headers, boss):
        refused = client.put(f"{LIBRARY}/{entry['id']}", headers=who,
                             json={"value": {"value": "x"}, "version": 1})
        assert refused.status_code == 409
    assert client.delete(f"{LIBRARY}/{entry['id']}", headers=headers).status_code == 409
    client.post(f"{LIBRARY}/{entry['id']}/unlock", headers=boss)
    assert client.put(f"{LIBRARY}/{entry['id']}", headers=headers,
                      json={"value": {"value": "87654321"}, "version": 1}).status_code == 200
    assert [len(entries(session, a)) for a in ("library.locked", "library.unlocked")] == [1, 1]


def test_a_snippet_uses_variables_but_never_other_snippets(client, tech) -> None:
    _, headers = tech
    ok = add(client, headers, "snippet", "handover",
             {"text": "Call {{vars.support_phone}} for the full password."})
    assert ok.status_code == 201
    for bad in ("See {{text.other}}.", "Call {{ upper(vars.x) }}", "Open {{vars.x"):
        refused = add(client, headers, "snippet", "bad", {"text": bad})
        assert refused.status_code == 422
        assert refused.json()["detail"].startswith("A snippet can use variables")


def test_tables_import_from_csv_and_json(client, tech, session) -> None:
    _, headers = tech
    table = add(client, headers, "table", "severity",
                {"columns": ["Label"], "rows": {"critical": ["Kritisk"]}}).json()
    csv_file = "Severity,Label,Colour\ncritical,Kritisk,Red\nhigh,Høj,Amber\n\n"
    upload = {**headers, "Content-Type": "application/octet-stream"}
    imported = client.post(f"{LIBRARY}/{table['id']}/import", content=csv_file.encode(),
                           headers=upload)
    assert imported.status_code == 200
    assert imported.json()["value"] == {
        "key_label": "Severity", "columns": ["Label", "Colour"],
        "rows": {"critical": ["Kritisk", "Red"], "high": ["Høj", "Amber"]}}
    as_json = client.post(f"{LIBRARY}/{table['id']}/import?format=json",
                          content=json.dumps({"low": "Lav", "medium": "Middel"}).encode(),
                          headers=upload)
    assert as_json.json()["value"]["rows"] == {"low": ["Lav"], "medium": ["Middel"]}
    for broken, format in ((b"only a header\n", "csv"), (b"\xff\xfe", "csv"),
                           (b"[1, 2]", "json")):
        refused = client.post(f"{LIBRARY}/{table['id']}/import?format={format}", content=broken,
                              headers=upload)
        assert refused.status_code == 422, broken
    assert entries(session, "library.imported")


def test_removing_keeps_the_history_and_frees_nothing_to_rewrite(client, tech, engine) -> None:
    _, headers = tech
    entry = add(client, headers, "variable", "old", {"value": "1"}).json()
    assert client.delete(f"{LIBRARY}/{entry['id']}", headers=headers).status_code == 204
    assert client.get(LIBRARY, headers=headers).json() == []
    again = add(client, headers, "variable", "old", {"value": "2"}).json()
    assert (again["id"], again["version"]) == (entry["id"], 2)
    for statement in ("UPDATE library_versions SET value = '{}'", "DELETE FROM library_versions"):
        with engine.connect() as conn, pytest.raises(DBAPIError, match="kept as they were"):
            conn.execute(text(statement))


def test_templates_read_the_library(client, tech, session) -> None:
    _, headers = tech
    add(client, headers, "variable", "support_phone", {"value": "+45 70 20 30 40"})
    add(client, headers, "snippet", "handover", {"text": "Call {{vars.support_phone}}."})
    add(client, headers, "table", "severity", {"columns": ["Label"], "rows": {"high": ["Høj"]}})
    pairs = [(e, v) for e in session.scalars(select(LibraryEntry))
             for v in session.scalars(select(LibraryVersion).where(
                 LibraryVersion.entry_id == e.id, LibraryVersion.number == e.current))]
    session.commit()
    assert library_names(e for e, _ in pairs) == {"vars.support_phone": "string",
                                                   "text.handover": "string"}
    values, tables = library_values(pairs)
    assert values == {"vars": {"support_phone": "+45 70 20 30 40"},
                      "text": {"handover": "Call +45 70 20 30 40."}}
    assert tables["severity"].rows == {"high": ["Høj"]}
