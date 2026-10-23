"""The sample report used by the spike: a security incident report for a fictional customer.

All names, addresses and numbers are invented.
"""

REPORT_CSS = """
@font-face { font-family: 'Marcellus'; src: url('Marcellus-Regular.ttf'); font-weight: 400; }
@font-face { font-family: 'IBM Plex Sans'; src: url('IBMPlexSans-Regular.ttf'); font-weight: 400; }
@font-face { font-family: 'IBM Plex Sans'; src: url('IBMPlexSans-Medium.ttf'); font-weight: 500; }
@font-face { font-family: 'IBM Plex Sans'; src: url('IBMPlexSans-SemiBold.ttf'); font-weight: 600; }
@font-face { font-family: 'IBM Plex Mono'; src: url('IBMPlexMono-Medium.ttf'); font-weight: 500; }

@page {
  size: A4;
  margin: 25mm 20mm 25mm 20mm;
  @top-left { content: "INCIDENT \\00B7  INC-2026-0142"; font: 600 8pt 'IBM Plex Sans'; letter-spacing: 0.12em; color: #5B6675; }
  @top-right { content: "TLP:AMBER \\00B7  Fortroligt"; font: 600 8pt 'IBM Plex Sans'; color: #8A5A12; }
  @bottom-left { content: "Nordlys IT ApS \\00B7  Made with Skjald"; font: 400 8pt 'IBM Plex Sans'; color: #5B6675; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 400 8pt 'IBM Plex Sans'; color: #5B6675; }
}
@page :first { @top-left { content: none; } }

html { font-family: 'IBM Plex Sans'; font-size: 10.5pt; line-height: 1.55; color: #0F1B2D; }
h1, h2, h3 { font-family: 'Marcellus'; font-weight: 400; color: #0F1B2D; }
h1 { font-size: 26pt; line-height: 1.15; margin: 0 0 6pt; }
h2 { font-size: 16pt; margin: 22pt 0 6pt; }
h3 { font-size: 12.5pt; margin: 16pt 0 4pt; }
.overline { font-weight: 600; font-size: 8pt; letter-spacing: 0.12em; color: #5B6675; }
.lead { font-size: 12pt; color: #5B6675; }
.mark { width: 34pt; height: 34pt; margin-bottom: 18pt; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0; }
th { text-align: left; font-weight: 600; font-size: 9pt; background: #EFEFEF; }
th, td { padding: 5pt 7pt; border-bottom: 0.5pt solid #E5E5E5; vertical-align: top; }
code, .mono { font-family: 'IBM Plex Mono'; font-weight: 500; font-size: 9pt; }
.pill { display: inline-block; padding: 1pt 7pt; border-radius: 99pt; font-weight: 600; font-size: 8.5pt; }
.critical { background: #F9E3E0; color: #A3352A; }
.warning { background: #FBEFD9; color: #8A5A12; }
.ok { background: #E3F1E8; color: #2F6B47; }
/* Readability: every major section starts on its own page, and nothing awkward splits */
.major { break-before: page; }
.major > .overline + h2 { margin-top: 4pt; }
h2, h3 { break-after: avoid; }
tr, .pill, .callout { break-inside: avoid; }
thead { display: table-header-group; }
p { orphans: 3; widows: 3; }
.callout { border: 0.5pt solid #E5E5E5; border-radius: 6pt; background: #EFEFEF; padding: 8pt 10pt; margin: 10pt 0; }
.sigrow { margin-top: 18pt; display: flex; gap: 12pt; }
.sigbox { width: 150pt; height: 72pt; border: 0.75pt dashed #8A94A3; border-radius: 6pt; }
.draft { position: fixed; top: 95mm; left: 0; width: 100%; text-align: center; font: 600 96pt 'IBM Plex Sans';
         color: rgba(200, 134, 42, 0.14); transform: rotate(-30deg); }
.blocked-image { width: 1pt; height: 1pt; }
"""

