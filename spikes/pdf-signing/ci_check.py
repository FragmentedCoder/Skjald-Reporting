"""Fail CI unless the signing spike produced the expected results (reads out/report.json)."""

import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "out/report.json").read_text())
failures = []


def all_valid(key):
    rows = report[key]
    if not rows or not all(row.get("bottom_line") for row in rows):
        failures.append(f"{key}: expected every signature to be valid")


def none_valid(key):
    if any(row.get("bottom_line") for row in report[key]):
        failures.append(f"{key}: expected every signature to be rejected")


all_valid("validation_final")
all_valid("validation_offline_from_embedded_data")
all_valid("protected_B_encrypt_then_sign")
none_valid("validation_after_post_lock_edit")
none_valid("validation_tampered")
none_valid("protected_A_encrypt_after_signing")
for marker, value in report["pdfa_signed"].items():
    expected = marker != "encrypted"
    if value is not expected:
        failures.append(f"pdfa_signed.{marker} is {value}, expected {expected}")
if not report["refused_urls"]:
    failures.append("the renderer did not refuse the outside URL")
if report["qpdf_signed"] != "ok":
    failures.append(f"qpdf check failed: {report['qpdf_signed']}")

if failures:
    print("\n".join(failures))
    sys.exit(1)
print(f"signing spike ok: {len(report['validation_final'])} signatures valid, {report['pages']} pages")
