"""The reports API: a project's reports, their answers and who has them checked out.

Everyone who may open a project reads its reports. Writing them is for the
project's technicians (its responsible technician and those on its team as
technicians) and Administrators; an archived project's reports are read-only.
Whoever changes a report checks it out first, one step of its form or all of it,
and Administrators can end anyone's checkout.

A report's title and answers are sealed with the customer's key. A secret answer
leaves only as whether it's filled in and how the PDF prints it; seeing it takes a
fresh confirmation with multifactor, and each look is logged. Opening a report is
logged too, and the audit log names reports by number, never by title.

The browser works the form out as the technician types; what counts is the
server's own verdict (app/reports/form.py), given with the report and on request.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock, jobs, mail
from app.auth.dependencies import DB, FullSession, client_ip, require, require_step_up
from app.auth.sessions import UserSession
from app.branding import company_timezone
from app.cel.library import Table
from app.custom_fields import custom_names
from app.customer_routes import sites_of
from app.customers import Customer, Keyring
from app.library.routes import current_entries
from app.library.values import library_names, library_values
from app.notices import SIGN_OFF
from app.project_routes import visible_project
from app.projects import Project, ProjectMember, site_ids_of, team_ids
from app.reports.answers import MAX_ANSWERS_BYTES, PersonFinder, Refused, merge, shown
from app.reports.context import person_parts, report_context
from app.reports.form import evaluate
from app.reports.models import (
    DRAFT,
    STALE_HOURS_LIMITS,
    Report,
    ReportCheckout,
    next_number,
    set_stale_hours,
    stale_hours,
)
from app.roles import Capability, Role, UserRole, can, roles_of
from app.settings import settings
from app.setup import company_name
from app.templates.content import Id, TemplateContent
from app.templates.models import Template, TemplateAsset, TemplateVersion
from app.templates.names import questions
from app.users import User

router = APIRouter()

Administrator = Annotated[UserSession, Depends(require(Capability.ADMINISTER))]
Breaker = Annotated[UserSession, Depends(require(Capability.BREAK_CHECKOUTS))]

NOT_FOUND = "That report doesn't exist."
LOG_SAVES_EVERY = timedelta(minutes=10)
# Opening a report is logged; opening it again within this time is the same sitting
# (an open report is fetched again whenever someone else saves) and isn't logged again.
LOG_VIEWS_EVERY = timedelta(minutes=10)
# (user ID, report ID) -> when their view was last logged. Kept in this process only:
# after a restart, or in another worker, the next view is simply logged again.
_VIEWS_LOGGED: dict[tuple[int, int], datetime] = {}
_VIEWS_REMEMBERED = 10_000
# How long a revealed secret stays on the screen.
REVEAL_SECONDS = 30
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Named(BaseModel):
    id: int
    name: str


class TemplateRef(BaseModel):
    id: int
    name: str
    version: int


class CheckoutOut(BaseModel):
    id: int
    # The step of the form it holds; none for the whole report.
    step: str | None
    holder: Named
    taken_at: datetime
    active_at: datetime
    stale: bool
    mine: bool


class ReportSummary(BaseModel):
    id: int
    number: str
    title: str
    status: str
    revision: int
    template: TemplateRef
    author: Named | None
    created_at: datetime
    updated_at: datetime
    checkouts: list[CheckoutOut]


class ReportList(BaseModel):
    reports: list[ReportSummary]
    may_create: bool


class TemplateChoice(BaseModel):
    id: int
    name: str
    description: str
    version: int
    prefix: str


class ReportIn(BaseModel):
    template_id: int
    # The template's name unless one is given.
    title: str | None = Field(default=None, max_length=200)
    site_id: int | None = None


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    site_id: int | None = None


class AnswersIn(BaseModel):
    # By question ID. An empty answer (null, "", []) clears it.
    answers: dict[str, Any] = Field(max_length=500)


class Saved(BaseModel):
    saves: int
    updated_at: datetime
    # The answers that changed, as they're kept; and the ones no longer answered.
    answers: dict[str, Any]
    forgotten: list[str]


class CheckoutIn(BaseModel):
    step: Id | None = None


class DiscardIn(BaseModel):
    confirm_number: str = Field(max_length=30)


class MissingOut(BaseModel):
    step: str
    question: str
    message: str


class ErrorOut(BaseModel):
    element: str
    message: str


class StateOut(BaseModel):
    """The server's verdict on the form: what it hides and requires, what fails its
    rule, and everything that keeps the report from going for review."""

    hidden: list[str]
    required: list[str]
    invalid: dict[str, str]
    missing: list[MissingOut]
    errors: list[ErrorOut]


class Activity(BaseModel):
    """What changes while a report is open: who holds what, and how often it was saved."""

    status: str
    saves: int
    updated_at: datetime
    checkouts: list[CheckoutOut]


class ProjectRef(BaseModel):
    id: int
    number: str
    name: str
    classification: str
    archived: bool


class TemplateOut(TemplateRef):
    content: dict[str, Any]


class TableOut(BaseModel):
    columns: list[str]
    rows: dict[str, list[str]]


class LibraryOut(BaseModel):
    names: dict[str, str]
    values: dict[str, Any]
    tables: dict[str, TableOut]


class PersonOut(BaseModel):
    id: str
    technician: bool
    reviewer: bool
    on_team: bool
    display_name: str
    first_name: str
    middle_name: str
    last_name: str
    job_title: str
    department: str
    company: str
    email: str
    phone: str


class AssetRef(BaseModel):
    url: str
    width: int
    height: int


class ReportDetail(BaseModel):
    id: int
    number: str
    title: str
    status: str
    revision: int
    project: ProjectRef
    customer: Named
    template: TemplateOut
    site: Named | None
    sites: list[Named]
    author: Named | None
    created_at: datetime
    updated_at: datetime
    answers: dict[str, Any]
    saves: int
    context: dict[str, Any]
    library: LibraryOut
    people: list[PersonOut]
    assets: dict[str, AssetRef]
    time_zone: str
    checkouts: list[CheckoutOut]
    may_edit: bool
    may_reveal: bool
    may_break: bool
    may_discard: bool
    state: StateOut


class Revealed(BaseModel):
    value: str
    seconds: int


class ReportSettings(BaseModel):
    checkout_stale_hours: int = Field(ge=STALE_HOURS_LIMITS[0], le=STALE_HOURS_LIMITS[1])


def _log(
    db: Session, request: Request, record: UserSession, action: str, report: Report,
    details: dict[str, object] | None = None,
) -> None:
    audit.append(
        db, action, actor_id=record.user.id, actor_name=record.user.username,
        target_type="report", target_id=str(report.id), ip=client_ip(request),
        details={"number": report.number, **(details or {})},
    )


# Who may do what


def writes(db: Session, user_id: int, roles: set[Role], project: Project) -> bool:
    """Whether someone writes this project's reports: an Administrator, or a
    technician who is on the project as one."""
    if not can(roles, Capability.FILL_IN_REPORTS):
        return False
    if can(roles, Capability.ADMINISTER) or project.responsible_id == user_id:
        return True
    member = db.get(ProjectMember, (project.id, user_id))
    return member is not None and member.as_role == Role.TECHNICIAN.value


def _reviews(db: Session, user_id: int, roles: set[Role], project: Project) -> bool:
    """Whether someone is on the project to review its reports."""
    if not can(roles, Capability.REVIEW_AND_COUNTERSIGN):
        return False
    if project.reviewer_id == user_id:
        return True
    member = db.get(ProjectMember, (project.id, user_id))
    return member is not None and member.as_role == Role.REVIEWER.value


def _open(db: Session, request: Request, record: UserSession, report_id: int
          ) -> tuple[Report, Project, Customer]:
    """The report with its project and customer, for someone who may read it. One
    they may not see answers like one that doesn't exist."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    try:
        project, customer = visible_project(db, request, record, report.project_id)
    except HTTPException:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return report, project, customer


