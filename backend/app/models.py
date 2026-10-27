"""Imports every module that defines tables, so Base.metadata is complete for migrations."""

import app.audit
import app.audit_stamps
import app.auth.mfa
import app.auth.sessions
import app.backgrounds
import app.customers
import app.images
import app.jobs
import app.library.models
import app.policy
import app.projects
import app.roles
import app.styles.models
import app.templates.models
import app.users  # noqa: F401
