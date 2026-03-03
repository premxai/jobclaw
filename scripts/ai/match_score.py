"""
Resume Match Scorer — Cosine similarity between resume and job embeddings.

Given a resume text/file, embeds it and scores every active job
by cosine similarity. Powers the "🎯 94% match" feature.

Usage:
    from scripts.ai.match_score import ResumeMatcher
    matcher = ResumeMatcher()
    matcher.load_resume("path/to/resume.txt")
    matches = matcher.score_jobs(top_k=20)
    for m in matches:
        print(f"  🎯 {m['score']:.0%} | {m['title']} @ {m['company']}")
"""

import json
import numpy as np
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"


class ResumeMatcher:
    """Score job matches against a user's resume."""

    def __init__(self):
        from scripts.ai.embed_jobs import JobEmbedder
        self.embedder = JobEmbedder()
        self.resume_vector = None
        self.resume_text = ""

    def load_resume(self, path_or_text: str):
        """Load resume from file path or raw text."""
        path = Path(path_or_text)
        if path.exists():
            self.resume_text = path.read_text(encoding="utf-8", errors="replace")
        else:
            self.resume_text = path_or_text

        self.resume_vector = self.embedder.embed_text(self.resume_text)

    def score_jobs(self, top_k: int = 20, min_score: float = 0.3) -> list[dict]:
        """
        Score all embedded jobs against the resume.
        
        Returns list of {internal_hash, title, company, location, url, score, match_tier}.
        score is cosine similarity [0, 1].
        match_tier: "excellent" (>0.7), "good" (>0.5), "fair" (>0.3).
        """
        if self.resume_vector is None:
            raise ValueError("No resume loaded. Call load_resume() first.")

        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT internal_hash, title, company, location, url, 
                       salary_min, salary_max, keywords_matched, embedding_json
                FROM jobs
                WHERE embedding_json IS NOT NULL AND is_active = 1
            """)
            
            results = []
            for row in cursor:
                try:
                    emb = np.array(json.loads(row["embedding_json"]), dtype=np.float32)
                    score = float(np.dot(self.resume_vector, emb))

                    if score < min_score:
                        continue

                    tier = "excellent" if score > 0.7 else "good" if score > 0.5 else "fair"
                    
                    kws = row["keywords_matched"]
                    if isinstance(kws, str):
                        try:
                            kws = json.loads(kws)
                        except Exception:
                            kws = []

                    results.append({
                        "internal_hash": row["internal_hash"],
                        "title": row["title"],
                        "company": row["company"],
                        "location": row["location"],
                        "url": row["url"],
                        "salary_min": row["salary_min"],
                        "salary_max": row["salary_max"],
                        "keywords_matched": kws,
                        "score": round(score, 4),
                        "match_tier": tier,
                    })
                except Exception:
                    continue

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        finally:
            conn.close()

    def format_discord(self, matches: list[dict], max_items: int = 10) -> str:
        """Format top matches for Discord embed."""
        lines = ["## 🎯 Resume Match Results\n"]
        tier_emoji = {"excellent": "🟢", "good": "🟡", "fair": "🟠"}

        for m in matches[:max_items]:
            emoji = tier_emoji.get(m["match_tier"], "⚪")
            salary = ""
            if m.get("salary_min") and m.get("salary_max"):
                salary = f" | 💰 ${m['salary_min']/1000:.0f}k-${m['salary_max']/1000:.0f}k"
            lines.append(
                f"{emoji} **{m['score']:.0%}** — [{m['title']}]({m['url']})\n"
                f"   🏢 {m['company']} | 📍 {m.get('location', 'Unknown')}{salary}"
            )
        
        return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    matcher = ResumeMatcher()
    
    # Use sample resume text for testing
    sample_resume = """
    Senior Machine Learning Engineer with 5+ years of experience.
    Skills: Python, PyTorch, TensorFlow, NLP, LLMs, Computer Vision, Transformers.
    Experience building production ML pipelines, training large language models,
    and deploying inference systems at scale. AWS, Kubernetes, MLflow.
    MS Computer Science, Stanford University.
    """
    
    matcher.load_resume(sample_resume)
    matches = matcher.score_jobs(top_k=10)
    
    if matches:
        print(matcher.format_discord(matches))
    else:
        print("No embedded jobs found. Run embed_jobs.py first.")