def _writable_project(db: Session, request: Request, record: UserSession, project_id: int
                      ) -> tuple[Project, Customer]:
    project, customer = visible_project(db, request, record, project_id)
    if not writes(db, record.user_id, roles_of(db, record.user_id), project):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only the project's technicians write its reports.")
    if project.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Archived projects are read-only.")
    return project, customer


def _writable(db: Session, request: Request, record: UserSession, report_id: int
              ) -> tuple[Report, Project, Customer]:
    report, _, _ = _open(db, request, record, report_id)
    project, customer = _writable_project(db, request, record, report.project_id)
    if report.status != DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft can be changed.")
    return report, project, customer


# What's kept


def _title(keyring: Keyring, customer: Customer, report: Report) -> str:
    opened = keyring.sealer(customer).open("report-title", report.id, report.sealed_title)
    return str(opened["title"])


def _answers(keyring: Keyring, customer: Customer, report: Report) -> dict[str, Any]:
    opened = keyring.sealer(customer).open("report-answers", report.id, report.sealed_answers)
    answers: dict[str, Any] = opened["answers"]
    return answers


def _seal_title(keyring: Keyring, customer: Customer, report: Report, title: str) -> None:
    report.sealed_title = keyring.sealer(customer).seal("report-title", report.id,
                                                        {"title": title})


