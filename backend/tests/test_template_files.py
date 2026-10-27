""".skjald files: strings and rules by element, export and import, and hostile files.

shared/templates/strings.json runs here and in the browser's tests (strings.test.ts).
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import select

from app.audit import AuditEntry
from app.library.models import LibraryEntry
from app.roles import Role, grant_role
from app.styles.models import Style
from app.templates import files
from app.templates.content import TemplateContent

SHARED = Path(__file__).resolve().parents[2] / "shared" / "templates"
INCIDENT = json.loads((SHARED / "incident.json").read_text())
STRINGS = json.loads((SHARED / "strings.json").read_text())
TEMPLATES = "/api/templates"


def incident() -> dict[str, Any]:
    return TemplateContent.model_validate(copy.deepcopy(INCIDENT)).dump()


# Strings and rules


def test_the_shared_strings_and_rules() -> None:
    # As written in incident.json: the browser gathers from the same document.
    assert files.strings(copy.deepcopy(INCIDENT)) == STRINGS["strings"]
    assert files.rules(copy.deepcopy(INCIDENT)) == STRINGS["rules"]


def test_strings_and_rules_go_back_where_they_came_from() -> None:
    content = incident()
    same = files.apply(copy.deepcopy(content), texts=files.strings(content),
                       expressions=files.rules(content))
    assert same == content
    changed = files.apply(copy.deepcopy(content), texts={
        "q_summary/label": "Resumé af hændelsen", "b_cover/facts/0/label": "Rapport",
        "q_attackers/settings/columns/2/settings/options/0/label": "Blokeret",
        "q_cvss/valid_message": "Mellem 0 og 10."},
        expressions={"b_attack/visible_when": "true"})
    step = changed["form"][0]["questions"][0]
    assert step["label"] == "Resumé af hændelsen"
    assert changed["layout"][0]["facts"][0]["label"] == "Rapport"
    assert files.rules(changed)["b_attack/visible_when"] == "true"
    attackers = changed["form"][1]["questions"][1]["settings"]["columns"][2]["settings"]
    assert attackers["options"][0] == {"value": "blocked", "label": "Blokeret"}
    assert TemplateContent.model_validate(changed)
    for wrong in ({"q_nope/label": "x"}, {"q_summary/visible_when": "x"},
                  {"q_attackers/settings/columns/2/settings/options/0/value": "x"}):
        with pytest.raises(files.TemplateFileRejected, match="names nothing"):
            files.apply(copy.deepcopy(content), texts=wrong)
    with pytest.raises(files.TemplateFileRejected):
        files.apply(copy.deepcopy(content), texts={"q_summary/label": "x"},
                    expressions={"q_summary/label": "true"})


# Export and import


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


def picture() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "#2B5D8A").save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def published(client, designer):
    """The sample incident report, published, with a picture and a library table."""
    made = client.post(TEMPLATES, headers=designer, json={"name": "Security incident report"})
    tid = made.json()["id"]
    image = client.post(f"{TEMPLATES}/{tid}/assets?name=graph.png", content=picture(),
                        headers={**designer, "Content-Type": "application/octet-stream"}).json()
    client.post("/api/library", headers=designer, json={
        "kind": "table", "key": "severity", "description": "Severity by rating",
        "value": {"key_label": "Rating", "columns": ["Severity"],
                  "rows": {"high": ["High"], "low": ["Low"]}}})
    content = incident()
    content["layout"][2]["blocks"].append({"id": "b_graph", "kind": "image",
                                           "asset": image["sha256"], "caption": "The graph"})
    content["layout"][1]["blocks"].append({"id": "b_lookup", "kind": "heading",
                                           "text": '{{ lookup("severity", "high") }}'})
    draft = client.get(f"{TEMPLATES}/{tid}/draft", headers=designer).json()
    saved = client.put(f"{TEMPLATES}/{tid}/draft", headers=designer,
                       json={"content": content, "revision": draft["revision"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["problems"] == [], saved.json()["problems"]
    done = client.post(f"{TEMPLATES}/{tid}/publish", headers=designer,
                       json={"revision": saved.json()["revision"], "note": "First"})
    assert done.status_code == 200, done.text
    return tid, content, image["sha256"]


def export(client, headers, tid, version=None):
    return client.get(f"{TEMPLATES}/{tid}/export" + (f"?version={version}" if version else ""),
                      headers=headers)


def import_(client, headers, data):
    return client.post(f"{TEMPLATES}/import", content=data,
                       headers={**headers, "Content-Type": "application/octet-stream"})


def unpack(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def pack(entries: dict[str, bytes], *, rehash: bool = True) -> bytes:
    """A ZIP of these files, with the manifest's hashes worked out again."""
    entries = dict(entries)
    if rehash and "manifest.json" in entries:
        manifest = json.loads(entries["manifest.json"])
        manifest["files"] = {n: hashlib.sha256(b).hexdigest()
                             for n, b in entries.items() if n != "manifest.json"}
        entries["manifest.json"] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return out.getvalue()


