"""A customer's report background: the letterhead art its reports print on.

Administrators and Managers (who run customers) and Report Designers (who style
reports, and see every customer's name) upload, adjust and remove it; whoever sees
the customer in full can look at it too. Uploads are logged by customer ID, like
everything else about a customer.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app import audit, clock, jobs
from app.auth.dependencies import DB, FullSession, client_ip, effective_capabilities
from app.auth.sessions import UserSession
from app.backgrounds import BackgroundRejected, CustomerBackground, prepare
from app.customer_routes import visible_customer
from app.customers import Customer, Keyring
from app.roles import Capability
from app.users import User

router = APIRouter(prefix="/customers/{customer_id}/background")

NONE = "This customer has no report background."


class Margins(BaseModel):
    top: float = Field(ge=5, le=80)
    bottom: float = Field(ge=5, le=80)
    left: float = Field(ge=5, le=60)
    right: float = Field(ge=5, le=60)


class BackgroundOut(BaseModel):
    status: str
    message: str
    pages: int
    margins: Margins
    uploaded_at: datetime
    uploaded_by: str | None


def styler(request: Request, record: FullSession, db: DB) -> UserSession:
    """Someone who may change customers' report backgrounds."""
    allowed = effective_capabilities(db, record, request)
    if not allowed & {Capability.MANAGE_CUSTOMERS, Capability.EDIT_STYLES}:
        audit.append(db, "auth.access_denied", actor_id=record.user.id,
                     actor_name=record.user.username, ip=client_ip(request),
                     details={"capability": "edit_styles", "path": request.url.path})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change report backgrounds.")
    return record


Styler = Annotated[UserSession, Depends(styler)]


def _customer(db: DB, request: Request, record: UserSession, customer_id: int) -> Customer:
    customer, _ = visible_customer(db, request, record, customer_id, need="names")
    return customer


def _out(db: DB, row: CustomerBackground) -> BackgroundOut:
    pages = 0
    if row.sealed_pages is not None:
        customer = db.get(Customer, row.customer_id)
        assert customer is not None
        pages = len(Keyring().sealer(customer).open("background-pages", row.customer_id,
                                                    row.sealed_pages)["pages"])
    who = db.get(User, row.uploaded_by) if row.uploaded_by else None
    return BackgroundOut(
        status=row.status, message=row.message, pages=pages,
        margins=Margins(top=row.margin_top, bottom=row.margin_bottom, left=row.margin_left,
                        right=row.margin_right),
        uploaded_at=row.uploaded_at, uploaded_by=who.display_name if who else None,
    )


def _log(db: DB, request: Request, record: UserSession, action: str, customer_id: int,
         **details: object) -> None:
    audit.append(db, action, actor_id=record.user.id, actor_name=record.user.username,
                 target_type="customer", target_id=str(customer_id), ip=client_ip(request),
                 details=details or None)


@router.get("")
def get_background(customer_id: int, request: Request, record: FullSession, db: DB
                   ) -> BackgroundOut:
    customer, level = visible_customer(db, request, record, customer_id, need="names")
    styles = Capability.EDIT_STYLES in effective_capabilities(db, record, request)
    if level != "full" and not styles:
        visible_customer(db, request, record, customer_id, need="full")
    row = db.get(CustomerBackground, customer.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NONE)
    return _out(db, row)


@router.put("")
def upload_background(
    customer_id: int, data: Annotated[bytes, Body(media_type="application/octet-stream")],
    request: Request, record: Styler, db: DB,
) -> BackgroundOut:
    customer = _customer(db, request, record, customer_id)
    try:
        kind, pages = prepare(data)
    except BackgroundRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    sealer = Keyring().sealer(customer)
    row = db.get(CustomerBackground, customer.id)
    if row is None:
        row = CustomerBackground(customer_id=customer.id, margin_top=30, margin_bottom=25,
                                 margin_left=20, margin_right=20, message="")
        db.add(row)
    row.sealed_original = sealer.seal("background", customer.id, {
        "file": base64.b64encode(data).decode(), "type": kind})
    row.sealed_pages = (sealer.seal("background-pages", customer.id, {"pages": pages})
                        if pages else None)
    row.status = "ready" if pages else "converting"
    row.message = ""
    row.uploaded_at = clock.utcnow()
    row.uploaded_by = record.user_id
    db.flush()
    if pages is None:
        jobs.enqueue(db, "background.convert", {"customer_id": customer.id},
                     requested_by=record.user_id)
    _log(db, request, record, "customer.background_changed", customer.id, type=kind)
    db.commit()
    return _out(db, row)


@router.patch("")
def set_margins(customer_id: int, body: Margins, request: Request, record: Styler, db: DB
                ) -> BackgroundOut:
    customer = _customer(db, request, record, customer_id)
    row = db.get(CustomerBackground, customer.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NONE)
    row.margin_top, row.margin_bottom = body.top, body.bottom
    row.margin_left, row.margin_right = body.left, body.right
    _log(db, request, record, "customer.background_margins_changed", customer.id)
    db.commit()
    return _out(db, row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_background(customer_id: int, request: Request, record: Styler, db: DB) -> Response:
    customer = _customer(db, request, record, customer_id)
    row = db.get(CustomerBackground, customer.id)
    if row is not None:
        db.delete(row)
        _log(db, request, record, "customer.background_removed", customer.id)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pages/{number}")
def background_page(customer_id: int, number: int, request: Request, record: FullSession,
                    db: DB) -> Response:
    get_background(customer_id, request, record, db)
    customer = db.get(Customer, customer_id)
    row = db.get(CustomerBackground, customer_id)
    assert customer is not None and row is not None
    pages = (Keyring().sealer(customer).open("background-pages", customer_id, row.sealed_pages)
             ["pages"] if row.sealed_pages else [])
    if not 1 <= number <= len(pages):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That page doesn't exist.")
    return Response(pages[number - 1], media_type="image/svg+xml", headers={
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy":
            "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox",
    })
