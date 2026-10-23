# Spike: PDF/A rendering and sequential signatures

**Result: the pipeline works.** WeasyPrint renders a branded PDF/A-3b report, and pyHanko adds technician, reviewer and company-seal signatures in a row. All three stay valid, carry trusted timestamps, validate offline from the data embedded in the file, and the last one locks the document. One design change came out of it: a password-protected delivery copy has to be encrypted **before** it is signed, not after.

This is throw-away spike code that proves the approach. It is not product code.

## What was tested

| Check | Result |
| --- | --- |
| Render a two-page incident report as PDF/A-3b with Marcellus and IBM Plex, header, footer, "Page X of Y", TLP label, status pills, Æ ø å | Works; 0.4 s for draft and final together |
| DRAFT watermark on every page of the draft | Works |
| Renderer refuses network access (the sample contains an `<img>` pointing at an outside address) | Refused; only files in the font folder can be read |
| Place signature fields exactly where the layout put the sign-off boxes | Works, using WeasyPrint's anchor boxes for the `#sig-…` elements |
| Three signatures in a row: technician, reviewer, company seal (ECDSA P-256, built-in test CA) | All three valid, intact and trusted |
| Trusted timestamp (RFC 3161) on every signature | Valid on all three |
| Validate offline, using only the revocation data embedded in the PDF | All three valid |
| PDF/A markers after signing: XMP part 3 / conformance B, output intent, printable signature widgets, embedded fonts in the signature stamps, no encryption | All present |
| Last signature locks the document; a real edit afterwards | Edit detected; all signatures report the document as modified |
| One byte changed inside the signed content | Detected; all signatures fail |
| `qpdf --check` on the signed file | Passes |
| Signing time | 0.08–0.13 s per signature |
| File size | 26 KB unsigned, 94 KB with three signatures and embedded validation data |

## Password-protected delivery copy

| Approach | Result |
| --- | --- |
| A. Encrypt the signed PDF afterwards (qpdf, AES-256) | **Breaks every signature.** Encryption rewrites the bytes the signatures cover. |
| B. Encrypt the unsigned PDF first, then sign the encrypted copy three times | **Works.** All three signatures valid, timestamped and trusted. |

So the design changes: when a report enters Signing and its template allows password-protected delivery, Skjald generates the delivery password, stores it encrypted with the customer key, and each signer signs both the PDF/A original and the encrypted copy in one action. The original stays unencrypted, because PDF/A does not allow encryption. The password is shown to the technician once, at delivery, as decided in D4.

## Findings for the real build

- **Create every signature field before the first signature.** The lock on the last field has to exist from the start; adding fields later counts as a change to signed content.
- **Timestamps in production need an independent TSA.** The spike used pyHanko's in-process test TSA (RSA only). Skjald should call a public RFC 3161 service, configured per install, so timestamps don't depend on Skjald's own clock.
- **Signature stamps need a design pass.** The stamp text uses an embedded IBM Plex subset, so PDF/A holds, but layout and styling are still plain.
- **Bundle the full fonts.** The spike uses the Latin subsets from Fontsource, which cover Danish but little beyond it.

## Still to check

- **veraPDF validation.** The sandbox could not download veraPDF, so the PDF/A checks above are markers, not a full validation. Run veraPDF in CI before Phase 1.
- **Adobe Acrobat.** Open the signed file in Acrobat Reader, trust the test root and confirm that all three signatures and the lock show as expected. ECDSA P-256 signatures and the RFC 9336 document-signing EKU should be accepted, but this needs a real check.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
npm pack @fontsource/marcellus @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono
for f in fontsource-*.tgz; do mkdir -p "${f%.tgz}" && tar -xzf "$f" -C "${f%.tgz}"; done
.venv/bin/python make_fonts.py . fonts/
.venv/bin/python spike.py --fonts fonts --out out
```

`out/` gets the draft, the unsigned and signed PDFs, the tampered and encrypted variants, `report.json`, and a throw-away test PKI. Never commit `out/`; it holds private keys.
