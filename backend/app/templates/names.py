"""The names a template's expressions can read, and their types.

Besides the template's own answers there are the report's context (company,
customer, site, contact, project, report, author, reviewer: shared/templates/
names.json, which a test holds this copy to) and the shared library (vars.<name>,
text.<name>). The browser works the same names out (frontend/src/lib/templates/
names.ts) as the designer edits; the shared examples hold both to one answer.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.templates.content import Question, TemplateContent
from app.templates.fields import FIELD_TYPES

CONTEXT: dict[str, str] = {
    "company.name": "string",
    "customer.name": "string",
    "customer.cvr": "string",
    "customer.address": "string",
    "customer.language": "string",
    "site.name": "string",
    "site.address": "string",
    "contact.name": "string",
    "contact.role": "string",
    "contact.email": "string",
    "contact.phone": "string",
    "project.name": "string",
    "project.number": "string",
    "project.start_date": "timestamp",
    "project.end_date": "timestamp",
    "project.classification": "string",
    "report.title": "string",
    "report.number": "string",
    "report.revision": "int",
    "report.date": "timestamp",
    **{f"{person}.{part}": "string"
       for person in ("author", "reviewer")
       for part in ("display_name", "first_name", "middle_name", "last_name", "job_title",
                    "department", "email", "phone")},
}

# Inside a section repeated for each item of a list.
ITEM = {"item": "map<string, dyn>"}


def question_names(question: Question) -> dict[str, str]:
    """The names one question gives expressions."""
    if question.key is None:
        return {}
    field_type = FIELD_TYPES[question.type]
    settings = field_type.settings.model_validate(question.settings)
    return {f"answers.{question.key}{suffix}": type_
            for suffix, type_ in field_type.names(settings).items()}


def questions(content: TemplateContent) -> list[Question]:
    return [q for step in content.form for q in step.questions]


def declarations(
    content: TemplateContent, library: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Every name the template's expressions can read, with its type.

    library: the shared library's names (vars.<name>, text.<name>) and their types.
    When two questions share a variable name, the first one's names count; the
    duplicate is a problem of its own.
    """
    names = dict(CONTEXT)
    for question in questions(content):
        for name, type_ in question_names(question).items():
            names.setdefault(name, type_)
    names.update(library or {})
    return dict(sorted(names.items()))
