"""
US Location Filter.

Filters job listings to United States locations only.
Includes Remote/Hybrid jobs. Excludes known non-US locations.
Uses config/us_locations.json for patterns.
"""

import json
import re
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "us_locations.json"

# Load patterns
_config = {}
if CONFIG_FILE.exists():
    _config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

_INCLUDE = [p.lower() for p in _config.get("include_patterns", [])]
_EXCLUDE = [p.lower() for p in _config.get("exclude_patterns", [])]

# Pre-compile word-boundary patterns for 2-letter state codes to avoid false matches
_STATE_CODES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}


def is_us_location(location: str) -> bool:
    """Check if a job location is in the United States.

    Args:
        location: Location string from job listing.

    Returns:
        True if US/Remote/Unknown, False if clearly non-US.
    """
    if not location:
        return True  # Unknown locations: include rather than exclude

    loc_lower = location.lower().strip()

    # Empty or generic
    if loc_lower in ("", "unknown", "n/a", "various", "multiple"):
        return True

    # Quick exclude: check for non-US countries/cities first
    for exc in _EXCLUDE:
        if exc in loc_lower:
            return False

    # Check for US patterns (longer strings first for accuracy)
    for inc in _INCLUDE:
        if len(inc) > 2 and inc in loc_lower:
            return True

    # Check 2-letter state codes with word boundary
    # e.g., "San Francisco, CA" → match "CA"
    words = re.findall(r'\b[A-Za-z]{2}\b', location)
    for word in words:
        if word.lower() in _STATE_CODES:
            return True

    # If no match at all, include it (better to over-include than miss US jobs)
    return True
