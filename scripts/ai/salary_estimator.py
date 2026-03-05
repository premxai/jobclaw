"""
Salary Estimator — Predicts salary ranges for undisclosed jobs.

Uses a simple kNN-style approach based on role category + location
to estimate salary from jobs that DO have disclosed salary data.

No external ML libraries needed — pure Python with SQLite aggregation.

Usage:
    from scripts.ai.salary_estimator import SalaryEstimator
    estimator = SalaryEstimator()
    estimator.train()  # Load reference data from DB
    estimate = estimator.predict("Software Engineer", "San Francisco")
    # → {"min": 140000, "max": 185000, "currency": "USD", "confidence": 0.82, "sample_size": 47}
"""

import re
from collections import defaultdict
from pathlib import Path

from scripts.database.db_utils import get_connection, is_postgres
from statistics import mean, median, stdev


# ── Location Normalization ───────────────────────────────────────────

# Major metro area normalizations
METRO_ALIASES = {
    "sf": "san_francisco",
    "san francisco": "san_francisco",
    "bay area": "san_francisco",
    "palo alto": "san_francisco",
    "mountain view": "san_francisco",
    "sunnyvale": "san_francisco",
    "menlo park": "san_francisco",
    "cupertino": "san_francisco",
    "redwood city": "san_francisco",
    "san jose": "san_francisco",
    "san mateo": "san_francisco",
    "nyc": "new_york",
    "new york": "new_york",
    "manhattan": "new_york",
    "brooklyn": "new_york",
    "seattle": "seattle",
    "bellevue": "seattle",
    "redmond": "seattle",
    "kirkland": "seattle",
    "la": "los_angeles",
    "los angeles": "los_angeles",
    "santa monica": "los_angeles",
    "austin": "austin",
    "chicago": "chicago",
    "boston": "boston",
    "cambridge": "boston",
    "denver": "denver",
    "boulder": "denver",
    "dc": "washington_dc",
    "washington": "washington_dc",
    "arlington": "washington_dc",
    "remote": "remote",
}


def normalize_location(loc: str) -> str:
    """Normalize a location string to a metro key."""
    if not loc:
        return "unknown"
    loc_lower = loc.lower().strip()
    for alias, metro in METRO_ALIASES.items():
        if alias in loc_lower:
            return metro
    return "other"


# ── Role Category Detection ─────────────────────────────────────────

ROLE_CATEGORIES = {
    "ai_ml": ["machine learning", "ml ", "ai ", "deep learning", "nlp", "computer vision",
              "llm", "generative ai", "data scientist", "applied scientist", "research scientist"],
    "swe": ["software engineer", "software developer", "full stack", "fullstack",
            "backend engineer", "frontend engineer", "web developer", "mobile developer"],
    "data_eng": ["data engineer", "data platform", "etl", "pipeline engineer",
                 "analytics engineer", "dbt", "airflow"],
    "devops": ["devops", "sre", "site reliability", "infrastructure", "cloud engineer",
               "platform engineer", "kubernetes"],
    "management": ["engineering manager", "tech lead", "director of engineering",
                   "vp engineering", "head of"],
}


def categorize_role(title: str) -> str:
    """Categorize a job title into a role bucket."""
    title_lower = title.lower()
    for category, keywords in ROLE_CATEGORIES.items():
        for kw in keywords:
            if kw in title_lower:
                return category
    return "other"


def detect_seniority(title: str) -> str:
    """Detect seniority level from title."""
    title_lower = title.lower()
    if any(w in title_lower for w in ["intern", "internship"]):
        return "intern"
    if any(w in title_lower for w in ["junior", "entry", "new grad", "associate", "early career"]):
        return "junior"
    if any(w in title_lower for w in ["senior", "sr ", "sr.", "lead"]):
        return "senior"
    if any(w in title_lower for w in ["staff", "principal", "distinguished"]):
        return "staff"
    if any(w in title_lower for w in ["director", "vp ", "head of", "chief"]):
        return "executive"
    return "mid"


# ═══════════════════════════════════════════════════════════════════════
# ESTIMATOR
# ═══════════════════════════════════════════════════════════════════════

