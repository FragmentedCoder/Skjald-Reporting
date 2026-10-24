# Spike: PDF/A rendering and sequential signatures

**Result: the pipeline works.** WeasyPrint renders a branded PDF/A-3b report, and pyHanko adds technician, reviewer and company-seal signatures in a row. All three stay valid, carry trusted timestamps, validate offline from the data embedded in the file, and the last one locks the document. One design change came out of it: a password-protected delivery copy has to be encrypted **before** it is signed, not after.

This is throw-away spike code that proves the approach. It is not product code.

## What was tested

| Check | Result |
| --- | --- |
| Render a five-page incident report as PDF/A-3b with Marcellus and IBM Plex, header, footer, "Page X of Y", TLP label, status pills, Æ ø å | Works; 0.4 s for draft and final together |
| Every major section starts on its own page; headings never sit alone at a page foot, table rows never split, table headers repeat | Works with plain CSS (`break-before: page`, `break-after: avoid`, `break-inside: avoid`) |
| DRAFT watermark on every page of the draft | Works |
| Renderer refuses network access (the sample contains an `<img>` pointing at an outside address) | Refused; only files in the font folder can be read |
| Place signature fields exactly where the layout put the sign-off boxes | Works, using WeasyPrint's anchor boxes for the `#sig-…` elements |
| Three signatures in a row: technician, reviewer, company seal (ECDSA P-256, built-in test CA) | All three valid, intact and trusted |
| Trusted timestamp (RFC 3161) on every signature | Valid on all three |
| Validate offline, using only the revocation data embedded in the PDF | All three valid |
| PDF/A markers after signing: XMP part 3 / conformance B, output intent, printable signature widgets, embedded fonts in the signature appearances, no encryption | All present |
| Last signature locks the document; a real edit afterwards | Edit detected; all signatures report the document as modified |
| One byte changed inside the signed content | Detected; all signatures fail |
| `qpdf --check` on the signed file | Passes |
| Visible signatures: handwritten style for technician and reviewer, company stamp for the seal | Works; appearances are tiny HTML pages rendered by the same renderer, so they use the brand fonts and colours and keep PDF/A intact |
| Signing time | 0.14–0.24 s per signature, including rendering its appearance |
| File size | 26 KB unsigned, 111 KB with three signatures, their appearances and embedded validation data |

## Signature appearances

Each template sets, per signer, how the visible signature looks. `appearances.py` renders the appearance as a one-page PDF exactly the size of the sign-off box, and pyHanko places it as the signature's appearance.

| Style | Looks like | Used for in the spike |
| --- | --- | --- |
| Handwritten | The signature in Midnat ink above a hairline, with name, role and signing time underneath | Technician and reviewer |
| Stamp | A Fjord-blue double-framed company stamp with company name, role, signing time and report number | Company seal |

In the product the handwritten signature comes from the user's profile: drawn in the browser (stored as an SVG path), uploaded as a scan, or generated from their name in a handwriting-style font. The spike uses the generated version, set in Mr Dafoe (SIL OFL). The picture only shows who signed; the cryptographic signature underneath is what proves it.

## Password-protected delivery copy

| Approach | Result |
| --- | --- |
| A. Encrypt the signed PDF afterwards (qpdf, AES-256) | **Breaks every signature.** Encryption rewrites the bytes the signatures cover. |
| B. Encrypt the unsigned PDF first, then sign the encrypted copy three times | **Works.** All three signatures valid, timestamped and trusted. |

So the design changes: when a report enters Signing and its template allows password-protected delivery, Skjald generates the delivery password, stores it encrypted with the customer key, and each signer signs both the PDF/A original and the encrypted copy in one action. The original stays unencrypted, because PDF/A does not allow encryption. The password is shown to the technician once, at delivery, as decided in D4.

## Findings for the real build

- **Create every signature field before the first signature.** The lock on the last field has to exist from the start; adding fields later counts as a change to signed content.
- **Timestamps in production need an independent TSA.** The spike used pyHanko's in-process test TSA (RSA only). Skjald should call a public RFC 3161 service, configured per install, so timestamps don't depend on Skjald's own clock.
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
