<p align="center">
  <img src="docs/brand/skjald-mark.svg" width="96" height="96" alt="Skjald">
</p>

<h1 align="center">Skjald</h1>

<p align="center"><em>Reports worth keeping.</em></p>

Skjald is a self-hosted, template-driven report builder for IT, MSP and security work: security incident reports, storage device destruction certificates, vulnerability assessments and similar. A technician picks a customer project and a template, answers the template's questions, reviews the generated PDF, signs it and delivers it to the customer.

A *skald* (Danish *skjald*) was the Norse poet who turned events into a lasting record. Skjald does the same for technical work.

> [!NOTE]
> **Status: early development.** There is nothing to install yet. Watch the repository to hear about the first release.

## What it will do

- **Template builder** — a question form, a drag-and-drop document layout, and visual logic (IF / ELSE IF / ELSE, SWITCH, AND / OR / XOR, regular expressions, text replacement) on top of a sandboxed expression language that never runs code.
- **Auto-fill** — customer and project details are typed once and filled into every report. Lookup tables cover things like CVSS severity and end-of-life dates.
- **Signed reports** — PDF/A output with PAdES signatures, trusted timestamps and long-term validation. Technician, reviewer and company signatures, set per template.
- **Delivery** — download, email, password-protected PDF, or an expiring secure link with an access code.
- **Security first** — per-customer encryption keys, MFA for every account, need-to-know access and a tamper-evident audit log.
- **Templates as files** — export, import and share templates as single `.skjald` files.
- **Easy to run** — one command installs it on an Ubuntu VM with Docker Compose. Updates take a backup first and roll back on failure; backups are encrypted and restore-tested.

## Roadmap

| Release | Scope |
| --- | --- |
| 1.0 | Platform (installer, sign-in, MFA, roles, admin), template builder, reports end to end with signing and delivery, three built-in templates |
| 1.1 | Secure links through the Bifrost delivery gateway |
| 1.2 | Active Directory (LDAPS) and Microsoft Entra ID sign-in; API |
| 1.3 | Importers (Nmap, OpenVAS / Greenbone, Nessus), vulnerability data feeds, more built-in templates |
| 1.4 | HSM support, syslog / SIEM forwarding, custom fonts |

The design is described in [docs/architecture.md](docs/architecture.md).

## Tech stack

SvelteKit and TypeScript · Python and FastAPI · SQLite with SQLCipher · WeasyPrint · pyHanko · Caddy · Docker Compose

## Contributing and security

Ideas, questions and bug reports are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please report security problems privately as described in [SECURITY.md](SECURITY.md), never in a public issue.

## Licence

Skjald is licensed under the [GNU Affero General Public License v3.0](LICENSE). You may use, study, change and share it. If you share a modified version, or run one as a service for others, you must publish its source under the same licence.
