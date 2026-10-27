"""What a template version holds: one JSON document, checked here on every save.

A version is frozen as a whole once published, and the same document is what a
.skjald file carries, so it's one document rather than rows per question and block.
The structure is checked strictly (unknown keys refused, sizes capped); whether its
expressions and references make sense is app/templates/checks.py's job, so a draft
can be saved half-finished but not published.

- settings: who signs, review, the numbering prefix, delivery methods, styles.
- form: the technician's steps, each with its questions. A question has a fixed ID
  (answers follow it from version to version) and a variable name, its key, which
  expressions read as answers.<key> and which can be renamed.
- layout: the PDF's blocks, a tree: sections hold blocks, columns hold blocks.
  Blocks name questions by ID, so renaming a question changes no block.
- sample: answers for "Try it", by question ID; builder only.

Rules are expressions stored on what they act on (visible_when, required_when,
valid_when, a calculated value, a callout's tone, a section's repeat_for).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.templates.fields import FIELD_TYPES, KEY_PATTERN
from app.templates.text import check_doc

SCHEMA_VERSION = 1
MAX_CONTENT_BYTES = 2 * 1024 * 1024

Id = Annotated[str, StringConstraints(pattern=r"^[a-z]_[a-z0-9]{4,32}$")]
Key = Annotated[str, StringConstraints(pattern=KEY_PATTERN)]
# Expressions longer than 2,000 characters are refused when checked, with a message;
# this cap only stops absurd input.
Expr = Annotated[str, StringConstraints(max_length=10_000)]
Line = Annotated[str, StringConstraints(max_length=500)]
RichText = Annotated[dict[str, Any], AfterValidator(check_doc)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique(values: list[Any]) -> list[Any]:
    if len(values) != len(set(values)):
        raise ValueError("Each choice can be made once.")
    return values


class Settings(Strict):
    # Reports are numbered <prefix>-<year>-<n>, such as INC-2026-0142.
    prefix: str = Field(default="REP", pattern=r"^[A-Z]{2,6}$")
    language: Literal["da", "en"] = "en"
    signing: Literal["company", "technician", "technician_reviewer"] = "technician"
    review: Literal["mandatory", "optional"] = "optional"
    delivery: list[Literal["download", "email", "protected_pdf"]] = Field(
        default=["download"], min_length=1)
    styles: list[Literal["company", "customer"]] = Field(
        default=["company", "customer"], min_length=1)
    # Whether reports print on the customer's report background, if it has one.
    customer_background: bool = True

    _delivery = field_validator("delivery")(_unique)
    _styles = field_validator("styles")(_unique)


class Question(Strict):
    id: Id
    # The variable name; headings have none.
    key: Key | None = None
    type: str
    label: str = Field(min_length=1, max_length=300)
    help: str = Field(default="", max_length=2000)
    required: bool = False
    required_when: Expr | None = None
    visible_when: Expr | None = None
    default: Expr | None = None
    valid_when: Expr | None = None
    valid_message: str = Field(default="", max_length=300)
    # A calculated field's expression.
    value: Expr | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _by_type(self) -> Question:
        field_type = FIELD_TYPES.get(self.type)
        if field_type is None:
            raise ValueError(f"{self.type!r} isn't a field type.")
        self.settings = field_type.settings.model_validate(self.settings).model_dump()
        if not field_type.asks:
            self.key = None
        return self


class Step(Strict):
    id: Id
    title: str = Field(min_length=1, max_length=200)
    help: str = Field(default="", max_length=2000)
    visible_when: Expr | None = None
    questions: list[Question] = Field(default_factory=list, max_length=300)


# Layout blocks


class BlockBase(Strict):
    id: Id
    visible_when: Expr | None = None


class Fact(Strict):
    label: Line
    value: Line


class Cover(BlockBase):
    kind: Literal["cover"]
    title: Line = "{{report.title}}"
    subtitle: Line = ""
    facts: list[Fact] = Field(default_factory=list, max_length=12)
    show_logo: bool = True


class Contents(BlockBase):
    kind: Literal["toc"]
    title: Line = "Contents"
    depth: Literal[1, 2] = 1


class Section(BlockBase):
    kind: Literal["section"]
    title: str = Field(min_length=1, max_length=300)
    intro: RichText | None = None
    new_page: bool = True
    numbered: bool = True
    landscape: bool = False
    # A list (a repeating group's rows) to print the section once for each item of;
    # inside it, item is the current one.
    repeat_for: Expr | None = None
    blocks: list[Block] = Field(default_factory=list, max_length=300)


class Heading(BlockBase):
    kind: Literal["heading"]
    text: str = Field(min_length=1, max_length=300)


class TextBlock(BlockBase):
    kind: Literal["text"]
    content: RichText


class Answer(BlockBase):
    kind: Literal["answer"]
    question: Id | None = None
    show_label: bool = True


class Table(BlockBase):
    kind: Literal["table"]
    question: Id | None = None
    caption: Line = ""
    # Which columns, in what order; all of them when not set.
    columns: list[Key] | None = Field(default=None, max_length=20)
    empty_text: Line = "No rows."


class Image(BlockBase):
    kind: Literal["image"]
    source: Literal["template", "question"] = "template"
    asset: Sha256 | None = None
    question: Id | None = None
    caption: Line = ""
    width: Literal["full", "two_thirds", "half", "third"] = "full"


class Gallery(BlockBase):
    kind: Literal["gallery"]
    question: Id | None = None
    caption: Line = ""
    per_row: Literal[2, 3] = 2


class Callout(BlockBase):
    kind: Literal["callout"]
    tone: Literal["info", "note", "warning", "critical", "success", "custom"] = "info"
    # An expression giving a tone's name, such as "critical", for a tone set by the
    # answers; the tone above is used when it's not set.
    tone_rule: Expr | None = None
    colour: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    title: Line = ""
    content: RichText


class SeveritySummary(BlockBase):
    kind: Literal["severity_summary"]
    question: Id | None = None
    # The column of the repeating group that holds each row's severity.
    column: Key | None = None
    levels: list[Annotated[str, StringConstraints(min_length=1, max_length=50)]] = Field(
        default=["Critical", "High", "Medium", "Low"], min_length=1, max_length=8)
    caption: Line = ""


class Source(Strict):
    title: str = Field(min_length=1, max_length=500)
    link: str = Field(default="", max_length=2000)


class Sources(BlockBase):
    kind: Literal["sources"]
    intro: Line = ""
    items: list[Source] = Field(default_factory=list, max_length=100)
    # A repeating group whose rows are the technician's own sources.
    question: Id | None = None


class Signer(Strict):
    role: Literal["technician", "reviewer", "company"]
    label: Line
    style: Literal["handwritten", "stamp"] = "handwritten"


class Signatures(BlockBase):
    kind: Literal["signatures"]
    signers: list[Signer] = Field(min_length=1, max_length=4)
    layout: Literal["row", "stack"] = "row"
    show_date: bool = True


class Columns(BlockBase):
    kind: Literal["columns"]
    columns: list[list[Block]] = Field(min_length=2, max_length=3)


class PageBreak(BlockBase):
    kind: Literal["page_break"]


Block = Annotated[
    Cover | Contents | Section | Heading | TextBlock | Answer | Table | Image | Gallery
    | Callout | SeveritySummary | Sources | Signatures | Columns | PageBreak,
    Field(discriminator="kind"),
]

Section.model_rebuild()
Columns.model_rebuild()


class Sample(Strict):
    # Answers by question ID, for "Try it".
    answers: dict[str, Any] = Field(default_factory=dict)


class TemplateContent(Strict):
    schema_: Literal[1] = Field(default=1, alias="schema")
    settings: Settings = Field(default_factory=Settings)
    form: list[Step] = Field(default_factory=list, max_length=50)
    layout: list[Block] = Field(default_factory=list, max_length=300)
    sample: Sample = Field(default_factory=Sample)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def dump(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def starter_content() -> TemplateContent:
    """What a new template starts with: one step and one section."""
    return TemplateContent.model_validate({
        "form": [{"id": "s_start", "title": "Step 1", "questions": []}],
        "layout": [{"id": "b_start", "kind": "section", "title": "Summary", "new_page": False}],
    })
