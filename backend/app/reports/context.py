"""A report's context: what its template's expressions read besides the answers.

The names are app/templates/names.py's CONTEXT (company, customer, site, contact,
project, report, author, reviewer) and the custom fields (customer.custom.<key>,
project.custom.<key>), here with a real report's values. The same values go to the
browser, which works the form and the preview out as the technician types, and to
the server's own check (app/reports/form.py), so both read one set.

Moments are ISO 8601 in UTC, as the browser writes them. A day (a project's dates, a
custom date field) is midnight in the company's time zone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import clock
from app.custom_fields import fields_for
from app.customers import Customer, CustomerContact, CustomerSite, Keyring
from app.projects import Project, site_ids_of
from app.reports.models import Report
from app.setup import company_name
from app.templates.fields import PERSON_PARTS
from app.users import User


def instant(moment: datetime) -> str:
    """A moment as the browser's toISOString() writes it: 2026-10-24T09:30:00.000Z."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _day(value: Any, zone: ZoneInfo) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return instant(datetime.combine(date.fromisoformat(value), time(), tzinfo=zone))
    except ValueError:
        return None


def person_parts(user: User | None, company: str) -> dict[str, str]:
    """Someone's business details as reports print them; all empty for nobody. Their
    company is the one in their profile (a consultant's own), else the company's."""
    if user is None:
        return dict.fromkeys(PERSON_PARTS, "")
    return {
        "display_name": user.display_name,
        "first_name": user.first_name or "",
        "middle_name": user.middle_name or "",
        "last_name": user.last_name or "",
        "job_title": user.job_title or "",
        "department": user.department or "",
        "company": user.company or company,
        "email": user.email or "",
        "phone": user.phone or "",
    }


def _custom(db: Session, applies_to: str, stored: dict[str, Any] | None, zone: ZoneInfo
            ) -> dict[str, Any]:
    """The custom fields' values, archived fields' too (a template published while
    one was in use still reads it), each as the kind of value expressions read it as."""
    values: dict[str, Any] = {}
    for field in fields_for(db, applies_to, archived=True):
        held = (stored or {}).get(field.key)
        if held is None:
            continue
        if field.type == "date":
            held = _day(held, zone)
        elif field.type == "number":
            held = float(held)
        if held is not None:
            values[field.key] = held
    return values


def site_of(db: Session, report: Report, project: Project) -> CustomerSite | None:
    """The site the report is about: the one chosen for it, or the project's only one."""
    if report.site_id is not None:
        return db.get(CustomerSite, report.site_id)
    sites = site_ids_of(db, project.id)
    return db.get(CustomerSite, sites[0]) if len(sites) == 1 else None


def report_context(
    db: Session, keyring: Keyring, report: Report, project: Project, customer: Customer,
    title: str, zone_name: str,
) -> dict[str, Any]:
    zone = ZoneInfo(zone_name)
    sealer = keyring.sealer(customer)
    company = company_name(db) or ""
    details = keyring.details(customer)
    opened = sealer.open("project", project.id, project.sealed)
    site = site_of(db, report, project)
    site_details = sealer.open("site", site.id, site.sealed) if site else {}
    contact = db.get(CustomerContact, project.contact_id) if project.contact_id else None
    contact_details = sealer.open("contact", contact.id, contact.sealed) if contact else {}
    author = db.get(User, report.author_id) if report.author_id else None
    reviewer = db.get(User, project.reviewer_id) if project.reviewer_id else None
    return {
        "company": {"name": company},
        "customer": {
            "name": str(details.get("name") or ""),
            "cvr": str(details.get("cvr") or ""),
            "address": str(details.get("address") or ""),
            "language": customer.language,
            "custom": _custom(db, "customer", details.get("custom"), zone),
        },
        "site": {"name": str(site_details.get("name") or ""),
                 "address": str(site_details.get("address") or "")},
        "contact": {part: str(contact_details.get(part) or "")
                    for part in ("name", "role", "email", "phone")},
        "project": {
            "name": str(opened.get("name") or ""),
            "number": project.number,
            "start_date": _day(opened.get("start_date"), zone),
            "end_date": _day(opened.get("end_date"), zone),
            "classification": project.classification,
            "custom": _custom(db, "project", opened.get("custom"), zone),
        },
        "report": {
            "title": title,
            "number": report.number,
            "revision": report.revision,
            # When it was signed, or today while it's a draft.
            "date": instant(clock.utcnow()),
            "started": instant(report.created_at),
        },
        "author": person_parts(author, company),
        "reviewer": person_parts(reviewer, company),
    }
