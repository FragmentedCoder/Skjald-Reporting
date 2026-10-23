"""Phase 0 spike: PDF/A-3b rendering and sequential PAdES signatures.

Proves (or disproves) the riskiest part of Skjald's report pipeline:

1. WeasyPrint renders a branded report as PDF/A-3b with the bundled Skjald fonts,
   header, footer, "Page X of Y" and a DRAFT watermark, and cannot fetch any URL.
2. pyHanko adds three signatures in a row (technician, reviewer, company seal) from a
   built-in test CA, each with a trusted timestamp and embedded revocation data,
   and the last one locks the document. Every signature must still validate at the end,
   and the long-term data must be enough to validate offline.
3. Delivery copies protected by a password: what breaks, and what works.

Everything here is throw-away test material: the CA, keys and people are fictional,
and all output goes to ./out (git-ignored).

Usage:
    python spike.py --fonts <folder with the five TTF files> [--out out]
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import io
import json
import pathlib
import subprocess
import time
import urllib.parse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko import stamp
from pyhanko.keys import load_cert_from_pemder, load_private_key_from_pemder
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.writer import copy_into_new_writer
from pyhanko.sign import fields, signers
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata, PdfSigner
from pyhanko.sign.timestamps.dummy_client import DummyTimeStamper
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko.sign.validation.dss import DocumentSecurityStore
from pyhanko_certvalidator import ValidationContext
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher, URLFetchingError

import appearances
from sample_report import REPORT_CSS, report_html

# RFC 9336 id-kp-documentSigning
DOCUMENT_SIGNING = x509.ObjectIdentifier("1.3.6.1.5.5.7.3.36")
CRL_URL = "http://pki.skjald.invalid/ca.crl"  # never fetched; the CRL is supplied directly
PT_PER_PX = 0.75  # WeasyPrint reports anchor boxes in CSS px (1px = 0.75pt)
DELIVERY_PASSWORD = "correct-horse-fjord-anchor"  # test value only


# --------------------------------------------------------------------------- render


class LocalOnlyFetcher(URLFetcher):
    """Allows file:// URLs inside the font folder and refuses everything else."""

    def __init__(self, allowed_dir: pathlib.Path, **kwargs):
        super().__init__(**kwargs)
        self.allowed_dir = allowed_dir.resolve()
        self.refused: list[str] = []

    def fetch(self, url, headers=None):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "file":
            path = pathlib.Path(urllib.parse.unquote(parsed.path)).resolve()
            if path.is_relative_to(self.allowed_dir):
                return super().fetch(url, headers)
        self.refused.append(url)
        raise URLFetchingError(f"refused by the Skjald renderer: {url}")


def render(fonts: pathlib.Path, draft: bool):
    fetcher = LocalOnlyFetcher(fonts)
    font_config = FontConfiguration()
    css = CSS(string=REPORT_CSS, base_url=f"{fonts.as_uri()}/", font_config=font_config, url_fetcher=fetcher)
    html = HTML(string=report_html(draft), base_url=f"{fonts.as_uri()}/", url_fetcher=fetcher)
    doc = html.render(stylesheets=[css], font_config=font_config)
    pdf = doc.write_pdf(pdf_variant="pdf/a-3b")
    return doc, pdf, fetcher.refused


def signature_boxes(doc) -> dict[str, tuple[int, tuple[int, int, int, int]]]:
    """Page index and PDF box (in pt, origin bottom-left) of every .sigbox, from layout anchors."""
    boxes = {}
    for index, page in enumerate(doc.pages):
        page_h = page.height * PT_PER_PX
        for name, (x1, y1, x2, y2) in page.anchors.items():
            if name.startswith("sig-"):
                boxes[name] = (index, (round(x1 * PT_PER_PX), round(page_h - y2 * PT_PER_PX),
                                       round(x2 * PT_PER_PX), round(page_h - y1 * PT_PER_PX)))
    return boxes


# --------------------------------------------------------------------------- test PKI


