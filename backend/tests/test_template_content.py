"""What a template holds, and whether it makes sense.

The examples in shared/templates/ run here and in the browser's tests
(frontend/src/lib/templates/checks.test.ts), so both find the same problems.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.templates.changes import changes
from app.templates.checks import check
from app.templates.content import (
    MAX_BLOCK_DEPTH,
    MAX_BLOCKS,
    MAX_CONTENT_BYTES,
    MAX_QUESTIONS,
    Section,
    Step,
    TemplateContent,
    starter_content,
)
from app.templates.names import CONTEXT, declarations
from app.templates.secrets import printed
from app.templates.text import RichTextError, check_doc, doc_text, interpolations

SHARED = Path(__file__).resolve().parents[2] / "shared" / "templates"
INCIDENT = json.loads((SHARED / "incident.json").read_text())
CHECKS = json.loads((SHARED / "checks.json").read_text())
NAMES = json.loads((SHARED / "names.json").read_text())
CONTEXT_ROOTS = {group["name"] for group in NAMES["groups"]}


def content(**parts: Any) -> TemplateContent:
    return TemplateContent.model_validate(parts)


def test_the_sample_template_has_no_problems() -> None:
    incident = TemplateContent.model_validate(INCIDENT)
    assert check(incident) == []
    assert incident.dump() == TemplateContent.model_validate(incident.dump()).dump()


@pytest.mark.parametrize("case", CHECKS["cases"], ids=lambda c: c["name"])
def test_shared_checks(case: dict[str, Any]) -> None:
    parsed = TemplateContent.model_validate(case["content"])
    found = check(parsed, library=case.get("library"), assets=case.get("assets", ()))
    assert [{"element": p.element, "field": p.field, "message": p.message}
            for p in found] == case["problems"]
    own = {k: v for k, v in declarations(parsed, case.get("library")).items()
           if k.split(".")[0] not in CONTEXT_ROOTS}
    assert own == case["answers"]


def test_context_names_follow_the_shared_list() -> None:
    shared = {n["name"]: n["type"] for group in NAMES["groups"] for n in group["names"]}
    assert shared == CONTEXT


def test_a_new_template_starts_with_a_step_and_a_section() -> None:
    starter = starter_content()
    assert [s.title for s in starter.form] == ["Details"]
    assert [b.kind for b in starter.layout] == ["section"]
    assert check(starter) == []


@pytest.mark.parametrize(("parts", "message"), [
    ({"surprise": 1}, "Extra inputs are not permitted"),
    ({"form": [{"id": "s_main1", "title": "Step", "questions": [
        {"id": "q_x123", "key": "x", "type": "teleport", "label": "X"}]}]}, "isn't a field type"),
    ({"form": [{"id": "s_main1", "title": "Step", "questions": [
        {"id": "q_x123", "key": "Bad Key", "type": "text", "label": "X"}]}]}, "pattern"),
    ({"form": [{"id": "s_main1", "title": "Step", "questions": [
        {"id": "q_x123", "key": "x", "type": "dropdown", "label": "X", "settings": {
            "options": [{"value": "a", "label": "A"}, {"value": "a", "label": "B"}]}}]}]},
     "Two options have the same value"),
    ({"form": [{"id": "s_main1", "title": "Step", "questions": [
        {"id": "q_x123", "key": "x", "type": "number", "label": "X",
         "settings": {"whole": True, "colour": "red"}}]}]}, "Extra inputs"),
    ({"form": [{"id": "s_main1", "title": "Step", "questions": [
        {"id": "q_x123", "key": "x", "type": "person", "label": "X",
         "settings": {"who": "strangers"}}]}]}, "Input should be"),
    ({"layout": [{"id": "b_main1", "kind": "marquee"}]}, "does not match any of the expected"),
    ({"layout": [{"id": "B_MAIN", "kind": "page_break"}]}, "pattern"),
    ({"layout": [{"id": "b_switch", "kind": "switch", "value": "answers.seen",
                  "cases": [{"match": True}]}]}, "Input should be a valid"),
    ({"layout": [{"id": "b_switch", "kind": "switch",
                  "cases": [{"match": 1.5}]}]}, "Input should be a valid"),
    ({"layout": [{"id": "b_switch", "kind": "switch",
                  "cases": [{"match": "a", "label": "A"}]}]}, "Extra inputs"),
    ({"settings": {"prefix": "inc"}}, "pattern"),
    ({"settings": {"delivery": ["email", "email"]}}, "Each choice can be made once"),
    ({"layout": [{"id": "b_text1", "kind": "text", "content": {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "x", "marks": [
            {"type": "link", "attrs": {"href": "javascript:alert(1)"}}]}]}]}}]},
     "Links must start with"),
])
def test_structure_is_checked_strictly(parts: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TemplateContent.model_validate(parts)


def test_a_template_carries_made_with_skjald_unless_it_says_not() -> None:
    assert content().settings.made_with_skjald is True
    without = content(settings={"made_with_skjald": False})
    assert without.dump()["settings"]["made_with_skjald"] is False


def test_settings_are_filled_in_with_their_defaults() -> None:
    parsed = content(form=[{"id": "s_main1", "title": "Step", "questions": [
        {"id": "q_x123", "key": "x", "type": "number", "label": "X"},
        {"id": "q_head", "key": "ignored", "type": "heading", "label": "Section"}]}])
    number, heading = parsed.form[0].questions
    assert number.settings == {"whole": False, "min": None, "max": None, "decimals": 1, "unit": ""}
    assert heading.key is None


def para(*inline: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(inline)}]}


@pytest.mark.parametrize("doc", [
    {"type": "doc", "content": [{"type": "script", "content": []}]},
    {"type": "doc", "content": [{"type": "paragraph", "attrs": {"style": "x"}}]},
    para({"type": "text", "text": "x", "marks": [{"type": "highlight"}]}),
    para({"type": "text", "text": "x", "marks": [{"type": "link", "attrs": {
        "href": "https://x.example", "target": "_blank"}}]}),
    para({"type": "image", "attrs": {"src": "https://x.example/a.png"}}),
    para({"type": "text", "text": ""}),
    {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 1}, "content": []}]},
    {"type": "doc", "content": [{"type": "bulletList", "content": []}]},
    {"type": "doc", "content": [{"type": "bulletList", "content": [
        {"type": "listItem", "content": [{"type": "bulletList", "content": []}]}]}]},
    {"type": "doc", "content": [{"type": "orderedList", "attrs": {"start": 0}, "content": [
        {"type": "listItem", "content": [{"type": "paragraph"}]}]}]},
    para({"type": "variable", "attrs": {"expr": "answers.x", "html": "<b>"}}),
])
def test_rich_text_holds_only_what_is_printed(doc: dict[str, Any]) -> None:
    with pytest.raises(RichTextError):
        check_doc(doc)


def test_rich_text_lists_and_words() -> None:
    doc = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Steps"}]},
        {"type": "orderedList", "attrs": {"start": 3, "type": None}, "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Call ", "marks": [{"type": "bold"}]},
                    {"type": "variable", "attrs": {"expr": "vars.phone"}},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "now", "marks": [
                        {"type": "link", "attrs": {"href": "mailto:a@b.example"}}]}]},
                {"type": "bulletList", "content": [{"type": "listItem", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "{{x}}"}]}]}]},
            ]}]},
    ]}
    assert check_doc(doc) is doc
    assert doc_text(doc) == "Steps\nCall \nnow\n{{x}}"


def test_expressions_in_text() -> None:
    found = interpolations('Hi {{ author.first_name }}, {{ {"a": {"b": "}}"}}["a"]["b"] }} {{x')
    assert [(f.expr, f.closed) for f in found] == [
        ("author.first_name", True), ('{"a": {"b": "}}"}}["a"]["b"]', True), ("x", False)]
    assert interpolations("No {single} braces") == []


def test_changes_by_id() -> None:
    old = TemplateContent.model_validate(INCIDENT)
    new_raw = json.loads(json.dumps(INCIDENT))
    new_raw["form"][0]["questions"][2]["label"] = "Highest CVSS base score"
    new_raw["form"][0]["questions"][2]["key"] = "cvss_score"
    del new_raw["form"][1]["questions"][2]
    new_raw["form"][1]["questions"].append(
        {"id": "q_hosts", "key": "hosts", "type": "text", "label": "Hosts"})
    new_raw["settings"]["prefix"] = "SEC"
    new_raw["layout"][1]["blocks"][1]["tone"] = "critical"
    found = changes(old, TemplateContent.model_validate(new_raw))
    assert [(c.id, c.parts) for c in found.questions_changed] == [("q_cvss", ["key", "label"])]
    assert [q.id for q in found.questions_removed] == ["q_evidence"]
    assert [q.id for q in found.questions_added] == ["q_hosts"]
    assert [(b.id, b.parts) for b in found.blocks_changed] == [("b_callout", ["tone"])]
    assert found.settings_changed == ["prefix"]
    assert found.any
    assert not changes(old, old).any
    assert not found.steps_changed and not found.questions_moved and not found.blocks_moved
    assert found.sample_changed is False


def test_changes_to_steps_moves_and_sample_answers_are_said() -> None:
    old = TemplateContent.model_validate(INCIDENT)

    def changed(edit: Any) -> Any:
        raw = json.loads(json.dumps(INCIDENT))
        edit(raw)
        found = changes(old, TemplateContent.model_validate(raw))
        assert found.any
        return found

    # A step put in another's place, with a rule of its own, and one renamed and hidden.
    def steps(raw: dict[str, Any]) -> None:
        raw["form"][1] = {"id": "s_extra1", "title": "Extra", "visible_when": "answers.found",
                          "questions": raw["form"][1]["questions"]}
        raw["form"][2]["title"] = "Handover"
        raw["form"][2]["visible_when"] = "false"
    found = changed(steps)
    assert [(s.id, s.label) for s in found.steps_added] == [("s_extra1", "Extra")]
    assert [(s.id, s.label) for s in found.steps_removed] == [("s_attack", "The attack")]
    assert [(s.id, s.label, s.parts) for s in found.steps_changed] == [
        ("s_actions", "Handover", ["title", "visible_when"])]
    assert [q.id for q in found.questions_moved] == ["q_found", "q_attackers", "q_evidence"]
    assert not found.questions_changed and not found.steps_moved

    # A question moved to another step, and steps put in another order.
    def moves(raw: dict[str, Any]) -> None:
        raw["form"][2]["questions"].insert(1, raw["form"][0]["questions"].pop(2))
        raw["form"].insert(0, raw["form"].pop(2))
    found = changed(moves)
    assert [(q.id, q.label) for q in found.questions_moved] == [("q_cvss", "Highest CVSS score")]
    assert [s.id for s in found.steps_moved] == ["s_actions"]
    assert not (found.questions_changed or found.questions_added or found.questions_removed)

    # One question moved up past four others is one question moved.
    def reorder(raw: dict[str, Any]) -> None:
        raw["form"][0]["questions"].insert(0, raw["form"][0]["questions"].pop(4))
    assert [q.id for q in changed(reorder).questions_moved] == ["q_deadline"]

    # A block moved to another section, and two blocks changing places.
    def blocks(raw: dict[str, Any]) -> None:
        raw["layout"][3]["blocks"].append(raw["layout"][1]["blocks"].pop(1))
        raw["layout"][2]["blocks"].reverse()
    found = changed(blocks)
    assert sorted(b.id for b in found.blocks_moved) in (
        ["b_callout", "b_evidence"], ["b_callout", "b_table"])
    assert not (found.blocks_changed or found.blocks_added or found.blocks_removed)

    # A question added among others moves none of them; sample answers are said.
    def added(raw: dict[str, Any]) -> None:
        raw["form"][0]["questions"].insert(
            1, {"id": "q_hosts", "key": "hosts", "type": "text", "label": "Hosts"})
        raw["sample"]["answers"]["q_summary"] = "Something else"
    found = changed(added)
    assert [q.id for q in found.questions_added] == ["q_hosts"]
    assert not found.questions_moved and found.sample_changed is True


def test_changes_inside_a_switch_are_the_blocks_own() -> None:
    def layout(match: str, text: str) -> TemplateContent:
        return content(layout=[{"id": "b_switch", "kind": "switch", "value": "customer.language",
                                "cases": [{"match": match, "blocks": [
                                    {"id": "b_head1", "kind": "heading", "text": text}]}],
                                "otherwise": []}])

    found = changes(layout("da", "Hej"), layout("en", "Hello"))
    assert [(b.id, b.parts) for b in found.blocks_changed] == [
        ("b_switch", ["cases"]), ("b_head1", ["text"])]
    # The case was renamed, not the heading moved; nor when a case is put before it.
    assert not found.blocks_moved
    assert not changes(layout("da", "Hej"), layout("da", "Hej")).any
    before = layout("da", "Hej")
    after = content(layout=[{
        "id": "b_switch", "kind": "switch", "value": "customer.language",
        "cases": [{"match": "sv", "blocks": []},
                  {"match": "da", "blocks": [{"id": "b_head1", "kind": "heading", "text": "Hej"}]}],
        "otherwise": []}])
    assert not changes(before, after).blocks_moved
    moved = content(layout=[{
        "id": "b_switch", "kind": "switch", "value": "customer.language",
        "cases": [{"match": "da", "blocks": []}],
        "otherwise": [{"id": "b_head1", "kind": "heading", "text": "Hej"}]}])
    assert [b.id for b in changes(before, moved).blocks_moved] == ["b_head1"]


SECRETS = json.loads((SHARED / "secrets.json").read_text())


@pytest.mark.parametrize("case", SECRETS["cases"], ids=lambda c: c["printed"] or "empty")
def test_secrets_print_partly(case: dict[str, str]) -> None:
    assert printed(case["secret"]) == case["printed"]
    assert printed(case["secret"], "omit") == ""


def test_the_size_limits_are_the_ones_the_builder_checks() -> None:
    """shared/templates/limits.json holds the server and the builder to the same numbers."""
    limits = json.loads((SHARED / "limits.json").read_text())
    assert limits["questions"] == MAX_QUESTIONS
    assert limits["blocks"] == MAX_BLOCKS
    assert limits["block_depth"] == MAX_BLOCK_DEPTH
    assert limits["bytes"] == MAX_CONTENT_BYTES

    def longest(model: Any, field: str) -> int:
        return next(m.max_length for m in model.model_fields[field].metadata
                    if getattr(m, "max_length", None) is not None)

    assert limits["in_one_list"] == longest(Section, "blocks") == longest(Step, "questions")
    assert limits["steps"] == longest(TemplateContent, "form")

