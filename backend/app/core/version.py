"""Application version detection.

APP_VERSION is set by Docker build at image creation time. When running from
source or without CI stamping, it defaults to "dev" and disables the
version-check banner.
"""
import os
import re

from packaging.version import InvalidVersion, Version

APP_VERSION: str = os.getenv("APP_VERSION", "dev")

_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-.+].*)?$")


def is_semver_build() -> bool:
    """True iff APP_VERSION looks like a semantic version."""
    return bool(_SEMVER_RE.match(APP_VERSION))


def parse_current() -> Version | None:
    """Return the parsed current version, or None for dev/SHA builds."""
    if not is_semver_build():
        return None
    try:
        return Version(APP_VERSION.lstrip("v"))
    except InvalidVersion:
        return None