def test_a_template_goes_out_and_comes_back_the_same(client, designer, published,
                                                      session) -> None:
    tid, content, sha = published
    sent = export(client, designer, tid)
    assert sent.status_code == 200
    assert sent.headers["content-type"] == "application/zip"
    assert 'filename="security-incident-report-v1.skjald"' in sent.headers["content-disposition"]
    inside = unpack(sent.content)
    assert set(inside) == {"manifest.json", "settings.json", "questions.json", "layout.json",
                           "rules.json", "strings.json", "styles.json", "library.json",
                           "sample.json", f"assets/{sha}.png"}
    manifest = json.loads(inside["manifest.json"])
    assert (manifest["format"], manifest["template"]["version"]) == ("skjald-template", 1)
    library = json.loads(inside["library.json"])
    assert [(e["kind"], e["key"]) for e in library] == [("table", "severity")]

    came = import_(client, designer, sent.content)
    assert came.status_code == 201, came.text
    body = came.json()
    assert body["template"]["name"] == "Security incident report (imported)"
    assert body["template"]["uuid"] != manifest["template"]["uuid"]
    assert body["library_kept"] == ['lookup("severity")'] and body["library_added"] == []
    new_id = body["template"]["id"]
    draft = client.get(f"{TEMPLATES}/{new_id}/draft", headers=designer).json()
    assert draft["problems"] == []
    assert TemplateContent.model_validate(draft["content"]).dump() == \
        TemplateContent.model_validate(content).dump()
    assert [a["sha256"] for a in body["template"]["assets"]] == [sha]
    actions = [e.action for e in session.scalars(select(AuditEntry).where(
        AuditEntry.action.in_(["template.exported", "template.imported"])))]
    assert actions == ["template.exported", "template.imported"]


def test_a_translator_edits_strings_json_alone(client, designer, published) -> None:
    tid, _, _ = published
    inside = unpack(export(client, designer, tid).content)
    texts = json.loads(inside["strings.json"])
    texts["q_summary/label"] = "Resumé af hændelsen"
    texts["b_summary/title"] = "Resumé"
    inside["strings.json"] = json.dumps(texts).encode()
    came = import_(client, designer, pack(inside)).json()
    draft = client.get(f"{TEMPLATES}/{came['template']['id']}/draft", headers=designer).json()
    assert draft["content"]["form"][0]["questions"][0]["label"] == "Resumé af hændelsen"
    assert draft["content"]["layout"][1]["title"] == "Resumé"


def test_an_import_adds_library_entries_and_a_style_and_changes_none(client, designer,
                                                                     published, session) -> None:
    tid, _, _ = published
    style = client.post("/api/styles", headers=designer, json={"name": "Nordlys brand"}).json()
    client.put("/api/styles/company-default", headers=designer, json={"style_id": style["id"]})
    inside = unpack(export(client, designer, tid).content)
    styles = json.loads(inside["styles.json"])
    assert styles["company_default"]["name"] == "Nordlys brand"
    library = json.loads(inside["library.json"])
    library.append({"kind": "variable", "key": "support_phone", "description": "Service desk",
                    "value": {"value": "+45 70 20 30 40"}})
    library[0]["value"]["rows"]["high"] = ["Changed"]
    inside["library.json"] = json.dumps(library).encode()
    came = import_(client, designer, pack(inside)).json()
    assert came["library_added"] == ["vars.support_phone"]
    assert came["library_kept"] == ['lookup("severity")']
    assert (came["style_added"], came["style_kept"]) == (None, "Nordlys brand")
    table = client.get("/api/library", headers=designer).json()
    severity = next(e for e in table if e["key"] == "severity")
    assert severity["value"]["rows"]["high"] == ["High"]

    styles["company_default"]["name"] = "Fjordvik look"
    styles["company_default"]["content"]["colours"]["heading"] = "#1D3A5F"
    inside["styles.json"] = json.dumps(styles).encode()
    again = import_(client, designer, pack(inside)).json()
    assert again["style_added"] == "Fjordvik look"
    made = session.scalars(select(Style).where(Style.name == "Fjordvik look")).one()
    assert made.is_default is False
    assert session.scalars(select(LibraryEntry).where(
        LibraryEntry.key == "support_phone")).one().current == 1


def test_copy_for_translation(client, designer, published) -> None:
    tid, _, _ = published
    made = client.post(f"{TEMPLATES}/{tid}/copy", headers=designer,
                       json={"name": "Sikkerhedshændelse", "language": "da"})
    assert made.status_code == 201
    draft = client.get(f"{TEMPLATES}/{made.json()['id']}/draft", headers=designer).json()
    assert draft["content"]["settings"]["language"] == "da"


