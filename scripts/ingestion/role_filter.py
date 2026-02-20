"""
Role Keyword Filter.

Filters job listings to only AI/ML, Software Engineering, and Data Science roles.
Case-insensitive, flexible matching.
"""

import re

# ═══════════════════════════════════════════════════════════════════════
# TARGET ROLE KEYWORDS
# ═══════════════════════════════════════════════════════════════════════

# Each tuple: (keyword, category)
ROLE_KEYWORDS: list[tuple[str, str]] = [
    # Core AI/ML
    ("machine learning engineer", "AI/ML"),
    ("ml engineer", "AI/ML"),
    ("artificial intelligence engineer", "AI/ML"),
    ("ai engineer", "AI/ML"),
    ("research engineer", "AI/ML"),
    ("applied scientist", "AI/ML"),
    ("ai scientist", "AI/ML"),
    ("machine learning scientist", "AI/ML"),
    ("ml scientist", "AI/ML"),
    ("deep learning", "AI/ML"),
    ("nlp engineer", "AI/ML"),
    ("computer vision engineer", "AI/ML"),
    ("robotics engineer", "AI/ML"),
    ("ml ops", "AI/ML"),
    ("mlops", "AI/ML"),
    ("machine learning", "AI/ML"),

    # Software Engineering
    ("software engineer", "SWE"),
    ("software developer", "SWE"),
    ("backend engineer", "SWE"),
    ("systems engineer", "SWE"),
    ("platform engineer", "SWE"),
    ("full stack engineer", "SWE"),
    ("fullstack engineer", "SWE"),
    ("frontend engineer", "SWE"),
    ("infrastructure engineer", "SWE"),
    ("site reliability engineer", "SWE"),
    ("sre", "SWE"),
    ("devops engineer", "SWE"),

    # Data
    ("data scientist", "Data"),
    ("data engineer", "Data"),
    ("applied data scientist", "Data"),
    ("ai data engineer", "Data"),
    ("analytics engineer", "Data"),
    ("data analyst", "Data"),
    ("business intelligence", "Data"),
]

# Pre-compile patterns for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(re.escape(kw), re.IGNORECASE), cat)
    for kw, cat in ROLE_KEYWORDS
]


def matches_target_role(title: str) -> list[str]:
    """Check if a job title matches any target role keywords.

    Args:
        title: Job title to check.

    Returns:
        List of matched keyword categories (e.g., ["AI/ML", "SWE"]).
        Empty list if no match.
    """
    if not title:
        return []
    matched_categories = set()
    for pattern, category in _COMPILED_PATTERNS:
        if pattern.search(title):
            matched_categories.add(category)
    return list(matched_categories)


def is_target_role(title: str) -> bool:
    """Quick check: does this title match any target role?"""
    return bool(matches_target_role(title))
