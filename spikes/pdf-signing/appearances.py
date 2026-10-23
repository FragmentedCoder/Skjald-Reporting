"""Signature appearances, rendered as tiny HTML pages by the same renderer as the reports.

Two styles, chosen per signer in the template:

- "stamp": a company stamp with company name, role, date and time, and report number.
- "handwritten": the signer's signature above a rule, with name, role and time underneath.
  In the product the signature comes from the user's profile: drawn (an SVG path captured
  in the browser), uploaded, or generated from their name in a handwriting-style font.
  The spike uses the generated version.

Each appearance is rendered to a one-page PDF exactly the size of the signature box,
and pyHanko places that page as the signature's visible appearance.
"""

from __future__ import annotations

import html
import pathlib

from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

APPEARANCE_CSS = """
@font-face { font-family: 'IBM Plex Sans'; src: url('IBMPlexSans-Regular.ttf'); font-weight: 400; }
@font-face { font-family: 'IBM Plex Sans'; src: url('IBMPlexSans-SemiBold.ttf'); font-weight: 600; }
@font-face { font-family: 'Signature'; src: url('MrDafoe-Regular.ttf'); }
html, body { margin: 0; padding: 0; height: 100%; }

/* Stamp: Fjord-blue "ink", double frame, like a company stamp */
.stamp { box-sizing: border-box; height: 100%; padding: 2.5pt; border: 1.4pt solid #2B5D8A; border-radius: 7pt; }
.stamp-inner { box-sizing: border-box; height: 100%; border: 0.5pt solid #2B5D8A; border-radius: 5pt;
               padding: 0 6pt; text-align: center; color: #2B5D8A; font-family: 'IBM Plex Sans';
               display: flex; flex-direction: column; justify-content: center; }
.stamp .company { font-weight: 600; font-size: 8.5pt; letter-spacing: 0.14em; }
.stamp .signed { font-size: 6.5pt; letter-spacing: 0.08em; margin-top: 2pt; }
.stamp .who { font-size: 7pt; margin-top: 2pt; }
.stamp .when { font-size: 6.5pt; margin-top: 2pt; }

/* Handwritten: Midnat ink above a hairline, details in IBM Plex underneath */
.hand { box-sizing: border-box; height: 100%; padding: 0 6pt; font-family: 'IBM Plex Sans'; color: #0F1B2D; }
.hand .sig { font-family: 'Signature'; font-size: 25pt; line-height: 1; height: 30pt; padding-top: 6pt;
             color: #1B2F55; white-space: nowrap; }
.hand .rule { border-top: 0.5pt solid #8A94A3; margin-top: 2pt; }
.hand .who { font-size: 7pt; font-weight: 600; margin-top: 3pt; }
.hand .when { font-size: 6.5pt; color: #5B6675; }
"""


def stamp_html(company: str, role: str, name: str, when: str, report_no: str) -> str:
    e = html.escape
    who = "" if name == company else f'\n  <div class="who">{e(name)}</div>'
    return f"""<div class="stamp"><div class="stamp-inner">
  <div class="company">{e(company.upper())}</div>
  <div class="signed">DIGITALLY SIGNED &#183; {e(role.upper())}</div>{who}
  <div class="when">{e(when)} &#183; {e(report_no)}</div>
</div></div>"""


def handwritten_html(signature_text: str, name: str, role: str, when: str) -> str:
    e = html.escape
    return f"""<div class="hand">
  <div class="sig">{e(signature_text)}</div>
  <div class="rule"></div>
  <div class="who">{e(name)} &#183; {e(role)}</div>
  <div class="when">Digitally signed {e(when)}</div>
</div>"""


def render_appearance(body: str, size_pt: tuple[float, float], fonts: pathlib.Path, url_fetcher,
                      target: pathlib.Path) -> pathlib.Path:
    width, height = size_pt
    font_config = FontConfiguration()
    page_css = f"@page {{ size: {width}pt {height}pt; margin: 0; }}"
    css = CSS(string=APPEARANCE_CSS + page_css, base_url=f"{fonts.as_uri()}/", font_config=font_config,
              url_fetcher=url_fetcher)
    doc = HTML(string=f"<!doctype html><html><body>{body}</body></html>", base_url=f"{fonts.as_uri()}/",
               url_fetcher=url_fetcher).render(stylesheets=[css], font_config=font_config)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.write_pdf(target, pdf_variant="pdf/a-3b")
    return target
