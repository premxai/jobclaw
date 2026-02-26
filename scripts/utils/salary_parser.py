"""
Salary & Experience Parser — Ported from stapply-ai/data with improvements.

Extracts salary ranges and experience requirements from raw job description
text using regex pattern matching with false-positive filtering.

Usage:
    from scripts.utils.salary_parser import extract_salary, extract_experience, parse_salary_range

    salary_str, context = extract_salary(description_text)
    # salary_str: "$130,900-$177,100"  context: "...base salary range: $130,900-$177,100 per year..."

    years, context = extract_experience(description_text)
    # years: 3, context: "...3+ years of experience in..."

    salary_min, salary_max, currency = parse_salary_range("$130,900-$177,100")
    # 130900.0, 177100.0, "USD"
"""

import re
import html
from typing import Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════
# FALSE-POSITIVE FILTERS
# ═══════════════════════════════════════════════════════════════════════

_FALSE_POSITIVE_PATTERNS = [
    r"\b(billion|billions)\s+.*?\$",
    r"\$\s*\d+(?:,\d+)*(?:[km])?\s+in\s+revenue",
    r"\$\s*\d+(?:,\d+)*(?:[km])?\s+revenue",
    r"\$\s*\d+(?:,\d+)*(?:[km])?\s+arr\b",
]


def _is_false_positive(context: str) -> bool:
    """Check if salary match is actually company revenue or valuation."""
    context_lower = context.lower()
    for pattern in _FALSE_POSITIVE_PATTERNS:
        if re.search(pattern, context_lower):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# SALARY EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

# Ordered from most specific (salary keyword + range) to least specific (standalone range)
_SALARY_PATTERNS = [
    # "salary range: $100k-150k", "compensation: $100k-150k"
    r"(?i)(?:salary|compensation|base\s+salary|base\s+compensation|pay\s+range|pay\s+band)(?:\s+range)?[:\s]+[\$£€¥]\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?\s*(?:[-–—to]+|&mdash;|&ndash;)\s*[\$£€¥]?\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?",
    # "estimated annual base salary: $93,000 - $135,000"
    r"(?i)(?:estimated\s+)?(?:annual\s+)?(?:base\s+)?salary[:\s]*(?:of\s+)?[\$£€¥]\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?\s*(?:[-–—]|&mdash;|&ndash;)\s*[\$£€¥]?\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?",
    # "$100,000 - $150,000 per year"
    r"[\$£€¥]\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:[-–—]|&mdash;|&ndash;)\s*[\$£€¥]?\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:per|\/)\s*(?:year|annum|annually|yr)",
    # Generic range: "$100k-150k", "$130,900 - $177,100"
    r"[\$£€¥]\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?\s*(?:[-–—]|&mdash;|&ndash;)\s*[\$£€¥]?\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?",
    # "$100k to $150k"
    r"[\$£€¥]\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?\s+to\s+[\$£€¥]?\s*(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:k|K)?",
    # Hourly: "$45 - $65 per hour"
    r"[\$£€¥]\s*(\d{2,3}(?:\.\d{2})?)\s*(?:[-–—]|&mdash;|&ndash;)\s*[\$£€¥]?\s*(\d{2,3}(?:\.\d{2})?)\s*(?:per|\/|\s)\s*(?:hour|hr)",
]


