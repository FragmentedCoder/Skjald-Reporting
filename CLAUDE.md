# Working on Skjald

Skjald is a self-hosted report builder that stores sensitive customer data. Read `docs/architecture.md` before changing the design, and keep it current when the design changes.

## Workflow

- One branch per phase or larger milestone (for example `phase-2`), merged into `main` only when the whole phase is tested. It changes only by pull requests and by merging `main` into it; never push to `main` or a phase branch directly.
- Work for a phase goes on a branch from the phase branch, named for what it is (`phase-2-fix/…`, `phase-2-feature/…`, `phase-2-hunt/…`), with many small, focused commits, and back into the phase branch by pull request.
- Small changes that can't wait for the phase (`hotfix/…`, `docs/…`, `maintenance/…`) branch from `main` and go back into `main` by pull request; then merge `main` into the phase branch.
- See "Branches" in CONTRIBUTING.md.
- Open the pull request as a draft early so progress can be followed, and mark it ready only when everything in it is tested.
- Describe in the pull request what changed and how it was tested.

## Rules that always apply

- Never commit secrets, real customer data, certificates or private keys. Demo data and templates use a fictional company.
- The security baseline is OWASP ASVS Level 2. New endpoints need authentication, authorisation by role and assignment, input validation and audit logging.
- The PDF renderer must never get network access, and template expressions must never execute code.
- UI and reports follow `docs/brand/` (tokens, fonts, logo rules). UI labels are plain English, in sentence case.
