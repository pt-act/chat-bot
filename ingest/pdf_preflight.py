"""PDF parser preflight checks — validates environment readiness for OpenDataLoader.

All checks are non-raising. `preflight_check()` returns `(ok, reason)` so callers
can decide whether to proceed with ODL or fall back to PyPDF.
"""

import logging
import re
import subprocess

import requests

from config import get_settings

logger = logging.getLogger(__name__)


_RE_JAVA_VERSION = re.compile(r'version\s+"([0-9._]+)"')


def _parse_java_version(text: str) -> int | None:
    """Extract major Java version from `java -version` stderr/out.

    Handles legacy ``1.8`` style (returns 8) and modern ``11.0.21`` / ``17`` style.
    Returns ``None`` when no version token is found.
    """
    match = _RE_JAVA_VERSION.search(text)
    if not match:
        return None
    raw = match.group(1)
    # Legacy scheme: 1.8.0_202 → major 8
    if raw.startswith("1."):
        try:
            return int(raw.split(".")[1])
        except (IndexError, ValueError):
            return None
    # Modern scheme: 11.0.21, 17, 21.0.1 → major = first token
    try:
        return int(raw.split(".")[0])
    except (IndexError, ValueError):
        return None


def _java_available() -> tuple[bool, str]:
    """Check Java is installed and >= 11.

    Returns ``(ok, reason)`` where reason is empty when ok.
    """
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return False, "Java is not installed (java command not found)"
    except subprocess.TimeoutExpired:
        return False, "Java version check timed out"
    except Exception as exc:
        logger.warning("Unexpected error running java -version: %s", exc)
        return False, f"Java check failed: {exc}"

    combined = result.stdout + result.stderr
    major = _parse_java_version(combined)
    if major is None:
        return False, "Could not parse Java version from output"
    if major < 11:
        return False, f"Java {major} detected; Java 11+ is required for OpenDataLoader"
    return True, ""


def _odl_importable() -> tuple[bool, str]:
    """Check the ``opendataloader_pdf`` Python package is importable."""
    try:
        import opendataloader_pdf  # noqa: F401
    except ImportError as exc:
        return False, f"opendataloader_pdf package is not installed: {exc}"
    return True, ""


def _hybrid_reachable(url: str | None) -> tuple[bool, str]:
    """Check the hybrid sidecar server is reachable.

    Returns ``(ok, reason)`` — ok is ``True`` when no URL is configured
    (nothing to validate) or when the health endpoint responds 2xx.
    """
    if not url:
        return True, ""
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code < 200 or resp.status_code >= 300:
            return False, f"Hybrid server at {url} returned HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return False, f"Hybrid server at {url} is unreachable: {exc}"
    return True, ""


def preflight_check() -> tuple[bool, str]:
    """Return ``(True, "")`` if the environment can run OpenDataLoader; otherwise ``(False, reason)``.

    Checks, in order:
    1. Java 11+ is installed and on ``$PATH``.
    2. The ``opendataloader_pdf`` Python package is importable.
    3. If ``ODL_HYBRID`` is configured, the hybrid server URL is reachable.

    This function never raises. The returned ``reason`` is safe to log and
    expose to operators (no file paths, no secrets).
    """
    ok, reason = _java_available()
    if not ok:
        return ok, reason

    ok, reason = _odl_importable()
    if not ok:
        return ok, reason

    settings = get_settings()
    if settings.odl_hybrid:
        ok, reason = _hybrid_reachable(settings.odl_hybrid_url)
        if not ok:
            if settings.odl_hybrid_fallback:
                logger.warning("Hybrid server unreachable (%s); fallback to local ODL enabled.", reason)
                return True, ""  # Local ODL is still viable
            return False, reason

    return True, ""
