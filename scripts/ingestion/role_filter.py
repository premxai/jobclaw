"""
Role Keyword Filter — Complete Taxonomy (142+ titles).

Filters job listings to AI/ML, Data Science, Data Engineering,
Data Analysis, Software Engineering, New Grad, and Emerging roles.
Case-insensitive, flexible matching with pre-compiled regex.
"""

import re

# ═══════════════════════════════════════════════════════════════════════
# TARGET ROLE KEYWORDS — organized by category
# ═══════════════════════════════════════════════════════════════════════

ROLE_KEYWORDS: list[tuple[str, str]] = [
    # ── AI/ML Core ────────────────────────────────────────────────────
    ("machine learning engineer", "AI/ML"),
    ("ml engineer", "AI/ML"),
    ("ai engineer", "AI/ML"),
    ("generative ai engineer", "AI/ML"),
    ("applied machine learning engineer", "AI/ML"),
    ("machine learning scientist", "AI/ML"),
    ("ml scientist", "AI/ML"),
    ("research scientist", "AI/ML"),
    ("ai research assistant", "AI/ML"),
    ("llm engineer", "AI/ML"),
    ("nlp engineer", "AI/ML"),
    ("computer vision engineer", "AI/ML"),
    ("deep learning engineer", "AI/ML"),
    ("deep learning", "AI/ML"),
    ("ml compiler engineer", "AI/ML"),
    ("mlops engineer", "AI/ML"),
    ("ml ops", "AI/ML"),
    ("ai/ml platform engineer", "AI/ML"),
    ("applied scientist", "AI/ML"),
    ("ai scientist", "AI/ML"),
    ("machine learning", "AI/ML"),

    # ── AI/ML Specialized ─────────────────────────────────────────────
    ("prompt engineer", "AI/ML"),
    ("rag engineer", "AI/ML"),
    ("ai architect", "AI/ML"),
    ("ml systems engineer", "AI/ML"),
    ("ai research engineer", "AI/ML"),
    ("foundation model engineer", "AI/ML"),
    ("ai perception engineer", "AI/ML"),
    ("robotics ml engineer", "AI/ML"),
    ("robotics engineer", "AI/ML"),
    ("llmops engineer", "AI/ML"),
    ("vector database engineer", "AI/ML"),
    ("embeddings engineer", "AI/ML"),
    ("ai ethics researcher", "AI/ML"),
    ("ai automation engineer", "AI/ML"),

    # ── Data Science Core ─────────────────────────────────────────────
    ("data scientist", "Data Science"),
    ("associate data scientist", "Data Science"),
    ("junior data scientist", "Data Science"),
    ("quantitative data scientist", "Data Science"),
    ("research data scientist", "Data Science"),
    ("applied data scientist", "Data Science"),
    ("data science analyst", "Data Science"),

    # ── Data Science Specialized ──────────────────────────────────────
    ("business intelligence data scientist", "Data Science"),
    ("optimization data scientist", "Data Science"),
    ("clinical data scientist", "Data Science"),
    ("geospatial data scientist", "Data Science"),
    ("decision scientist", "Data Science"),
    ("analytics scientist", "Data Science"),
    ("predictive modeler", "Data Science"),
    ("statistical analyst", "Data Science"),

    # ── Data Engineering Core ─────────────────────────────────────────
    ("data engineer", "Data Engineering"),
    ("junior data engineer", "Data Engineering"),
    ("associate data engineer", "Data Engineering"),
    ("big data engineer", "Data Engineering"),
    ("cloud data engineer", "Data Engineering"),
    ("data platform engineer", "Data Engineering"),
    ("analytics engineer", "Data Engineering"),

    # ── Data Engineering Specialized ──────────────────────────────────
    ("etl developer", "Data Engineering"),
    ("data pipeline engineer", "Data Engineering"),
    ("data warehouse engineer", "Data Engineering"),
    ("database engineer", "Data Engineering"),
    ("data infrastructure engineer", "Data Engineering"),
    ("big data developer", "Data Engineering"),
    ("bi developer", "Data Engineering"),
    ("data integration engineer", "Data Engineering"),
    ("hadoop developer", "Data Engineering"),
    ("search engineer", "Data Engineering"),
    ("solutions architect", "Data Engineering"),
    ("data architect", "Data Engineering"),
    ("database developer", "Data Engineering"),
    ("azure data engineer", "Data Engineering"),
    ("aws data engineer", "Data Engineering"),
    ("gcp data engineer", "Data Engineering"),

    # ── Data Analyst Core ─────────────────────────────────────────────
    ("data analyst", "Data Analyst"),
    ("junior data analyst", "Data Analyst"),
    ("associate data analyst", "Data Analyst"),
    ("entry level data analyst", "Data Analyst"),
    ("business data analyst", "Data Analyst"),
    ("operations data analyst", "Data Analyst"),
    ("marketing data analyst", "Data Analyst"),

    # ── Data Analyst Specialized ──────────────────────────────────────
    ("business intelligence analyst", "Data Analyst"),
    ("analytics analyst", "Data Analyst"),
    ("reporting analyst", "Data Analyst"),
    ("data quality analyst", "Data Analyst"),
    ("product data analyst", "Data Analyst"),
    ("financial data analyst", "Data Analyst"),
    ("fraud data analyst", "Data Analyst"),
    ("clinical data analyst", "Data Analyst"),
    ("gis analyst", "Data Analyst"),
    ("people analytics analyst", "Data Analyst"),
    ("sales analytics analyst", "Data Analyst"),
    ("customer analytics analyst", "Data Analyst"),
    ("quantitative analyst", "Data Analyst"),
    ("data visualization analyst", "Data Analyst"),
    ("business analyst", "Data Analyst"),

    # ── SWE Core ──────────────────────────────────────────────────────
    ("software engineer", "SWE"),
    ("software developer", "SWE"),
    ("junior software engineer", "SWE"),
    ("associate software engineer", "SWE"),
    ("entry level software engineer", "SWE"),
    ("new grad software engineer", "SWE"),
    ("graduate software engineer", "SWE"),

    # ── SWE Frontend/Backend/Full-Stack ───────────────────────────────
    ("frontend engineer", "SWE"),
    ("backend engineer", "SWE"),
    ("full stack engineer", "SWE"),
    ("fullstack engineer", "SWE"),
    ("full stack developer", "SWE"),
    ("web developer", "SWE"),
    ("mobile engineer", "SWE"),
    ("ios engineer", "SWE"),
    ("android engineer", "SWE"),

    # ── SWE Specialized ───────────────────────────────────────────────
    ("cloud engineer", "SWE"),
    ("devops engineer", "SWE"),
    ("site reliability engineer", "SWE"),
    ("sre", "SWE"),
    ("platform engineer", "SWE"),
    ("infrastructure engineer", "SWE"),
    ("systems engineer", "SWE"),
    ("network engineer", "SWE"),
    ("automation engineer", "SWE"),
    ("solutions engineer", "SWE"),
    ("application engineer", "SWE"),
    ("embedded software engineer", "SWE"),
    ("database administrator", "SWE"),
    ("qa engineer", "SWE"),
    ("quality assurance analyst", "SWE"),
    ("test engineer", "SWE"),
    ("sdet", "SWE"),
    ("security engineer", "SWE"),
    ("cybersecurity analyst", "SWE"),

    # ── New Grad / Early Career ───────────────────────────────────────
    ("new college grad", "New Grad"),
    ("rotational program", "New Grad"),
    ("technology development program", "New Grad"),
    ("engineering development program", "New Grad"),
    ("leadership development program", "New Grad"),
    ("new grad 2026", "New Grad"),
    ("new grad 2025", "New Grad"),
    ("university graduate", "New Grad"),
    ("recent graduate program", "New Grad"),
    ("associate data professional", "New Grad"),
    ("technology analyst", "New Grad"),
    ("engineering analyst", "New Grad"),

    # ── Product & Research ────────────────────────────────────────────
    ("associate product manager", "Product"),
    ("technical product manager", "Product"),
    ("research associate", "Research"),
    ("research engineer", "Research"),
    ("computational biologist", "Research"),
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


# Quick stat
TOTAL_KEYWORDS = len(ROLE_KEYWORDS)
CATEGORIES = sorted(set(cat for _, cat in ROLE_KEYWORDS))
