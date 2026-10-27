"""Whether a template makes sense: the checks that decide whether it can be published.

A draft is saved whatever these say, so a designer can stop halfway; publishing
needs none. Each problem names the element (a step, question or block ID, or
"settings") and the field it's about, in words fit to show beside it. The builder
runs the same checks as the designer types (frontend/src/lib/templates/checks.ts);
shared/templates/checks.json holds both to the same problems, in the same order:
steps and their questions first, then loops among calculated values, then the
layout, depth first.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

import re2

from app.cel import Engine, ExpressionError
from app.cel.engine import human, unknown_name
from app.templates.content import (
    Answer,
    Block,
    Callout,
    Columns,
    Contents,
    Cover,
    Gallery,
    Image,
    Question,
    Section,
    SeveritySummary,
    Signatures,
    Sources,
    Table,
    TemplateContent,
    TextBlock,
)
from app.templates.content import Heading as HeadingBlock
from app.templates.fields import FIELD_TYPES
from app.templates.names import ITEM, declarations, question_names, questions
from app.templates.text import doc_expressions, interpolations

# Words CEL keeps for itself: answers.<key> can't be read with one of them as key.
RESERVED = frozenset({
    "true", "false", "null", "in", "as", "break", "const", "continue", "else", "for",
    "function", "if", "import", "let", "loop", "package", "namespace", "return", "var",
    "void", "while",
})
LISTS = ("repeating", "table")
ITEM_OUTSIDE = "item is only there inside a section repeated for each item."


@dataclass(frozen=True)
class Problem:
    element: str
    field: str
    message: str


def _fits(got: str, expected: str) -> bool:
    if got == "dyn" or got == expected:
        return True
    return expected == "list" and got.startswith("list<")


@dataclass
class _Checker:
    content: TemplateContent
    engine: Engine
    item_engine: Engine
    assets: Collection[str]
    problems: list[Problem] = field(default_factory=list)
    seen_ids: set[str] = field(default_factory=set)
    by_id: dict[str, Question] = field(default_factory=dict)

    def add(self, element: str, field_: str, message: str) -> None:
        self.problems.append(Problem(element, field_, message))

    def id(self, element: str) -> None:
        if element in self.seen_ids:
            self.add(element, "id", f"Another element already uses the ID {element}.")
        self.seen_ids.add(element)

    def message(self, error: ExpressionError, item: bool) -> str:
        if not item and error.message == unknown_name("item"):
            return ITEM_OUTSIDE
        return error.message

    def expr(self, element: str, field_: str, expr: str | None, expected: str | None,
             *, item: bool = False) -> None:
        """An expression that, when set, must work and give the expected type."""
        if expr is None:
            return
        if not expr.strip():
            self.add(element, field_, "Write the expression, or remove the rule.")
            return
        engine = self.item_engine if item else self.engine
        try:
            got = engine.check(expr)
        except ExpressionError as error:
            self.add(element, field_, self.message(error, item))
            return
        if expected is not None and not _fits(got, expected):
            self.add(element, field_,
                     f"This should give {human(expected)}, but gives {human(got)}.")

    def printed(self, element: str, field_: str, expr: str, *, item: bool) -> None:
        """An expression whose value is printed: anything but a list or a map."""
        if not expr:
            self.add(element, field_, "Write an expression between {{ and }}.")
            return
        engine = self.item_engine if item else self.engine
        try:
            got = engine.check(expr)
        except ExpressionError as error:
            self.add(element, field_, self.message(error, item))
            return
        if got.startswith(("list", "map")):
            self.add(element, field_, "This gives a list or a map, which can't be printed as "
                                      "it is: pick one item, or join a list of text with "
                                      ".join(\", \").")

    def text(self, element: str, field_: str, text: str, *, item: bool) -> None:
        for found in interpolations(text):
            if not found.closed:
                self.add(element, field_, "A {{ has no closing }}.")
            else:
                self.printed(element, field_, found.expr, item=item)

    def rich(self, element: str, field_: str, doc: dict[str, Any] | None, *, item: bool) -> None:
        if doc is None:
            return
        for expr in doc_expressions(doc):
            self.printed(element, field_, expr.strip(), item=item)

    # The form

    def question(self, q: Question, seen_keys: set[str]) -> None:
        self.id(q.id)
        field_type = FIELD_TYPES[q.type]
        if field_type.asks:
            if q.key is None:
                self.add(q.id, "key", "Give the question a variable name.")
            elif q.key in RESERVED:
                self.add(q.id, "key", f"{q.key} is a reserved word in expressions: "
                                      "choose another variable name.")
            elif q.key in seen_keys:
                self.add(q.id, "key", f"Another question already uses the variable name {q.key}.")
            if q.key is not None:
                seen_keys.add(q.key)
        self.settings(q)
        self.expr(q.id, "required_when", q.required_when, "bool")
        self.expr(q.id, "visible_when", q.visible_when, "bool")
        self.expr(q.id, "valid_when", q.valid_when, "bool")
        own = question_names(q).get(f"answers.{q.key}") if q.key else None
        if q.default is not None:
            if own is None or q.type == "calculated":
                self.add(q.id, "default", "This kind of question can't have a default.")
            else:
                self.expr(q.id, "default", q.default, own)
        if q.type == "calculated":
            if not (q.value or "").strip():
                self.add(q.id, "value", "Write the expression that works out this value.")
            else:
                self.expr(q.id, "value", q.value, own)
        elif q.value is not None:
            self.add(q.id, "value", "Only calculated values have an expression.")

    def settings(self, q: Question) -> None:
        s = q.settings
        if q.type in ("text", "serial") and s.get("pattern"):
            try:
                re2.compile(s["pattern"])
            except Exception:
                self.add(q.id, "settings.pattern",
                         "This pattern isn't a regular expression Skjald can use (RE2 syntax).")
        if q.type == "number" and s["min"] is not None and s["max"] is not None:
            if s["min"] > s["max"]:
                self.add(q.id, "settings.min", "The smallest value is larger than the largest.")
        if q.type == "multi_select" and None not in (s["min_selected"], s["max_selected"]):
            if s["min_selected"] > s["max_selected"]:
                self.add(q.id, "settings.min_selected",
                         "The fewest choices are more than the most.")
        if q.type in LISTS:
            keys = [c["key"] for c in s["columns"]]
            for key in sorted({k for k in keys if keys.count(k) > 1}):
                self.add(q.id, "settings.columns", f"Two columns use the variable name {key}.")
        if q.type == "table":
            rows = [r["key"] for r in s["rows"]]
            for key in sorted({k for k in rows if rows.count(k) > 1}):
                self.add(q.id, "settings.rows", f"Two rows use the variable name {key}.")
        if q.type == "repeating" and s["min_rows"] > s["max_rows"]:
            self.add(q.id, "settings.min_rows", "The fewest rows are more than the most.")

    def loops(self) -> None:
        """Calculated values that depend on themselves, through others or directly."""
        calculated = {q.key: q for q in questions(self.content)
                      if q.type == "calculated" and q.key and (q.value or "").strip()}
        depends: dict[str, list[str]] = {}
        for key, q in calculated.items():
            try:
                read = self.engine.references(q.value or "")
            except ExpressionError:
                read = []
            depends[key] = sorted({name.split(".")[1] for name in read
                                   if name.startswith("answers.")
                                   and name.split(".")[1] in calculated})
        for key, q in calculated.items():
            path = self._path_back(key, depends)
            if path:
                self.add(q.id, "value",
                         f"This value depends on itself: {' → '.join([key, *path])}.")

    @staticmethod
    def _path_back(start: str, depends: Mapping[str, list[str]]) -> list[str]:
        """The shortest way from start back to itself, if there is one."""
        queue: list[list[str]] = [[d] for d in depends.get(start, [])]
        visited: set[str] = set()
        while queue:
            path = queue.pop(0)
            if path[-1] == start:
                return path
            if path[-1] in visited:
                continue
            visited.add(path[-1])
            queue.extend([*path, d] for d in depends.get(path[-1], []))
        return []

    # The layout

    def chosen(self, element: str, question_id: str | None, missing: str) -> Question | None:
        if question_id is None:
            self.add(element, "question", missing)
            return None
        found = self.by_id.get(question_id)
        if found is None:
            self.add(element, "question", "The question this block prints was removed.")
        return found

    def is_list(self, element: str, q: Question) -> bool:
        if q.type not in LISTS:
            self.add(element, "question", f"“{q.label}” isn't a repeating group or table.")
            return False
        return True

    def column(self, element: str, field_: str, q: Question, key: str) -> None:
        if key not in [c["key"] for c in q.settings["columns"]]:
            self.add(element, field_, f"“{q.label}” has no column {key}.")

    def block(self, b: Block, *, item: bool) -> None:
        self.id(b.id)
        # A repeated section's own rule, title and intro are worked out for each item;
        # what it repeats for, outside them.
        outer = item
        item = item or (isinstance(b, Section) and b.repeat_for is not None)
        self.expr(b.id, "visible_when", b.visible_when, "bool", item=item)
        if isinstance(b, Cover):
            self.text(b.id, "title", b.title, item=item)
            self.text(b.id, "subtitle", b.subtitle, item=item)
            for i, fact in enumerate(b.facts):
                self.text(b.id, f"facts.{i}.label", fact.label, item=item)
                self.text(b.id, f"facts.{i}.value", fact.value, item=item)
        elif isinstance(b, Contents):
            self.text(b.id, "title", b.title, item=item)
        elif isinstance(b, Section):
            self.text(b.id, "title", b.title, item=item)
            self.rich(b.id, "intro", b.intro, item=item)
            self.expr(b.id, "repeat_for", b.repeat_for, "list", item=outer)
            for child in b.blocks:
                self.block(child, item=item)
        elif isinstance(b, HeadingBlock):
            self.text(b.id, "text", b.text, item=item)
        elif isinstance(b, TextBlock):
            self.rich(b.id, "content", b.content, item=item)
        elif isinstance(b, Answer):
            q = self.chosen(b.id, b.question, "Choose the question to print.")
            if q is not None and not FIELD_TYPES[q.type].asks:
                self.add(b.id, "question", "Headings have no answer to print.")
        elif isinstance(b, Table):
            q = self.chosen(b.id, b.question, "Choose the repeating group or table to print.")
            if q is not None and self.is_list(b.id, q):
                for key in b.columns or []:
                    self.column(b.id, "columns", q, key)
            self.text(b.id, "caption", b.caption, item=item)
            self.text(b.id, "empty_text", b.empty_text, item=item)
        elif isinstance(b, Image):
            if b.source == "template":
                if b.asset is None:
                    self.add(b.id, "asset", "Choose an image.")
                elif b.asset not in self.assets:
                    self.add(b.id, "asset", "The image file is missing: upload it again.")
            else:
                q = self.chosen(b.id, b.question, "Choose the photo question.")
                if q is not None and q.type != "photo":
                    self.add(b.id, "question", f"“{q.label}” isn't a photo question.")
            self.text(b.id, "caption", b.caption, item=item)
        elif isinstance(b, Gallery):
            q = self.chosen(b.id, b.question, "Choose the photo question.")
            if q is not None:
                if q.type != "photo":
                    self.add(b.id, "question", f"“{q.label}” isn't a photo question.")
                elif not q.settings["multiple"]:
                    self.add(b.id, "question", f"“{q.label}” takes one photo: let it take "
                                               "several to show a gallery.")
            self.text(b.id, "caption", b.caption, item=item)
        elif isinstance(b, Callout):
            self.expr(b.id, "tone_rule", b.tone_rule, "string", item=item)
            if b.tone == "custom" and b.colour is None:
                self.add(b.id, "colour", "Choose the custom colour.")
            self.text(b.id, "title", b.title, item=item)
            self.rich(b.id, "content", b.content, item=item)
        elif isinstance(b, SeveritySummary):
            q = self.chosen(b.id, b.question, "Choose the repeating group to count.")
            if q is not None and self.is_list(b.id, q):
                if b.column is None:
                    self.add(b.id, "column", "Choose the column that holds each row's severity.")
                else:
                    self.column(b.id, "column", q, b.column)
            self.text(b.id, "caption", b.caption, item=item)
        elif isinstance(b, Sources):
            self.text(b.id, "intro", b.intro, item=item)
            if b.question is not None:
                q = self.chosen(b.id, b.question, "")
                if q is not None:
                    self.is_list(b.id, q)
        elif isinstance(b, Signatures):
            for i, signer in enumerate(b.signers):
                self.text(b.id, f"signers.{i}.label", signer.label, item=item)
        elif isinstance(b, Columns):
            for column in b.columns:
                for child in column:
                    self.block(child, item=item)


def check(
    content: TemplateContent,
    *,
    library: Mapping[str, str] | None = None,
    assets: Collection[str] = (),
    timezone: str = "Europe/Copenhagen",
) -> list[Problem]:
    """Every problem in the template, in the order the builder shows them."""
    names = declarations(content, library)
    language = content.settings.language
    checker = _Checker(
        content=content,
        engine=Engine(names, timezone=timezone, language=language),
        item_engine=Engine(names | ITEM, timezone=timezone, language=language),
        assets=assets,
        by_id={q.id: q for q in questions(content)},
    )
    seen_keys: set[str] = set()
    for step in content.form:
        checker.id(step.id)
        checker.expr(step.id, "visible_when", step.visible_when, "bool")
        for q in step.questions:
            checker.question(q, seen_keys)
    checker.loops()
    for b in content.layout:
        checker.block(b, item=False)
    return checker.problems