def _seal_answers(keyring: Keyring, customer: Customer, report: Report,
                  answers: Mapping[str, Any]) -> None:
    if len(json.dumps(answers, separators=(",", ":"))) > MAX_ANSWERS_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            "This report holds more than a report can: shorten its longest "
                            "answers.")
    report.sealed_answers = keyring.sealer(customer).seal("report-answers", report.id,
                                                          {"answers": dict(answers)})


def _pinned(db: Session, report: Report) -> tuple[Template, TemplateVersion, TemplateContent]:
    version = db.get(TemplateVersion, report.template_version_id)
    assert version is not None and version.number is not None
    template = db.get(Template, version.template_id)
    assert template is not None
    return template, version, TemplateContent.model_validate_json(version.content)


def _library(db: Session) -> tuple[dict[str, str], dict[str, Any], dict[str, Table]]:
    """The shared library and the custom fields as a report reads them: what was taken
    out or archived since its template was published is still there, as it last was."""
    entries = current_entries(db, removed=True)
    names = {**library_names((entry for entry, _ in entries), removed=True),
             **custom_names(db, archived=True)}
    values, tables = library_values(entries, removed=True)
    return names, dict(values), tables


def _named(db: Session, user_id: int | None) -> Named | None:
    user = db.get(User, user_id) if user_id else None
    return Named(id=user.id, name=user.display_name) if user else None


# Checkouts


def _held(db: Session, report_id: int) -> list[ReportCheckout]:
    return list(db.scalars(select(ReportCheckout).where(ReportCheckout.report_id == report_id)
                           .order_by(ReportCheckout.id)))


def _checkouts_out(db: Session, record: UserSession, held: list[ReportCheckout]
                   ) -> list[CheckoutOut]:
    if not held:
        return []
    names = {user_id: name for user_id, name in db.execute(
        select(User.id, User.display_name).where(User.id.in_({c.user_id for c in held})))}
    limit = timedelta(hours=stale_hours(db))
    now = clock.utcnow()
    return [CheckoutOut(id=c.id, step=c.step_id,
                        holder=Named(id=c.user_id, name=names.get(c.user_id, "Someone")),
                        taken_at=c.taken_at, active_at=c.active_at,
                        stale=now - c.active_at > limit, mine=c.user_id == record.user_id)
            for c in held]


def _covers(held: list[ReportCheckout], user_id: int, step_id: str) -> bool:
    return any(c.user_id == user_id and c.step_id in (None, step_id) for c in held)


def _what(checkout: ReportCheckout, content: TemplateContent) -> str:
    if checkout.step_id is None:
        return "the whole report"
    title = next((s.title for s in content.form if s.id == checkout.step_id), "")
    return f"the step “{title}”" if title else "a step"


# People


def _asked(content: TemplateContent) -> set[str]:
    """Whom the template's person questions offer: technicians, reviewers, team, everyone."""
    return {str(q.settings.get("who", "technicians"))
            for q in questions(content) if q.type == "person"}


def _may_be_picked(who: str, *, technician: bool, reviewer: bool, on_team: bool) -> bool:
    return {"technicians": technician, "reviewers": reviewer, "team": on_team}.get(who, True)