def make_pki(folder: pathlib.Path) -> dict[str, pathlib.Path]:
    folder.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    files: dict[str, pathlib.Path] = {}

    def save_key(name, key):
        path = folder / f"{name}.key.pem"
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        files[f"{name}.key"] = path

    def save_cert(name, cert):
        path = folder / f"{name}.cert.pem"
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        files[f"{name}.cert"] = path

    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "DK"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nordlys IT ApS"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Skjald Signing CA (test)"),
    ])
    root = (
        x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
        .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    save_key("root", root_key)
    save_cert("root", root)

    def leaf(name, common_name, eku, signer: bool):
        # pyHanko's in-process test TSA only supports RSA; signers use ECDSA P-256.
        key = ec.generate_private_key(ec.SECP256R1()) if signer else rsa.generate_private_key(65537, 2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "DK"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nordlys IT ApS"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]))
            .issuer_name(root_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(hours=1)).not_valid_after(now + dt.timedelta(days=825))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, signer, False, False, False, False, False, False, False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([eku]), critical=not signer)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
            .add_extension(x509.CRLDistributionPoints([x509.DistributionPoint(
                full_name=[x509.UniformResourceIdentifier(CRL_URL)], relative_name=None, reasons=None,
                crl_issuer=None)]), critical=False)
            .sign(root_key, hashes.SHA256())
        )
        save_key(name, key)
        save_cert(name, cert)

    leaf("technician", "Freja Holm", DOCUMENT_SIGNING, signer=True)
    leaf("reviewer", "Ivar Lund", DOCUMENT_SIGNING, signer=True)
    leaf("company", "Nordlys IT ApS (company seal)", DOCUMENT_SIGNING, signer=True)
    leaf("tsa", "Skjald Timestamp Authority (test)", ExtendedKeyUsageOID.TIME_STAMPING, signer=False)

    crl = (
        x509.CertificateRevocationListBuilder().issuer_name(root_name)
        .last_update(now - dt.timedelta(hours=1)).next_update(now + dt.timedelta(days=7))
        .add_extension(x509.CRLNumber(1), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    files["crl"] = folder / "ca.crl"
    files["crl"].write_bytes(crl.public_bytes(serialization.Encoding.DER))
    return files


# --------------------------------------------------------------------------- signing


ROLES = [
    # (anchor id, PDF field name, person file prefix, role label, locks the document, appearance, display name)
    ("sig-technician", "Sig_Technician", "technician", "Technician", False, "handwritten", "Freja Holm"),
    ("sig-reviewer", "Sig_Reviewer", "reviewer", "Reviewer", False, "handwritten", "Ivar Lund"),
    ("sig-company", "Sig_Company", "company", "Company seal", True, "stamp", "Nordlys IT ApS"),
]
COMPANY, REPORT_NO = "Nordlys IT ApS", "INC-2026-0142"


def add_signature_fields(pdf: bytes, boxes, password: str | None = None) -> bytes:
    w = IncrementalPdfFileWriter(io.BytesIO(pdf))
    if password:
        w.encrypt(password)
    for anchor, field_name, _, _, locks, _, _ in ROLES:
        page, box = boxes[anchor]
        fields.append_signature_field(w, fields.SigFieldSpec(
            field_name, on_page=page, box=box,
            field_mdp_spec=fields.FieldMDPSpec(fields.FieldMDPAction.ALL) if locks else None,
            doc_mdp_update_value=fields.MDPPerm.NO_CHANGES if locks else None,
        ))
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def appearance_style(kind: str, role: str, name: str, box, fonts: pathlib.Path, folder: pathlib.Path):
    """Render this signer's appearance as a one-page PDF the size of the box, for pyHanko to place."""
    when = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if kind == "stamp":
        body = appearances.stamp_html(COMPANY, role, name, when, REPORT_NO)
    else:
        body = appearances.handwritten_html(name, name, role, when)
    size = (box[2] - box[0], box[3] - box[1])
    path = appearances.render_appearance(body, size, fonts, LocalOnlyFetcher(fonts),
                                         folder / f"{role.lower().replace(' ', '-')}.pdf")
    return stamp.StaticStampStyle.from_pdf_file(str(path), border_width=0)


def sign_once(pdf: bytes, field_name: str, role: str, signer, tsa, vc, style,
              password: str | None = None) -> bytes:
    w = IncrementalPdfFileWriter(io.BytesIO(pdf))
    if password:
        w.encrypt(password)
    meta = PdfSignatureMetadata(
        field_name=field_name,
        md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        embed_validation_info=True,
        validation_context=vc,
        reason=f"{role} sign-off",
        location="Skjald",
    )
    pdf_signer = PdfSigner(meta, signer=signer, timestamper=tsa, stamp_style=style)
    out = io.BytesIO()
    pdf_signer.sign_pdf(w, output=out)
    return out.getvalue()


def sign_all(pdf: bytes, pki, tsa, vc, boxes, fonts, folder, password=None) -> tuple[list[bytes], list[float]]:
    revisions, seconds = [], []
    current = pdf
    for anchor, field_name, prefix, role, _, kind, name in ROLES:
        signer = signers.SimpleSigner.load(
            str(pki[f"{prefix}.key"]), str(pki[f"{prefix}.cert"]), ca_chain_files=(str(pki["root.cert"]),))
        start = time.perf_counter()
        style = appearance_style(kind, role, name, boxes[anchor][1], fonts, folder)
        current = sign_once(current, field_name, role, signer, tsa, vc, style, password)
        seconds.append(time.perf_counter() - start)
        revisions.append(current)
    return revisions, seconds


# --------------------------------------------------------------------------- checks


def validate(pdf: bytes, vc, password: str | None = None) -> list[dict]:
    reader = PdfFileReader(io.BytesIO(pdf))
    if password:
        reader.decrypt(password)
    results = []
    for sig in reader.embedded_signatures:
        try:
            status = asyncio.run(async_validate_pdf_signature(sig, vc, ts_validation_context=vc))
            results.append({
                "field": sig.field_name,
                "signer": status.signing_cert.subject.human_friendly,
                "intact": status.intact,
                "valid": status.valid,
                "trusted": status.trusted,
                "timestamp_ok": bool(status.timestamp_validity and status.timestamp_validity.valid
                                     and status.timestamp_validity.trusted),
                "coverage": status.coverage.name,
                "modifications": status.modification_level.name if status.modification_level else None,
                "docmdp_ok": status.docmdp_ok,
                "bottom_line": status.bottom_line,
            })
        except Exception as exc:  # a broken file is a result, not a crash
            results.append({"field": sig.field_name, "error": f"{type(exc).__name__}: {exc}", "bottom_line": False})
    return results


def offline_context(pdf: bytes, root_cert, password: str | None = None) -> ValidationContext:
    """A validation context built only from what is embedded in the PDF (its DSS)."""
    reader = PdfFileReader(io.BytesIO(pdf))
    if password:
        reader.decrypt(password)
    dss = DocumentSecurityStore.read_dss(reader)
    return dss.as_validation_context({
        "trust_roots": [root_cert], "allow_fetching": False, "revocation_mode": "hard-fail"})


def pdfa_markers(pdf: bytes) -> dict:
    reader = PdfFileReader(io.BytesIO(pdf))
    root = reader.root
    xmp = root["/Metadata"].data.decode("utf-8", "replace") if "/Metadata" in root else ""
    widgets_print_flag = []
    stamp_fonts_embedded = []
    acroform = root["/AcroForm"].get_object() if "/AcroForm" in root else None
    for field in (acroform["/Fields"] if acroform else []):
        field = field.get_object()
        if field.get("/FT") != "/Sig":
            continue
        widgets_print_flag.append(bool(int(field.get("/F", 0)) & 4))
        if "/AP" in field and "/V" in field:  # signed: inspect fonts in the appearance stream
            normal = field["/AP"].get_object()["/N"].get_object()
            stamp_fonts_embedded.append(_fonts_embedded(normal))
    return {
        "xmp_pdfa_part_3": "pdfaid:part>3<" in xmp.replace(" ", "") or 'pdfaid:part="3"' in xmp,
        "xmp_conformance_B": "pdfaid:conformance>B<" in xmp.replace(" ", "") or 'pdfaid:conformance="B"' in xmp,
        "output_intent": "/OutputIntents" in root,
        "need_appearances_off": not (acroform and acroform.get("/NeedAppearances", False)),
        "signature_widgets_printable": all(widgets_print_flag) if widgets_print_flag else None,
        "signature_fonts_embedded": all(stamp_fonts_embedded) if stamp_fonts_embedded else None,
        "encrypted": "/Encrypt" in reader.trailer,
    }


def _fonts_embedded(xobject, depth=0) -> bool:
    if depth > 5:
        return True
    resources = xobject["/Resources"].get_object() if "/Resources" in xobject else {}
    ok = True
    fonts = resources["/Font"].get_object() if "/Font" in resources else {}
    for font in fonts.values():
        font = font.get_object()
        target = font["/DescendantFonts"].get_object()[0].get_object() if "/DescendantFonts" in font else font
        descriptor = target["/FontDescriptor"].get_object() if "/FontDescriptor" in target else None
        if descriptor is None or not any(k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3")):
            ok = False
    xobjects = resources["/XObject"].get_object() if "/XObject" in resources else {}
    for inner in xobjects.values():
        ok = ok and _fonts_embedded(inner.get_object(), depth + 1)
    return ok


def qpdf_check(path: pathlib.Path, password: str | None = None) -> str:
    cmd = ["qpdf", "--check"] + ([f"--password={password}"] if password else []) + [str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return "ok" if result.returncode == 0 else f"exit {result.returncode}: {result.stdout.strip()[-200:]}"


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out"))
    args = parser.parse_args()
    out, fonts = args.out, args.fonts.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    # 1. Render
    start = time.perf_counter()
    _, draft_pdf, _ = render(fonts, draft=True)
    doc, final_pdf, refused = render(fonts, draft=False)
    report["render_seconds_both"] = round(time.perf_counter() - start, 2)
    report["refused_urls"] = refused
    (out / "1-draft.pdf").write_bytes(draft_pdf)
    (out / "2-final-unsigned.pdf").write_bytes(final_pdf)
    boxes = signature_boxes(doc)
    report["signature_boxes"] = boxes
    report["pages"] = len(doc.pages)
    report["pdfa_unsigned"] = pdfa_markers(final_pdf)

    # 2. PKI, timestamp authority, validation context
    pki = make_pki(out / "pki")
    root_cert = load_cert_from_pemder(str(pki["root.cert"]))
    tsa = DummyTimeStamper(
        tsa_cert=load_cert_from_pemder(str(pki["tsa.cert"])),
        tsa_key=load_private_key_from_pemder(str(pki["tsa.key"]), passphrase=None),
    )
    vc = ValidationContext(trust_roots=[root_cert], crls=[pki["crl"].read_bytes()],
                           allow_fetching=False, revocation_mode="hard-fail")

    # 3. Three signatures in a row
    prepared = add_signature_fields(final_pdf, boxes)
    revisions, seconds = sign_all(prepared, pki, tsa, vc, boxes, fonts, out / "appearances")
    for i, rev in enumerate(revisions, start=1):
        (out / f"3-signed-{i}-{ROLES[i - 1][2]}.pdf").write_bytes(rev)
    signed = revisions[-1]
    report["sign_seconds"] = [round(s, 3) for s in seconds]
    report["validation_final"] = validate(signed, vc)
    report["validation_offline_from_embedded_data"] = validate(signed, offline_context(signed, root_cert))
    report["pdfa_signed"] = pdfa_markers(signed)
    report["qpdf_signed"] = qpdf_check(out / "3-signed-3-company.pdf")
    report["size_kb"] = {"unsigned": len(final_pdf) // 1024, "signed": len(signed) // 1024}

    # 3b. Lock: a real change after the locking signature must be flagged
    w = IncrementalPdfFileWriter(io.BytesIO(signed))
    w.root["/Lang"] = generic.TextStringObject("da")  # was "en": a genuine edit to the catalog
    w.update_root()
    after_lock = io.BytesIO()
    w.write(after_lock)
    report["validation_after_post_lock_edit"] = validate(after_lock.getvalue(), vc)

    # 3c. Tamper: flip one byte inside the first, signed revision
    tampered = bytearray(signed)
    pos = len(final_pdf) // 2
    tampered[pos] = (tampered[pos] + 1) % 256
    (out / "4-tampered.pdf").write_bytes(tampered)
    report["validation_tampered"] = validate(bytes(tampered), vc)

    # 4a. Protected copy, approach A: encrypt the signed file afterwards (qpdf)
    enc_after = out / "5a-encrypted-after-signing.pdf"
    subprocess.run(["qpdf", "--encrypt", DELIVERY_PASSWORD, DELIVERY_PASSWORD + "-owner", "256", "--",
                    str(out / "3-signed-3-company.pdf"), str(enc_after)], check=True)
    report["protected_A_encrypt_after_signing"] = validate(enc_after.read_bytes(), vc, DELIVERY_PASSWORD)

    # 4b. Protected copy, approach B: encrypt first, then sign the encrypted copy
    copy_writer = copy_into_new_writer(PdfFileReader(io.BytesIO(final_pdf)))
    copy_writer.encrypt(DELIVERY_PASSWORD + "-owner", DELIVERY_PASSWORD)
    encrypted = io.BytesIO()
    copy_writer.write(encrypted)
    prepared_b = add_signature_fields(encrypted.getvalue(), boxes, DELIVERY_PASSWORD)
    revisions_b, seconds_b = sign_all(prepared_b, pki, tsa, vc, boxes, fonts, out / "appearances",
                                      DELIVERY_PASSWORD)
    (out / "5b-encrypted-then-signed.pdf").write_bytes(revisions_b[-1])
    report["protected_B_encrypt_then_sign"] = validate(revisions_b[-1], vc, DELIVERY_PASSWORD)
    report["protected_B_sign_seconds"] = [round(s, 3) for s in seconds_b]
    report["protected_B_markers"] = pdfa_markers_safe(revisions_b[-1])
    report["qpdf_protected_B"] = qpdf_check(out / "5b-encrypted-then-signed.pdf", DELIVERY_PASSWORD)

    (out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


def pdfa_markers_safe(pdf: bytes) -> dict:
    reader = PdfFileReader(io.BytesIO(pdf))
    return {"encrypted": "/Encrypt" in reader.trailer}


if __name__ == "__main__":
    main()
