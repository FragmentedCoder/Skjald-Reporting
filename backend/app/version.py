"""Which Skjald this is."""

import importlib.metadata
import os


def skjald_version() -> str:
    """The release the image was built as (or, built from a checkout, what git calls
    that commit); without either, the package's version marked as a development build."""
    built = os.environ.get("SKJALD_VERSION", "").strip()
    return built or f"{importlib.metadata.version('skjald-backend')}-dev"