def _people(db: Session, project: Project, asked: set[str]) -> list[PersonOut]:
    """The people the template's person questions can pick, and nobody else: active
    accounts, with the business details reports print."""
    if not asked:
        return []
    team = team_ids(db, project)
    held: dict[int, set[str]] = {}
    for user_id, role in db.execute(select(UserRole.user_id, UserRole.role)):
        held.setdefault(user_id, set()).add(role)
    company = company_name(db) or ""
    people = []
    users = db.scalars(select(User).where(User.is_active.is_(True))
                       .order_by(User.display_name, User.id))
    for user in users:
        flags = {"technician": Role.TECHNICIAN.value in held.get(user.id, set()),
                 "reviewer": Role.REVIEWER.value in held.get(user.id, set()),
                 "on_team": user.id in team}
        if any(_may_be_picked(who, **flags) for who in asked):
            people.append(PersonOut.model_validate(
                {"id": str(user.id), **flags, **person_parts(user, company)}))
    return people


def _person_finder(db: Session, project: Project) -> PersonFinder:
    def find(who: str, picked: str) -> dict[str, str] | None:
        # An ID is a short run of digits; anything else names nobody.
        known = picked.isascii() and picked.isdigit() and len(picked) <= 10
        user = db.get(User, int(picked)) if known else None
        if user is None or not user.is_active:
            return None
        roles = roles_of(db, user.id)
        if not _may_be_picked(who, technician=Role.TECHNICIAN in roles,
                              reviewer=Role.REVIEWER in roles,
                              on_team=user.id in team_ids(db, project)):
            return None
        return person_parts(user, company_name(db) or "")

    return find


# What's given out


def _template_ref(template: Template, version: TemplateVersion) -> TemplateRef:
    assert version.number is not None
    return TemplateRef(id=template.id, name=template.name, version=version.number)


def _summary(db: Session, record: UserSession, keyring: Keyring, customer: Customer,
             report: Report) -> ReportSummary:
    version = db.get(TemplateVersion, report.template_version_id)
    assert version is not None
    template = db.get(Template, version.template_id)
    assert template is not None
    return ReportSummary(
        id=report.id, number=report.number, title=_title(keyring, customer, report),
        status=report.status, revision=report.revision,
        template=_template_ref(template, version), author=_named(db, report.author_id),
        created_at=report.created_at, updated_at=report.updated_at,
        checkouts=_checkouts_out(db, record, _held(db, report.id)),
    )


def _state(content: TemplateContent, answers: Mapping[str, Any], context: Mapping[str, Any],
           library: tuple[dict[str, str], dict[str, Any], dict[str, Table]], zone: str
           ) -> StateOut:
    names, values, tables = library
    state = evaluate(content, answers, context, library_names=names, library_values=values,
                     tables=tables, timezone=zone)
    return StateOut(
        hidden=state.hidden, required=state.required, invalid=state.invalid,
        missing=[MissingOut(step=m.step, question=m.question, message=m.message)
                 for m in state.missing],
        errors=[ErrorOut(element=element, message=message) for element, message in state.errors],
    )


def _detail(db: Session, record: UserSession, report: Report, project: Project,
            customer: Customer) -> ReportDetail:
    keyring = Keyring()
    sealer = keyring.sealer(customer)
    template, version, content = _pinned(db, report)
    title = _title(keyring, customer, report)
    answers = _answers(keyring, customer, report)
    zone = company_timezone(db)
    context = report_context(db, keyring, report, project, customer, title, zone)
    library = _library(db)
    names, values, tables = library
    roles = roles_of(db, record.user_id)
    held = _held(db, report.id)
    sites = {s.id: s.name for s in sites_of(db, sealer, customer.id)}
    may_write = (writes(db, record.user_id, roles, project) and project.archived_at is None
                 and report.status == DRAFT)
    shown_content = content.dump()
    # Sample answers are the builder's, for "Try it"; a report has its own.
    shown_content.pop("sample", None)
    assets = db.scalars(select(TemplateAsset).where(TemplateAsset.template_id == template.id))
    opened = sealer.open("project", project.id, project.sealed)
    return ReportDetail(
        id=report.id, number=report.number, title=title, status=report.status,
        revision=report.revision,
        project=ProjectRef(id=project.id, number=project.number, name=str(opened["name"]),
                           classification=project.classification,
                           archived=project.archived_at is not None),
        customer=Named(id=customer.id, name=keyring.name(customer)),
        template=TemplateOut(**_template_ref(template, version).model_dump(),
                             content=shown_content),
        site=(Named(id=report.site_id, name=sites[report.site_id])
              if report.site_id in sites else None),
        sites=[Named(id=i, name=sites[i]) for i in site_ids_of(db, project.id) if i in sites],
        author=_named(db, report.author_id),
        created_at=report.created_at, updated_at=report.updated_at,
        answers=shown(content, answers), saves=report.saves, context=context,
        library=LibraryOut(names=names, values=values, tables={
            key: TableOut(columns=list(table.columns),
                          rows={k: list(v) for k, v in table.rows.items()})
            for key, table in tables.items()}),
        people=_people(db, project, _asked(content)),
        assets={a.sha256: AssetRef(url=f"/api/reports/{report.id}/assets/{a.sha256}",
                                   width=a.width, height=a.height) for a in assets},
        time_zone=zone,
        checkouts=_checkouts_out(db, record, held),
        may_edit=may_write,
        may_reveal=may_write or _reviews(db, record.user_id, roles, project),
        may_break=can(roles, Capability.BREAK_CHECKOUTS),
        may_discard=may_write and (report.author_id == record.user_id
                                   or can(roles, Capability.ADMINISTER)),
        state=_state(content, answers, context, library, zone),
    )


