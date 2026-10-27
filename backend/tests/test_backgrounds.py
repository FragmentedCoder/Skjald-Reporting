"""Customers' report backgrounds: uploads, the renderer's conversion, who may change them."""

from __future__ import annotations

import io
import json
import shutil
import threading
import time
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app import backgrounds, jobs
from app.audit import AuditEntry
from app.backgrounds import CustomerBackground, render_pdf
from app.customers import Customer
from app.renderer import RenderError, convert_background
from app.roles import Role, grant_role

CUSTOMERS = "/api/customers"


def minimal_pdf(width: float = 595.28, height: float = 841.89, pages: int = 1) -> bytes:
    """A small PDF with a filled box on each page, its cross-reference table worked out."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>")
    for i in range(pages):
        stream = f"0.17 0.36 0.54 rg 40 {height - 120} 200 80 re f"
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                       f"/Contents {4 + 2 * i} 0 R >>")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
              .encode())
    return out.getvalue()


def picture(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "#DCE6EE").save(out, format="PNG")
    return out.getvalue()


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
def customer(client, admin):
    _, headers = admin
    return client.post(CUSTOMERS, headers=headers, json={"name": "Fjordvik Logistik A/S"}).json()


def upload(client, headers, customer_id, data):
    return client.put(f"{CUSTOMERS}/{customer_id}/background", content=data,
                      headers={**headers, "Content-Type": "application/octet-stream"})


def test_a_picture_of_a_page_is_ready_at_once(client, admin, customer) -> None:
    _, headers = admin
    done = upload(client, headers, customer["id"], picture(420, 594))
    assert done.status_code == 200
    assert (done.json()["status"], done.json()["pages"]) == ("ready", 1)
    page = client.get(f"{CUSTOMERS}/{customer['id']}/background/pages/1", headers=headers)
    assert page.headers["content-type"].startswith("image/svg+xml")
    assert "sandbox" in page.headers["content-security-policy"]
    assert b'href="data:image/png;base64,' in page.content
    wrong = upload(client, headers, customer["id"], picture(600, 400))
    assert wrong.status_code == 400
    assert "A4" in wrong.json()["detail"]


def test_an_svg_page_is_cleaned(client, admin, customer) -> None:
    _, headers = admin
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297"><script>x()</script>'
           b'<rect width="210" height="20" style="fill:#2B5D8A;stroke:none" onclick="y()"/></svg>')
    assert upload(client, headers, customer["id"], svg).json()["status"] == "ready"
    page = client.get(f"{CUSTOMERS}/{customer['id']}/background/pages/1", headers=headers).content
    assert b"script" not in page and b"onclick" not in page and b"style=" not in page
    assert b'fill="#2B5D8A"' in page


def test_a_pdf_is_converted_by_the_renderer(client, admin, customer, session, monkeypatch) -> None:
    _, headers = admin
    started = upload(client, headers, customer["id"], minimal_pdf())
    assert started.json()["status"] == "converting"
    [job] = session.scalars(select(jobs.Job).where(jobs.Job.kind == "background.convert"))
    session.commit()
    page = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 595 842">'
            '<rect width="9" height="9"/></svg>')
    monkeypatch.setattr(backgrounds, "render_pdf", lambda pdf: [page, page])
    assert backgrounds.convert(session, job) == {"status": "ready", "pages": 2}
    session.commit()
    shown = client.get(f"{CUSTOMERS}/{customer['id']}/background", headers=headers).json()
    assert (shown["status"], shown["pages"]) == ("ready", 2)

    refusal = "The background must be A4 portrait (210 × 297 mm)."

    def refuse(pdf: bytes) -> list[str]:
        raise RenderError(refusal)

    upload(client, headers, customer["id"], minimal_pdf())
    monkeypatch.setattr(backgrounds, "render_pdf", refuse)
    assert backgrounds.convert(session, job)["status"] == "failed"
    session.commit()
    shown = client.get(f"{CUSTOMERS}/{customer['id']}/background", headers=headers).json()
    assert (shown["status"], shown["message"]) == ("failed", refusal)


def test_the_worker_and_the_renderer_meet_in_their_folder(tmp_path: Path) -> None:
    def renderer(result: dict[str, object]) -> None:
        for _ in range(100):
            found = list((tmp_path / "in").glob("*.pdf"))
            if found:
                (tmp_path / "out").mkdir(exist_ok=True)
                (tmp_path / "out" / f"{found[0].stem}.json").write_text(json.dumps(result))
                found[0].unlink()
                return
            time.sleep(0.05)

    helper = threading.Thread(target=renderer, args=({"pages": ["<svg/>"]},))
    helper.start()
    assert render_pdf(b"%PDF-1.4", exchange=tmp_path, wait=5) == ["<svg/>"]
    helper.join()
    assert list(tmp_path.rglob("*.json")) == [] and list(tmp_path.rglob("*.pdf")) == []
    helper = threading.Thread(target=renderer, args=({"error": "Not a PDF."},))
    helper.start()
    with pytest.raises(RenderError, match="Not a PDF."):
        render_pdf(b"%PDF-1.4", exchange=tmp_path, wait=5)
    helper.join()
    with pytest.raises(RenderError, match="couldn't convert"):
        render_pdf(b"%PDF-1.4", exchange=tmp_path, wait=0.3)


@pytest.mark.skipif(shutil.which("pdftocairo") is None, reason="needs poppler, as the renderer has")
def test_the_renderer_turns_an_a4_pdf_into_svg_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "letterhead.pdf"
    pdf.write_bytes(minimal_pdf(pages=3))
    pages = convert_background(pdf)
    assert len(pages) == 2
    assert all(page.lstrip().startswith(("<?xml", "<svg")) for page in pages)
    letter = tmp_path / "letter.pdf"
    letter.write_bytes(minimal_pdf(width=612, height=792))
    with pytest.raises(RenderError, match="A4 portrait.*216 × 279 mm"):
        convert_background(letter)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(RenderError):
        convert_background(broken)


def test_who_changes_backgrounds(client, person, customer, session) -> None:
    _, tech = person("tove", "technician")
    assert upload(client, tech, customer["id"], picture(210, 297)).status_code == 403
    _, designer = person("dagny", "report_designer")
    assert upload(client, designer, customer["id"], picture(210, 297)).status_code == 200
    margins = client.patch(f"{CUSTOMERS}/{customer['id']}/background", headers=designer,
                           json={"top": 40, "bottom": 30, "left": 25, "right": 25})
    assert margins.json()["margins"] == {"top": 40, "bottom": 30, "left": 25, "right": 25}
    _, manager = person("maja", "manager")
    assert client.delete(f"{CUSTOMERS}/{customer['id']}/background",
                         headers=manager).status_code == 204
    assert client.get(f"{CUSTOMERS}/{customer['id']}/background",
                      headers=manager).status_code == 404
    logged = [(e.action, e.target_id) for e in session.scalars(
        select(AuditEntry).where(AuditEntry.action.like("customer.background%"))
        .order_by(AuditEntry.seq))]
    assert logged == [("customer.background_changed", str(customer["id"])),
                      ("customer.background_margins_changed", str(customer["id"])),
                      ("customer.background_removed", str(customer["id"]))]
    refused = session.scalars(select(AuditEntry).where(AuditEntry.action == "auth.access_denied")
                              .order_by(AuditEntry.seq.desc())).first()
    assert refused is not None and refused.actor_name == "tove"


def test_deleting_the_customer_deletes_its_background(client, admin, customer, session) -> None:
    _, headers = admin
    upload(client, headers, customer["id"], picture(210, 297))
    assert len(session.scalars(select(CustomerBackground)).all()) == 1
    doomed = session.get(Customer, customer["id"])
    session.delete(doomed)
    session.commit()
    assert session.scalars(select(CustomerBackground)).all() == []
