"""
Job Embeddings — Local Sentence Transformer Embedding Pipeline.

Uses `all-MiniLM-L6-v2` (22M params, 384 dims) for fast, free local embeddings.
Falls back to OpenAI `text-embedding-3-small` (1536 dims) if API key is set.

Embeddings enable:
  - Semantic job search
  - Resume ↔ job matching (cosine similarity)
  - Semantic deduplication
  - "Similar jobs" recommendations

Usage:
    from scripts.ai.embed_jobs import JobEmbedder
    embedder = JobEmbedder()
    vec = embedder.embed_text("Senior ML Engineer building LLM pipelines")
    # → numpy array of shape (384,)
    
    # Batch embed all un-embedded jobs
    embedder.embed_all_jobs()
"""

import json
import os
import sqlite3
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "jobclaw.db"


# ═══════════════════════════════════════════════════════════════════════
# EMBEDDING BACKENDS
# ═══════════════════════════════════════════════════════════════════════

class LocalEmbedder:
    """Sentence Transformer embedding (free, local, fast)."""

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMS = 384

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.MODEL_NAME)
            except ImportError:
                raise ImportError(
                    "sentence-transformers required. Run: pip install sentence-transformers"
                )

    def embed(self, text: str) -> np.ndarray:
        self._load()
        return self._model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        self._load()
        return self._model.encode(texts, batch_size=batch_size, normalize_embeddings=True)

    @property
    def dims(self):
        return self.DIMS


class OpenAIEmbedder:
    """OpenAI embedding via API (requires OPENAI_API_KEY)."""

    MODEL_NAME = "text-embedding-3-small"
    DIMS = 1536

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

    def embed(self, text: str) -> np.ndarray:
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        resp = client.embeddings.create(input=[text], model=self.MODEL_NAME)
        return np.array(resp.data[0].embedding, dtype=np.float32)

    def embed_batch(self, texts: list[str], batch_size: int = 100) -> np.ndarray:
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            resp = client.embeddings.create(input=chunk, model=self.MODEL_NAME)
            batch_vecs = [np.array(d.embedding, dtype=np.float32) for d in resp.data]
            all_embeddings.extend(batch_vecs)
        return np.array(all_embeddings)

    @property
    def dims(self):
        return self.DIMS


# ═══════════════════════════════════════════════════════════════════════
# JOB EMBEDDER
# ═══════════════════════════════════════════════════════════════════════

class JobEmbedder:
    """
    High-level job embedding pipeline.
    
    Auto-selects backend:
      - OpenAI if OPENAI_API_KEY is set
      - Local sentence-transformers otherwise
    """

    def __init__(self, backend: str = "auto"):
        if backend == "openai" or (backend == "auto" and os.environ.get("OPENAI_API_KEY")):
            self.embedder = OpenAIEmbedder()
            self.backend_name = "openai"
        else:
            self.embedder = LocalEmbedder()
            self.backend_name = "local"

    def _job_to_text(self, job: dict) -> str:
        """Convert a job dict to embeddable text."""
        parts = []
        if job.get("title"):
            parts.append(f"Title: {job['title']}")
        if job.get("company"):
            parts.append(f"Company: {job['company']}")
        if job.get("location"):
            parts.append(f"Location: {job['location']}")
        if job.get("description"):
            # Truncate long descriptions to stay within token limits
            desc = job["description"][:2000]
            parts.append(f"Description: {desc}")
        if job.get("keywords_matched"):
            kws = job["keywords_matched"]
            if isinstance(kws, str):
                try:
                    kws = json.loads(kws)
                except Exception:
                    kws = []
            if kws:
                parts.append(f"Category: {', '.join(kws)}")
        return " | ".join(parts) if parts else ""

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        return self.embedder.embed(text)

    def embed_job(self, job: dict) -> np.ndarray:
        """Embed a single job dict."""
        text = self._job_to_text(job)
        return self.embedder.embed(text) if text else np.zeros(self.embedder.dims)

    def embed_all_jobs(self, limit: int = 10000) -> int:
        """
        Batch-embed all jobs that don't have embeddings yet.
        Stores embeddings as JSON-encoded numpy arrays in the DB.
        
        Returns count of jobs embedded.
        """
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        
        try:
            # Ensure embedding column exists
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN embedding_json TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Get jobs without embeddings
            cursor = conn.execute("""
                SELECT internal_hash, title, company, location, description, keywords_matched
                FROM jobs
                WHERE embedding_json IS NULL AND is_active = 1
                ORDER BY first_seen DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

            if not rows:
                return 0

            # Build texts
            jobs = [dict(r) for r in rows]
            texts = [self._job_to_text(j) for j in jobs]
            hashes = [j["internal_hash"] for j in jobs]

            # Batch embed
            print(f"Embedding {len(texts)} jobs with {self.backend_name}...")
            embeddings = self.embedder.embed_batch(texts)

            # Store in DB
            for i, (hash_val, emb) in enumerate(zip(hashes, embeddings)):
                emb_json = json.dumps(emb.tolist())
                conn.execute(
                    "UPDATE jobs SET embedding_json = ? WHERE internal_hash = ?",
                    (emb_json, hash_val)
                )
                if (i + 1) % 500 == 0:
                    conn.commit()
                    print(f"  Stored {i + 1}/{len(hashes)} embeddings...")

            conn.commit()
            print(f"Done! Embedded {len(hashes)} jobs.")
            return len(hashes)

        finally:
            conn.close()

    def find_similar(self, query_text: str, top_k: int = 10) -> list[dict]:
        """
        Find jobs most similar to a text query using cosine similarity.
        Returns list of {internal_hash, title, company, similarity} dicts.
        """
        query_vec = self.embed_text(query_text)

        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT internal_hash, title, company, location, url, embedding_json
                FROM jobs
                WHERE embedding_json IS NOT NULL AND is_active = 1
                LIMIT 5000
            """)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                try:
                    emb = np.array(json.loads(row["embedding_json"]), dtype=np.float32)
                    sim = float(np.dot(query_vec, emb))  # Already normalized → cosine sim
                    results.append({
                        "internal_hash": row["internal_hash"],
                        "title": row["title"],
                        "company": row["company"],
                        "location": row["location"],
                        "url": row["url"],
                        "similarity": round(sim, 4),
                    })
                except Exception:
                    continue

            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results[:top_k]

        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    embedder = JobEmbedder()
    print(f"Backend: {embedder.backend_name} ({embedder.embedder.dims} dims)")

    count = embedder.embed_all_jobs(limit=500)
    print(f"Embedded {count} jobs")

    # Test similarity search
    if count > 0:
        results = embedder.find_similar("Machine Learning Engineer building NLP systems")
        print("\nTop 5 similar jobs:")
        for r in results[:5]:
            print(f"  {r['similarity']:.3f} | {r['title']} @ {r['company']}")