# Reports


@router.get("/projects/{project_id}/reports")
def list_reports(project_id: int, request: Request, record: FullSession, db: DB) -> ReportList:
    """The project's reports, newest first."""
    project, customer = visible_project(db, request, record, project_id)
    keyring = Keyring()
    reports = db.scalars(select(Report).where(Report.project_id == project.id)
                         .order_by(Report.created_at.desc(), Report.id.desc()))
    roles = roles_of(db, record.user_id)
    return ReportList(
        reports=[_summary(db, record, keyring, customer, report) for report in reports],
        may_create=(writes(db, record.user_id, roles, project) and project.archived_at is None),
    )


@router.get("/projects/{project_id}/report-templates")
def list_report_templates(project_id: int, request: Request, record: FullSession, db: DB
                          ) -> list[TemplateChoice]:
    """The templates a report can be written with: published and not retired, each at
    its newest version."""
    _writable_project(db, request, record, project_id)
    choices = []
    for template in db.scalars(select(Template).where(Template.retired_at.is_(None))):
        version = _newest(db, template.id)
        if version is None or version.number is None:
            continue
        prefix = json.loads(version.content).get("settings", {}).get("prefix", "REP")
        choices.append(TemplateChoice(id=template.id, name=template.name,
                                      description=template.description,
                                      version=version.number, prefix=str(prefix)))
    return sorted(choices, key=lambda choice: choice.name.casefold())


def _newest(db: Session, template_id: int) -> TemplateVersion | None:
    return db.scalar(select(TemplateVersion)
                     .where(TemplateVersion.template_id == template_id,
                            TemplateVersion.number.is_not(None))
                     .order_by(TemplateVersion.number.desc()).limit(1))