def test_only_template_builders_move_templates(client, person, published) -> None:
    tid, _, _ = published
    _, tech = person("tove", "technician")
    assert export(client, tech, tid).status_code == 403
    assert import_(client, tech, b"PK").status_code == 403


# Hostile files


def good(client, designer, tid) -> dict[str, bytes]:
    return unpack(export(client, designer, tid).content)


def refused(client, designer, data: bytes) -> str:
    answer = import_(client, designer, data)
    assert answer.status_code in (400, 422), answer.text
    return str(answer.json()["detail"])


def test_files_that_arent_template_files(client, designer, published) -> None:
    assert "isn't a Skjald template file" in refused(client, designer, b"not a zip at all")
    assert "no manifest" in refused(client, designer, pack({"settings.json": b"{}"}))
    inside = good(client, designer, published[0])
    manifest = json.loads(inside["manifest.json"])
    manifest["format_version"] = 99
    assert "can't read" in refused(client, designer, pack({**inside, "manifest.json":
                                                           json.dumps(manifest).encode()}))


@pytest.mark.parametrize("name", ["../evil.json", "/etc/passwd", "assets/../../x.png",
                                  "assets\\evil.png", "notes.txt", "assets/abc.png",
                                  "assets/sub/" + "a" * 64 + ".png"])
def test_paths_skjald_doesnt_write_are_refused(client, designer, published, name) -> None:
    inside = good(client, designer, published[0])
    assert "doesn't accept" in refused(client, designer, pack({**inside, name: b"{}"}))


def test_folders_and_links_are_refused(client, designer, published) -> None:
    inside = good(client, designer, published[0])
    for kind in ("folder", "link"):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for name, body in inside.items():
                archive.writestr(name, body)
            if kind == "folder":
                archive.writestr(zipfile.ZipInfo("assets/"), b"")
            else:
                link = zipfile.ZipInfo("assets/" + "b" * 64 + ".png")
                link.external_attr = (0o120777 << 16)
                archive.writestr(link, b"/etc/passwd")
        assert "doesn't accept" in refused(client, designer, out.getvalue())


def test_changed_or_extra_files_are_refused(client, designer, published) -> None:
    inside = good(client, designer, published[0])
    tampered = {**inside, "settings.json": inside["settings.json"] + b"\n"}
    assert "doesn't match its manifest" in refused(client, designer, pack(tampered, rehash=False))
    sha = "c" * 64
    extra = pack({**inside, f"assets/{sha}.png": picture()}, rehash=False)
    assert "don't match its manifest" in refused(client, designer, extra)
    missing = {k: v for k, v in inside.items() if k != "sample.json"}
    assert "no sample.json" in refused(client, designer, pack(missing))


def test_bombs_and_deep_data_are_refused(client, designer, published) -> None:
    inside = good(client, designer, published[0])
    bomb = pack({**inside, "assets/" + "d" * 64 + ".png": b"\0" * (5 * 1024 * 1024)})
    assert "expands" in refused(client, designer, bomb)
    deep: Any = []
    for _ in range(200):
        deep = [deep]
    nested = pack({**inside, "sample.json": json.dumps(deep).encode()})
    assert "nested too deeply" in refused(client, designer, nested)
    many = {**inside, **{f"assets/{i:064x}.png": picture() for i in range(310)}}
    assert "too many" in refused(client, designer, pack(many))
    with pytest.raises(files.TemplateFileRejected, match="12 MB"):
        files.read(b"PK" + b"\0" * (13 * 1024 * 1024))


def test_what_a_template_may_not_hold_is_refused(client, designer, published) -> None:
    inside = good(client, designer, published[0])
    rules = json.loads(inside["rules.json"])
    rules["b_attack/visible_when"] = 'answers.summary.matches(".*")'
    matching = pack({**inside, "rules.json": json.dumps(rules).encode()})
    assert "can't be imported" in refused(client, designer, matching)
    texts = json.loads(inside["strings.json"])
    texts["b_summary/title"] = "{{ system('rm -rf /') }}"
    assert "isn't a function Skjald knows" in refused(
        client, designer, pack({**inside, "strings.json": json.dumps(texts).encode()}))
    texts = json.loads(inside["strings.json"])
    texts["b_callout/content"] = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "x", "marks": [{"type": "link",
                                                  "attrs": {"href": "javascript:alert(1)"}}]}]}]}
    assert refused(client, designer, pack({**inside, "strings.json": json.dumps(texts).encode()}))
    layout = json.loads(inside["layout.json"])
    layout[0]["onclick"] = "x"
    assert "isn't valid" in refused(client, designer,
                                    pack({**inside, "layout.json": json.dumps(layout).encode()}))
    sha = next(n for n in inside if n.startswith("assets/"))
    assert "can't be used" in refused(client, designer, pack({**inside, sha: b"GIF89a fake"}))