MARK_SVG = (
    '<svg class="mark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">'
    '<rect width="160" height="160" rx="36" fill="#0F1B2D"/>'
    '<path d="M62 36 V124 M62 40 L98 64 M62 64 L98 88" fill="none" stroke="#C8862A" '
    'stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def report_html(draft: bool) -> str:
    watermark = '<div class="draft">DRAFT</div>' if draft else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Security incident report INC-2026-0142</title>
<meta name="author" content="Nordlys IT ApS"></head>
<body>
{watermark}
{MARK_SVG}
<div class="overline">INCIDENT &#183; INC-2026-0142</div>
<h1>Security incident report</h1>
<p class="lead">Fjordvik Logistik A/S &#183; Credential stuffing against the customer portal</p>

<table>
  <tr><th>Customer</th><td>Fjordvik Logistik A/S, CVR 00000000, Havnevej 1, 9999 Fjordvik</td></tr>
  <tr><th>Detected</th><td>2026-10-21 03:14 CEST</td></tr>
  <tr><th>Severity</th><td><span class="pill critical">Critical</span></td></tr>
  <tr><th>NIS2 deadlines</th><td>Early warning by 2026-10-22 03:14 &#183; notification by 2026-10-24 03:14 &#183; final report by 2026-11-21</td></tr>
  <tr><th>Technician</th><td>Freja Holm</td></tr>
</table>

<h2>Summary</h2>
<p>Between 03:14 and 04:02, 1 842 sign-in attempts against the customer portal used credentials from a known
breach list. Twelve accounts were locked automatically; no account was taken over. The attacking addresses were
blocked at the firewall at 04:05, and all affected users have reset their passwords. Æ, ø and å render correctly.</p>

<section class="major">
  <div class="overline">SECTION 2</div>
  <h2>Timeline</h2>
  <table>
    <thead><tr><th>Time (CEST)</th><th>Event</th></tr></thead>
    <tr><td class="mono">2026-10-21 03:14</td><td>First failed sign-in from 198.51.100.23</td></tr>
    <tr><td class="mono">2026-10-21 03:21</td><td>Monitoring alert: sign-in failures above threshold</td></tr>
    <tr><td class="mono">2026-10-21 03:38</td><td>On-call technician starts investigation</td></tr>
    <tr><td class="mono">2026-10-21 04:02</td><td>Last attempt recorded</td></tr>
    <tr><td class="mono">2026-10-21 04:05</td><td>Both addresses blocked at the firewall</td></tr>
    <tr><td class="mono">2026-10-21 09:30</td><td>Customer informed; password resets started</td></tr>
  </table>
</section>

<section class="major">
  <div class="overline">SECTION 3</div>
  <h2>Attacking addresses</h2>
  <table>
    <thead><tr><th>Address</th><th>Attempts</th><th>Status</th></tr></thead>
    <tr><td class="mono">198.51.100.23</td><td>1 204</td><td><span class="pill ok">Blocked</span></td></tr>
    <tr><td class="mono">203.0.113.77</td><td>611</td><td><span class="pill ok">Blocked</span></td></tr>
    <tr><td class="mono">2001:db8::5</td><td>27</td><td><span class="pill warning">Monitoring</span></td></tr>
  </table>
  <!-- The renderer must refuse this: no network access, ever. -->
  <img class="blocked-image" src="http://198.51.100.200/tracker.png" alt="">
</section>

<section class="major">
  <div class="overline">SECTION 4</div>
  <h2>Actions taken</h2>
  <p>Firewall rules were added for both addresses, rate limiting was tightened on the portal, and MFA enforcement
  was brought forward for all portal users.</p>
  <div class="callout">Log excerpt: <code>2026-10-21T03:14:07Z auth fail user=a.berg src=198.51.100.23</code></div>
  <h3>Recommendations</h3>
  <p>Require MFA for every portal account by 2026-11-01, add the breach-list check to password changes, and review
  the alert threshold so a similar attack raises an alarm within five minutes.</p>
</section>

<section class="major">
  <div class="overline">SIGN-OFF</div>
  <h2>Signatures</h2>
  <p>This report is signed by the technician, countersigned by the reviewer and sealed by Nordlys IT ApS.
  Each signature carries a trusted timestamp.</p>
  <div class="sigrow">
    <div class="sigbox" id="sig-technician"></div><div class="sigbox" id="sig-reviewer"></div><div class="sigbox" id="sig-company"></div>
  </div>
</section>
</body></html>"""