def _check_site(db: Session, project: Project, site_id: int | None) -> None:
    if site_id is not None and site_id not in site_ids_of(db, project.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That site isn't one of the project's.")


@router.post("/projects/{project_id}/reports", status_code=status.HTTP_201_CREATED)
def create_report(project_id: int, body: ReportIn, request: Request, record: FullSession,
                  db: DB) -> ReportDetail:
    """Start a report with a template's newest published version. It stays pinned to
    that version, whatever is published later."""
    project, customer = _writable_project(db, request, record, project_id)
    template = db.get(Template, body.template_id)
    version = _newest(db, template.id) if template is not None else None
    if template is None or version is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Choose a published template to write the report with.")
    if template.retired_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That template is retired: no new reports are written with it.")
    _check_site(db, project, body.site_id)
    content = TemplateContent.model_validate_json(version.content)
    now = clock.utcnow()
    report = Report(
        project_id=project.id, number=next_number(db, content.settings.prefix),
        template_version_id=version.id, status=DRAFT, revision=1, sealed_title=b"",
        sealed_answers=b"", site_id=body.site_id, saves=0, author_id=record.user_id,
        created_at=now, updated_at=now, updated_by=record.user_id,
    )
    db.add(report)
    db.flush()
    keyring = Keyring()
    _seal_title(keyring, customer, report, (body.title or "").strip() or template.name)
    _seal_answers(keyring, customer, report, {})
    _log(db, request, record, "report.created", report,
         {"project": project.number, "template": template.id, "version": version.number})
    db.commit()
    return _detail(db, record, report, project, customer)


@router.get("/reports/{report_id}")
def get_report(report_id: int, request: Request, record: FullSession, db: DB) -> ReportDetail:
    report, project, customer = _open(db, request, record, report_id)
    detail = _detail(db, record, report, project, customer)
    _log_view(db, request, record, report)
    db.commit()
    return detail


def _log_view(db: Session, request: Request, record: UserSession, report: Report) -> None:
    """Every view of a report is logged, once per person and sitting."""
    now = clock.utcnow()
    key = (record.user_id, report.id)
    last = _VIEWS_LOGGED.get(key)
    if last is not None and timedelta(0) <= now - last < LOG_VIEWS_EVERY:
        return
    if len(_VIEWS_LOGGED) >= _VIEWS_REMEMBERED:
        _VIEWS_LOGGED.clear()
    _VIEWS_LOGGED[key] = now
    _log(db, request, record, "report.viewed", report)


@router.get("/reports/{report_id}/activity")
def get_activity(report_id: int, request: Request, record: FullSession, db: DB) -> Activity:
    """Who holds what and whether it was saved since: what an open report asks now
    and then, to notice other people's work."""
    report, _, _ = _open(db, request, record, report_id)
    return Activity(status=report.status, saves=report.saves, updated_at=report.updated_at,
                    checkouts=_checkouts_out(db, record, _held(db, report.id)))


@router.post("/reports/{report_id}/check")
def check_report(report_id: int, request: Request, record: FullSession, db: DB) -> StateOut:
    """The server's own verdict on the answers as they're kept now."""
    report, project, customer = _open(db, request, record, report_id)
    keyring = Keyring()
    _, _, content = _pinned(db, report)
    zone = company_timezone(db)
    context = report_context(db, keyring, report, project, customer,
                             _title(keyring, customer, report), zone)
    return _state(content, _answers(keyring, customer, report), context, _library(db), zone)


def _touch(report: Report, record: UserSession, now: datetime) -> None:
    report.updated_at = now
    report.updated_by = record.user_id


@router.patch("/reports/{report_id}")
def update_report(report_id: int, body: ReportUpdate, request: Request, record: FullSession,
                  db: DB) -> ReportDetail:
    """Change the report's title or the site it's about. Its holder does: someone who
    has a part of it checked out."""
    report, project, customer = _writable(db, request, record, report_id)
    if not any(c.user_id == record.user_id for c in _held(db, report.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Check the report out to change it.")
    keyring = Keyring()
    sent = body.model_fields_set
    changed = []
    if body.title is not None and body.title.strip() != _title(keyring, customer, report):
        if not body.title.strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the report a title.")
        _seal_title(keyring, customer, report, body.title.strip())
        changed.append("title")
    if "site_id" in sent and body.site_id != report.site_id:
        _check_site(db, project, body.site_id)
        report.site_id = body.site_id
        changed.append("site")
    if changed:
        _touch(report, record, clock.utcnow())
        _log(db, request, record, "report.updated", report, {"fields": changed})
    db.commit()
    return _detail(db, record, report, project, customer)


@router.patch("/reports/{report_id}/answers")
def save_answers(report_id: int, body: AnswersIn, request: Request, record: FullSession,
                 db: DB) -> Saved:
    """Keep the answers sent: the ones that changed, not the whole form, so two people
    working in different steps never overwrite each other. Each must be in a step the
    saver has checked out."""
    report, project, customer = _writable(db, request, record, report_id)
    _, _, content = _pinned(db, report)
    held = _held(db, report.id)
    step_of = {q.id: step.id for step in content.form for q in step.questions}
    for question_id in body.answers:
        if question_id not in step_of:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "That question isn't in this report's template.")
        if not _covers(held, record.user_id, step_of[question_id]):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Check the step out before changing its answers.")
    keyring = Keyring()
    before = _answers(keyring, customer, report)
    now = clock.utcnow()
    try:
        answers, changed = merge(content, before, body.answers,
                                 find_person=_person_finder(db, project), now=now)
    except Refused as refused:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refused)) from None
    for checkout in held:
        if checkout.user_id == record.user_id:
            checkout.active_at = now
    if changed:
        _seal_answers(keyring, customer, report, answers)
        report.saves += 1
        _touch(report, record, now)
        by_id = {q.id: q for q in questions(content)}
        # A signature is someone's word: each one taken is logged, not one save in ten.
        signed = [q for q in changed if by_id[q].type == "signature" and answers.get(q)]
        if signed:
            _log(db, request, record, "report.signature_recorded", report,
                 {"questions": signed})
        if (report.logged_by != record.user_id or report.logged_at is None
                or now - report.logged_at >= LOG_SAVES_EVERY):
            _log(db, request, record, "report.answers_saved", report, {"saves": report.saves})
            report.logged_at, report.logged_by = now, record.user_id
    db.commit()
    kept = shown(content, {q: answers[q] for q in changed if q in answers})
    return Saved(saves=report.saves, updated_at=report.updated_at, answers=kept,
                 forgotten=[q for q in changed if q not in answers])


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_report(report_id: int, request: Request, record: FullSession, db: DB,
                   body: Annotated[DiscardIn, Body()]) -> Response:
    """Discard a draft, for whoever started it and for Administrators, who type its
    number to confirm. Its number isn't used again."""
    report, _, _ = _writable(db, request, record, report_id)
    roles = roles_of(db, record.user_id)
    if report.author_id != record.user_id and not can(roles, Capability.ADMINISTER):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only whoever started a report, or an Administrator, discards it.")
    if body.confirm_number.strip() != report.number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Type the report's number exactly to confirm.")
    if any(c.user_id != record.user_id for c in _held(db, report.id)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Someone else has this report checked out.")
    template, version, _ = _pinned(db, report)
    _log(db, request, record, "report.discarded", report,
         {"template": template.id, "version": version.number})
    db.delete(report)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Checkouts


@router.post("/reports/{report_id}/checkouts")
def check_out(report_id: int, body: CheckoutIn, request: Request, record: FullSession, db: DB
              ) -> Activity:
    """Check out one step of the form, or the whole report (no step). A part someone
    else holds can't be taken; they release it, or an Administrator ends it."""
    report, _, _ = _writable(db, request, record, report_id)
    _, _, content = _pinned(db, report)
    if body.step is not None and body.step not in {step.id for step in content.form}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That step isn't in this report.")
    held = _held(db, report.id)
    mine = [c for c in held if c.user_id == record.user_id]
    others = [c for c in held if c.user_id != record.user_id]
    in_the_way = [c for c in others if body.step is None or c.step_id in (None, body.step)]
    if in_the_way:
        holder = db.get(User, in_the_way[0].user_id)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{holder.display_name if holder else 'Someone'} has "
            f"{_what(in_the_way[0], content)} checked out.")
    if not any(c.step_id is None or c.step_id == body.step for c in mine):
        now = clock.utcnow()
        if body.step is None:
            # The whole report takes the place of the steps they held.
            for checkout in mine:
                db.delete(checkout)
            db.flush()
        db.add(ReportCheckout(report_id=report.id, step_id=body.step, user_id=record.user_id,
                              taken_at=now, active_at=now))
        _log(db, request, record, "report.checked_out", report, {"step": body.step})
    db.commit()
    return Activity(status=report.status, saves=report.saves, updated_at=report.updated_at,
                    checkouts=_checkouts_out(db, record, _held(db, report.id)))


