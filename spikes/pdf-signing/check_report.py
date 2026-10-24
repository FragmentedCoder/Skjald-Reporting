"""Check a signed report: the logic behind Skjald's "Check a signed report" tool.

Answers what a technician needs to know about a PDF someone sends back:
are the signatures intact and trusted, when and by whom was it signed, was
anything changed afterwards, is it still PDF/A, and is this exact file one
Skjald issued (by SHA-256 against the archive).

    python check_report.py out/3-signed-3-company.pdf --trust out/pki/root.cert.pem \
        --crl out/pki/ca.crl --issued out/3-signed-3-company.pdf=INC-2026-0142 --json result.json

Spike code: in the product this runs in the signer container, and the archive
lookup is a query on the reports table.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import pathlib

from pyhanko.keys import load_cert_from_pemder
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

# What changed after a signature, in plain words. pyHanko's levels are cumulative.
CHANGES = {
    "NONE": "Nothing",
    "LTA_UPDATES": "Only validation data was added",
    "FORM_FILLING": "Only later signatures were added",
    "ANNOTATIONS": "Comments or annotations were added",
    "OTHER": "The content was changed",
}
ROLES = {"Sig_Technician": "Technician", "Sig_Reviewer": "Reviewer", "Sig_Company": "Company seal"}


def name_parts(subject) -> dict:
    """Common name and organisation from a certificate subject."""
    values = subject.native
    return {"name": values.get("common_name", ""), "organisation": values.get("organization_name", "")}


def check(pdf: bytes, vc: ValidationContext, issued: dict[str, str]) -> dict:
    sha256 = hashlib.sha256(pdf).hexdigest()
    result = {"sha256": sha256, "size_kb": round(len(pdf) / 1024), "issued_as": issued.get(sha256)}
    try:
        reader = PdfFileReader(io.BytesIO(pdf))
    except Exception as exc:  # not a PDF, or too damaged to read
        return {**result, "verdict": "unreadable", "error": f"{type(exc).__name__}: {exc}", "signatures": []}

    root = reader.root
    meta = root.get("/Metadata")
    xmp = meta.get_object().data.decode("utf-8", "replace") if meta is not None else ""
    result["pdfa"] = 'pdfaid:part="3"' in xmp or "<pdfaid:part>3</pdfaid:part>" in xmp
    result["pages"] = int(root["/Pages"]["/Count"])

    signatures = []
    for sig in reader.embedded_signatures:
        entry = {"field": sig.field_name, "role": ROLES.get(sig.field_name, sig.field_name)}
        try:
            status = asyncio.run(async_validate_pdf_signature(sig, vc, ts_validation_context=vc))
            ts = status.timestamp_validity
            level = status.modification_level.name if status.modification_level else "OTHER"
            entry.update({
                **name_parts(status.signing_cert.subject),
                "signed_at": (ts.timestamp if ts else status.signer_reported_dt).isoformat(),
                "timestamp_trusted": bool(ts and ts.valid and ts.trusted),
                "timestamp_by": name_parts(ts.signing_cert.subject)["name"] if ts else None,
                "intact": status.intact,
                "trusted": status.trusted,
                "changes_after": CHANGES.get(level, level),
                "change_level": level,
                "ok": bool(status.bottom_line),
            })
        except Exception as exc:  # a broken signature is a result, not a crash
            entry.update({"ok": False, "intact": False, "trusted": False, "error": f"{type(exc).__name__}: {exc}"})
        signatures.append(entry)
    result["signatures"] = signatures

    if not signatures:
        result["verdict"] = "unsigned"
    elif not all(s.get("intact") for s in signatures):
        result["verdict"] = "changed"  # the signed bytes no longer match
    elif any(s.get("change_level") in ("ANNOTATIONS", "OTHER") for s in signatures):
        result["verdict"] = "changed"  # edits were added after signing
    elif not all(s.get("trusted") for s in signatures):
        result["verdict"] = "untrusted"
    else:
        result["verdict"] = "valid" if all(s["ok"] for s in signatures) else "invalid"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=pathlib.Path)
    parser.add_argument("--trust", type=pathlib.Path, required=True, help="trusted root certificate (PEM)")
    parser.add_argument("--crl", type=pathlib.Path, help="revocation list for the test CA")
    parser.add_argument("--issued", action="append", default=[], help="FILE=REPORT: a file Skjald issued, for the archive lookup")
    parser.add_argument("--json", type=pathlib.Path, help="write the result here as JSON")
    args = parser.parse_args()

    vc = ValidationContext(trust_roots=[load_cert_from_pemder(str(args.trust))],
                           crls=[args.crl.read_bytes()] if args.crl else [], allow_fetching=False)
    issued = {}
    for item in args.issued:
        file, report = item.split("=", 1)
        issued[hashlib.sha256(pathlib.Path(file).read_bytes()).hexdigest()] = report

    result = {"file": args.pdf.name, **check(args.pdf.read_bytes(), vc, issued)}
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"{args.pdf.name}: {result['verdict']}, {len(result['signatures'])} signatures, "
          f"issued as {result['issued_as'] or 'nothing in the archive'}")


if __name__ == "__main__":
    main()
