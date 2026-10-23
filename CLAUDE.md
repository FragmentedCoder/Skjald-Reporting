# Working on Skjald

Skjald is a self-hosted report builder that stores sensitive customer data. Read `docs/architecture.md` before changing the design, and keep it current when the design changes.

## Workflow

- Work on a feature branch and open a pull request; never push to `main`.
- Keep pull requests focused and describe how the change was tested.
- Batch fixes into fewer, larger pull requests rather than many tiny ones; CI minutes are shared.

## Rules that always apply

- Never commit secrets, real customer data, certificates or private keys. Demo data and templates use a fictional company.
- The security baseline is OWASP ASVS Level 2. New endpoints need authentication, authorisation by role and assignment, input validation and audit logging.
- The PDF renderer must never get network access, and template expressions must never execute code.
- UI and reports follow `docs/brand/` (tokens, fonts, logo rules). UI labels are plain English, in sentence case.