def _checkout(db: Session, report: Report, checkout_id: int) -> ReportCheckout:
    checkout = db.get(ReportCheckout, checkout_id)
    if checkout is None or checkout.report_id != report.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That checkout has ended already.")
    return checkout


@router.delete("/reports/{report_id}/checkouts/{checkout_id}")
def release(report_id: int, checkout_id: int, request: Request, record: FullSession, db: DB
            ) -> Activity:
    """Release a checkout of one's own. What was saved under it is kept."""
    report, _, _ = _open(db, request, record, report_id)
    checkout = _checkout(db, report, checkout_id)
    if checkout.user_id != record.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only its holder releases a checkout; an Administrator can end it.")
    db.delete(checkout)
    _log(db, request, record, "report.checkout_released", report, {"step": checkout.step_id})
    db.commit()
    return Activity(status=report.status, saves=report.saves, updated_at=report.updated_at,
                    checkouts=_checkouts_out(db, record, _held(db, report.id)))


@router.post("/reports/{report_id}/checkouts/{checkout_id}/break")
def break_checkout(report_id: int, checkout_id: int, request: Request, admin: Breaker, db: DB
                   ) -> Activity:
    """End someone's checkout, stale or not. It's logged, and its holder is told by
    email when email is set up and they have an address."""
    report, _, _ = _open(db, request, admin, report_id)
    checkout = _checkout(db, report, checkout_id)
    holder = db.get(User, checkout.user_id)
    stale = clock.utcnow() - checkout.active_at > timedelta(hours=stale_hours(db))
    told = False
    if holder is not None and holder.email and mail.load_server(db).configured:
        part = "the whole report" if checkout.step_id is None else "a step of the report"
        jobs.enqueue(db, "mail", {
            "to": [holder.email],
            "subject": f"Your checkout of {report.number} was ended",
            "body": (f"{admin.user.display_name} ended your checkout of {part} "
                     f"{report.number}. What you had saved is kept. To carry on, open the "
                     "report and check it out again." + SIGN_OFF.format(address=settings.address)),
        })
        told = True
    db.delete(checkout)
    _log(db, request, admin, "report.checkout_broken", report,
         {"step": checkout.step_id, "holder": checkout.user_id, "stale": stale,
          "holder_told": told})
    db.commit()
    return Activity(status=report.status, saves=report.saves, updated_at=report.updated_at,
                    checkouts=_checkouts_out(db, admin, _held(db, report.id)))


