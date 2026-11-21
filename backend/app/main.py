import math
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import (
    account,
    admin,
    audit_routes,
    background_routes,
    backup_routes,
    branding,
    custom_fields,
    customer_routes,
    maintenance,
    project_routes,
    server_routes,
    setup_routes,
)
from app.api import health
from app.auth import mfa_routes
from app.auth import routes as auth_routes
from app.auth.dependencies import SAFE_METHODS
from app.library import routes as library_routes
from app.styles import routes as style_routes
from app.templates import routes as template_routes
from app.templates import transfer as template_transfer

app = FastAPI(title="Skjald", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def refuse_cross_site_writes(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Browsers label requests another site started; such a request may not change anything.

    A second guard beside SameSite=Strict cookies and the CSRF token; it also covers
    sign-in, which has no session yet.
    """
    site = request.headers.get("sec-fetch-site")
    if request.method not in SAFE_METHODS and site in {"cross-site", "same-site"}:
        return JSONResponse({"detail": "Requests from other sites are not allowed."}, 403)
    return await call_next(request)


def _writable(value: Any) -> Any:
    """The value with each NaN and Infinity as text: JSON has neither."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _writable(held) for key, held in value.items()}
    if isinstance(value, list | tuple):
        return [_writable(held) for held in value]
    return value


@app.exception_handler(RequestValidationError)
async def refuse_invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's own answer to a request that fails its checks, which repeats what was
    sent. A NaN or an Infinity sent as a number can't be written as JSON, which made
    that answer an HTTP 500: here they're repeated as text."""
    return JSONResponse({"detail": _writable(jsonable_encoder(exc.errors()))}, 422)


@app.exception_handler(OverflowError)
async def refuse_huge_number(request: Request, exc: OverflowError) -> JSONResponse:
    """A whole number beyond what the database holds (64 bits), as an ID in the address
    or in what was sent: nothing has it, so the request is refused, not failed."""
    return JSONResponse({"detail": "A number in the request is too large."}, 400)


app.include_router(health.router, prefix="/api")
app.include_router(auth_routes.router, prefix="/api")
app.include_router(mfa_routes.router, prefix="/api")
app.include_router(setup_routes.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(branding.router, prefix="/api")
app.include_router(audit_routes.router, prefix="/api")
app.include_router(backup_routes.router, prefix="/api")
app.include_router(customer_routes.router, prefix="/api")
app.include_router(project_routes.router, prefix="/api")
app.include_router(server_routes.router, prefix="/api")
app.include_router(template_transfer.router, prefix="/api")
app.include_router(template_routes.router, prefix="/api")
app.include_router(library_routes.router, prefix="/api")
app.include_router(background_routes.router, prefix="/api")
app.include_router(style_routes.router, prefix="/api")
app.include_router(style_routes.customer_router, prefix="/api")
app.include_router(custom_fields.router, prefix="/api")