def extract_salary(description: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract salary from a job description.

    Returns:
        (salary_string, matched_context) e.g. ("$130,900-$177,100", "...salary range: $130,900...")
        (None, None) if no salary found.
    """
    if not description:
        return None, None

    # Strip HTML tags and decode entities
    desc_clean = re.sub(r"<[^>]+>", "", description)
    desc_clean = html.unescape(desc_clean)

    for pattern in _SALARY_PATTERNS:
        match = re.search(pattern, desc_clean, re.IGNORECASE)
        if not match:
            continue

        matched_text = match.group(0)

        # Get context around match for false-positive check
        start = max(0, match.start() - 100)
        end = min(len(desc_clean), match.end() + 100)
        context = desc_clean[start:end].strip()

        if _is_false_positive(context):
            continue

        if len(match.groups()) >= 2:
            min_val_str = match.group(1).replace(",", "")
            max_val_str = match.group(2).replace(",", "")
            # Handle European-style numbers like '82.952.900' (periods as thousands separators)
            if min_val_str.count('.') > 1:
                min_val_str = min_val_str.replace('.', '')
            if max_val_str.count('.') > 1:
                max_val_str = max_val_str.replace('.', '')
            try:
                min_val = float(min_val_str)
                max_val = float(max_val_str)
            except ValueError:
                continue

            if "k" in matched_text.lower():
                if min_val < 1000:
                    min_val *= 1000
                if max_val < 1000:
                    max_val *= 1000

            # Filter unrealistic values
            if min_val < 15000 or max_val > 1_500_000:
                continue
            if min_val > max_val:
                continue

            currency = "$" if "$" in matched_text else ("€" if "€" in matched_text else ("£" if "£" in matched_text else "$"))

            # Short context for return
            short_start = max(0, match.start() - 50)
            short_end = min(len(desc_clean), match.end() + 50)
            short_context = desc_clean[short_start:short_end].strip()

            return f"{currency}{int(min_val):,}-{currency}{int(max_val):,}", short_context

    return None, None


def parse_salary_range(salary_str: Optional[str]) -> Tuple[Optional[float], Optional[float], str]:
    """
    Parse a salary string like "$130,900-$177,100" into components.

    Returns:
        (salary_min, salary_max, currency_code)  e.g. (130900.0, 177100.0, "USD")
        (None, None, "USD") if unparseable.
    """
    if not salary_str:
        return None, None, "USD"

    # Detect currency
    if "$" in salary_str:
        currency = "USD"
    elif "€" in salary_str:
        currency = "EUR"
    elif "£" in salary_str:
        currency = "GBP"
    else:
        currency = "USD"

    # Strip currency symbols
    cleaned = re.sub(r"[\$£€¥]", "", salary_str).strip().replace(",", "")

    # Try to parse range
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|K)?\s*[-–—]\s*(\d+(?:\.\d+)?)\s*(?:k|K)?", cleaned)
    if range_match:
        min_val = float(range_match.group(1))
        max_val = float(range_match.group(2))

        if "k" in salary_str.lower():
            if min_val < 1000:
                min_val *= 1000
            if max_val < 1000:
                max_val *= 1000

        return min_val, max_val, currency

    # Try single value
    single_match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if single_match:
        val = float(single_match.group(1))
        if "k" in salary_str.lower() and val < 1000:
            val *= 1000
        return val, val, currency

    return None, None, currency


# ═══════════════════════════════════════════════════════════════════════
# EXPERIENCE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

_EXPERIENCE_PATTERNS = [
    # "3-5 years of experience with X"
    r"(\d+)\s*[-–—to]+\s*(\d+)\+?\s+years?\s+of\s+(?:\w+\s+){0,8}(?:experience|exp)",
    # "5+ years of experience"
    r"(\d+)\+\s+years?\s+(?:of\s+)?(?:\w+\s+){0,8}(?:experience|exp)",
    # "Have/Require 4+ years"
    r"(?:have|possess|require|requires|need|needs)\s+(\d+)\+?\s+years?\s+(?:of\s+)?(?:\w+\s+){0,8}(?:experience|exp)",
    # "at least 3 years"
    r"(?:at\s+least|minimum|min\.?)\s+(\d+)\s+years?\s+(?:of\s+)?(?:\w+\s+){0,8}(?:experience|exp)",
    # "3+ years building/developing..."
    r"(\d+)\+\s+years?\s+(?:building|developing|designing|managing|working|creating|implementing|maintaining|shipping)",
    # "3-5 years" with context verbs
    r"(\d+)\s*[-–—to]+\s*(\d+)\+?\s+years?\s+(?:in|with|working|building|developing|designing|managing|shipping)",
    # "5+ years" with context verbs
    r"(\d+)\+\s+years?\s+(?:in|with|working|building|developing|designing|managing|shipping)",
    # "5 years of experience" (no +)
    r"(\d+)\s+years?\s+(?:of\s+)?(?:\w+\s+){0,5}(?:experience|exp)",
]


def extract_experience(description: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Extract minimum years of experience from a job description.

    Returns:
        (min_years, matched_context) e.g. (3, "...3+ years of experience in...")
        (None, None) if not found.
    """
    if not description:
        return None, None

    desc_clean = re.sub(r"<[^>]+>", "", description)
    desc_clean = html.unescape(desc_clean)

    for pattern in _EXPERIENCE_PATTERNS:
        match = re.search(pattern, desc_clean, re.IGNORECASE)
        if not match:
            continue

        start = max(0, match.start() - 50)
        end = min(len(desc_clean), match.end() + 50)
        context = desc_clean[start:end].strip()

        if len(match.groups()) >= 2 and match.group(2):
            # Range — return minimum
            return int(match.group(1)), context
        elif len(match.groups()) >= 1:
            return int(match.group(1)), context

    return None, None