# Secrets and images


@router.post("/reports/{report_id}/answers/{question_id}/reveal")
def reveal_secret(report_id: int, question_id: str, request: Request, record: FullSession,
                  db: DB) -> Revealed:
    """Show a secret answer, to those who write or review the report, after they've
    confirmed it's them just now. Every look is logged; the value never is."""
    report, project, customer = _open(db, request, record, report_id)
    roles = roles_of(db, record.user_id)
    if not (writes(db, record.user_id, roles, project)
            or _reviews(db, record.user_id, roles, project)):
        _log(db, request, record, "report.secret_refused", report, {"question": question_id})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only those who write or review this report see its secrets.")
    _, _, content = _pinned(db, report)
    question = next((q for q in questions(content) if q.id == question_id), None)
    value = _answers(Keyring(), customer, report).get(question_id)
    if question is None or question.type != "secret" or not isinstance(value, str) or not value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no secret answer there.")
    require_step_up(record, "Confirm it's you to see this secret.")
    _log(db, request, record, "report.secret_revealed", report, {"question": question_id})
    db.commit()
    return Revealed(value=value, seconds=REVEAL_SECONDS)


@router.get("/reports/{report_id}/assets/{digest}")
def get_asset(report_id: int, digest: str, request: Request, record: FullSession, db: DB
              ) -> Response:
    """One of the template's images, for those who may read the report."""
    report, _, _ = _open(db, request, record, report_id)
    version = db.get(TemplateVersion, report.template_version_id)
    asset = (db.scalar(select(TemplateAsset).where(
        TemplateAsset.template_id == version.template_id, TemplateAsset.sha256 == digest))
        if version is not None and _SHA256.match(digest) else None)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That image doesn't exist.")
    return Response(asset.data, media_type=asset.content_type, headers={
        # Named by its hash, so it never changes; and never run as a page.
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    })


# Settings


@router.get("/admin/report-settings")
def get_report_settings(admin: Administrator, db: DB) -> ReportSettings:
    return ReportSettings(checkout_stale_hours=stale_hours(db))


@router.put("/admin/report-settings")
def put_report_settings(body: ReportSettings, request: Request, admin: Administrator, db: DB
                        ) -> ReportSettings:
    """How long a checkout may sit unused before it's marked stale."""
    if body.checkout_stale_hours != stale_hours(db):
        set_stale_hours(db, body.checkout_stale_hours)
        audit.append(db, "admin.report_settings_changed", actor_id=admin.user.id,
                     actor_name=admin.user.username, ip=client_ip(request),
                     details={"checkout_stale_hours": body.checkout_stale_hours})
    db.commit()
    return ReportSettings(checkout_stale_hours=stale_hours(db))