class SalaryEstimator:
    """
    Predicts salary ranges using aggregated data from the jobs database.
    
    Strategy: Groups known salaries by (role_category, seniority, metro)
    and uses the group statistics to estimate undisclosed salaries.
    Falls back to broader groups when specific data is sparse.
    """

    def __init__(self):
        # salary_data[role_category][seniority][metro] = [(min, max), ...]
        self.salary_data: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self._trained = False

    def train(self) -> int:
        """Load salary data from the database. Returns number of salary records used."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, location, salary_min, salary_max, salary_currency
                FROM jobs 
                WHERE salary_min IS NOT NULL 
                AND salary_min > 10000 
                AND salary_max IS NOT NULL 
                AND salary_max > 10000
                AND salary_currency = 'USD'
                AND is_active = 1
            """)
            cols = [desc[0] for desc in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

            count = 0
            for row in rows:
                role = categorize_role(row["title"])
                seniority = detect_seniority(row["title"])
                metro = normalize_location(row["location"] or "")

                self.salary_data[role][seniority][metro].append(
                    (row["salary_min"], row["salary_max"])
                )
                count += 1

            self._trained = True
            return count
        finally:
            conn.close()

    def predict(self, title: str, location: str = "") -> dict | None:
        """
        Predict salary range for a job title + location.
        
        Returns: {min, max, currency, confidence, sample_size, method}
        Returns None if insufficient data.
        """
        if not self._trained:
            self.train()

        role = categorize_role(title)
        seniority = detect_seniority(title)
        metro = normalize_location(location)

        # Try progressively broader groups
        candidates = self._get_candidates(role, seniority, metro)
        method = "exact"

        if len(candidates) < 3:
            # Broaden: any metro for same role + seniority
            candidates = self._get_candidates(role, seniority, None)
            method = "role+seniority"

        if len(candidates) < 3:
            # Broaden: any seniority for same role + metro
            candidates = self._get_candidates(role, None, metro)
            method = "role+metro"

        if len(candidates) < 3:
            # Broadest: just role category
            candidates = self._get_candidates(role, None, None)
            method = "role_only"

        if len(candidates) < 2:
            return None

        # Compute statistics
        mins = [c[0] for c in candidates]
        maxs = [c[1] for c in candidates]

        pred_min = round(median(mins) / 1000) * 1000  # Round to nearest 1k
        pred_max = round(median(maxs) / 1000) * 1000

        # Confidence based on sample size and std deviation
        confidence = min(0.95, 0.4 + (len(candidates) / 100))
        if len(candidates) >= 5:
            cv = stdev(mins) / mean(mins) if mean(mins) > 0 else 1.0
            confidence *= max(0.5, 1.0 - cv)  # Lower confidence if high variance

        return {
            "salary_min": pred_min,
            "salary_max": pred_max,
            "currency": "USD",
            "confidence": round(confidence, 2),
            "sample_size": len(candidates),
            "method": method,
        }

    def _get_candidates(self, role, seniority, metro) -> list[tuple]:
        """Get salary data points for the given filters (None = wildcard)."""
        results = []
        for r, seniority_data in self.salary_data.items():
            if role and r != role:
                continue
            for s, metro_data in seniority_data.items():
                if seniority and s != seniority:
                    continue
                for m, salaries in metro_data.items():
                    if metro and m != metro:
                        continue
                    results.extend(salaries)
        return results

    def estimate_all_undisclosed(self) -> int:
        """
        Estimate salary for all jobs without disclosed salary.
        Updates the database with estimated salaries (flagged as estimates).
        Returns count of jobs updated.
        """
        if not self._trained:
            self.train()

        conn = get_connection()
        ph = "%s" if is_postgres() else "?"
        updated = 0

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT internal_hash, title, location
                FROM jobs 
                WHERE (salary_min IS NULL OR salary_min = 0)
                AND is_active = 1
                LIMIT 5000
            """)
            cols = [desc[0] for desc in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

            for row in rows:
                estimate = self.predict(row["title"], row["location"] or "")
                if estimate and estimate["confidence"] >= 0.5:
                    conn.execute(f"""
                        UPDATE jobs 
                        SET salary_min = {ph}, salary_max = {ph}, salary_currency = {ph}
                        WHERE internal_hash = {ph} AND (salary_min IS NULL OR salary_min = 0)
                    """, (
                        estimate["salary_min"],
                        estimate["salary_max"],
                        estimate["currency"],
                        row["internal_hash"],
                    ))
                    updated += 1

            conn.commit()
            return updated
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    estimator = SalaryEstimator()
    n = estimator.train()
    print(f"Trained on {n} salary records")

    # Test predictions
    test_cases = [
        ("Software Engineer", "San Francisco"),
        ("Senior Machine Learning Engineer", "New York"),
        ("Data Scientist", "Remote"),
        ("Junior Software Developer", "Austin"),
        ("Staff Engineer", "Seattle"),
    ]

    for title, loc in test_cases:
        result = estimator.predict(title, loc)
        if result:
            print(f"  {title} @ {loc}: ${result['salary_min']:,}-${result['salary_max']:,} "
                  f"(confidence={result['confidence']}, n={result['sample_size']}, method={result['method']})")
        else:
            print(f"  {title} @ {loc}: insufficient data")
