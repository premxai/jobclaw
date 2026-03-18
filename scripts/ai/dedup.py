"""
Semantic Deduplication — Detect cross-platform duplicate job listings.

Uses MinHash + LSH (datasketch library) on job descriptions to find
near-duplicate postings across different ATS platforms. For example,
the same role posted on Greenhouse AND LinkedIn.

When datasketch is not installed, falls back to a simpler
token-set Jaccard similarity approach.

Usage:
    from scripts.ai.dedup import JobDeduplicator
    dedup = JobDeduplicator()
    clusters = dedup.find_duplicates()
    dedup.merge_duplicates(clusters)
"""

import re
from collections import defaultdict
from pathlib import Path

from scripts.database.db_utils import get_connection, is_postgres


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercase words."""
    if not text:
        return set()
    text = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = set(text.split())
    # Remove very common words that don't help distinguish jobs
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "this",
        "that",
        "these",
        "those",
        "we",
        "you",
        "your",
        "our",
        "their",
        "its",
        "as",
        "if",
        "not",
        "no",
        "all",
        "any",
        "each",
        "every",
        "such",
        "what",
        "which",
        "who",
        "whom",
        "more",
        "most",
        "other",
        "some",
        "about",
        "into",
        "through",
        "also",
    }
    return tokens - stopwords


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


class JobDeduplicator:
    """
    Find and merge duplicate job listings across platforms.

    Strategy:
    1. Group by normalized title to narrow candidates
    2. Within each title group, compute similarity on descriptions
    3. Jobs with Jaccard > threshold are considered duplicates
    4. Merge: keep the most complete listing, mark others as inactive
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self._use_minhash = False

        try:
            from datasketch import MinHash, MinHashLSH  # noqa: F401

            self._use_minhash = True
        except ImportError:
            pass

    def _normalize_title(self, title: str) -> str:
        """Normalize title for grouping (remove seniority, company specifics)."""
        t = title.lower().strip()
        # Remove common prefixes
        for prefix in [
            "senior ",
            "sr ",
            "sr. ",
            "junior ",
            "jr ",
            "jr. ",
            "lead ",
            "principal ",
            "staff ",
            "associate ",
        ]:
            t = t.replace(prefix, "")
        # Remove parenthetical qualifiers
        t = re.sub(r"\(.*?\)", "", t).strip()
        # Remove location suffixes
        t = re.sub(r"\s*-\s*(remote|hybrid|onsite|us|usa).*$", "", t, flags=re.IGNORECASE)
        return t

    def find_duplicates(self, limit: int = 5000) -> list[list[dict]]:
        """
        Find clusters of duplicate job listings.

        Returns list of clusters, where each cluster is a list of
        {internal_hash, title, company, source_ats, description_len} dicts.
        """
        conn = get_connection()
        ph = "%s" if is_postgres() else "?"

        try:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT internal_hash, title, company, source_ats,
                       description, location, salary_min
                FROM jobs
                WHERE is_active = 1
                ORDER BY first_seen DESC
                LIMIT {ph}
            """,
                (limit,),
            )
            cols = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()
            rows = [dict(zip(cols, r)) for r in raw_rows]

            # Group by normalized title
            title_groups = defaultdict(list)
            for row in rows:
                norm = self._normalize_title(row["title"])
                title_groups[norm].append(row)

            clusters = []

            for _norm_title, group in title_groups.items():
                if len(group) < 2:
                    continue

                # Within group, find pairs with high similarity
                if self._use_minhash and len(group) > 10:
                    group_clusters = self._minhash_cluster(group)
                else:
                    group_clusters = self._jaccard_cluster(group)

                clusters.extend(group_clusters)

            return clusters

        finally:
            conn.close()

    def _jaccard_cluster(self, group: list[dict]) -> list[list[dict]]:
        """Cluster by pairwise Jaccard similarity (for small groups)."""
        n = len(group)
        tokenized = [_tokenize(g.get("description", "")) for g in group]

        # Union-Find for clustering
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            pa, pb = find(a), find(b)
            if pa != pb:
                parent[pa] = pb

        for i in range(n):
            for j in range(i + 1, n):
                if group[i]["source_ats"] == group[j]["source_ats"]:
                    continue  # Same platform → skip (already deduped by hash)
                sim = jaccard_similarity(tokenized[i], tokenized[j])
                if sim >= self.threshold:
                    union(i, j)

        # Collect clusters
        cluster_map = defaultdict(list)
        for i in range(n):
            root = find(i)
            cluster_map[root].append(
                {
                    "internal_hash": group[i]["internal_hash"],
                    "title": group[i]["title"],
                    "company": group[i]["company"],
                    "source_ats": group[i]["source_ats"],
                    "description_len": len(group[i].get("description", "") or ""),
                    "has_salary": bool(group[i].get("salary_min")),
                }
            )

        return [c for c in cluster_map.values() if len(c) > 1]

    def _minhash_cluster(self, group: list[dict]) -> list[list[dict]]:
        """Cluster using MinHash LSH (for larger groups)."""
        from datasketch import MinHash, MinHashLSH

        lsh = MinHashLSH(threshold=self.threshold, num_perm=128)
        minhashes = {}

        for i, g in enumerate(group):
            tokens = _tokenize(g.get("description", ""))
            mh = MinHash(num_perm=128)
            for token in tokens:
                mh.update(token.encode("utf-8"))
            key = f"{i}_{g['internal_hash'][:20]}"
            try:
                lsh.insert(key, mh)
                minhashes[key] = (i, mh)
            except ValueError:
                continue  # Duplicate key

        # Query each item for its neighbors
        parent = list(range(len(group)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            pa, pb = find(a), find(b)
            if pa != pb:
                parent[pa] = pb

        for key, (idx, mh) in minhashes.items():
            neighbors = lsh.query(mh)
            for neighbor_key in neighbors:
                if neighbor_key == key:
                    continue
                neighbor_idx = minhashes[neighbor_key][0]
                if group[idx]["source_ats"] != group[neighbor_idx]["source_ats"]:
                    union(idx, neighbor_idx)

        cluster_map = defaultdict(list)
        for i in range(len(group)):
            root = find(i)
            cluster_map[root].append(
                {
                    "internal_hash": group[i]["internal_hash"],
                    "title": group[i]["title"],
                    "company": group[i]["company"],
                    "source_ats": group[i]["source_ats"],
                    "description_len": len(group[i].get("description", "") or ""),
                    "has_salary": bool(group[i].get("salary_min")),
                }
            )

        return [c for c in cluster_map.values() if len(c) > 1]

    def merge_duplicates(self, clusters: list[list[dict]]) -> int:
        """
        Merge duplicate clusters — keep the most complete listing,
        mark others as inactive.

        "Most complete" = longest description + has salary.
        Returns count of jobs marked as duplicates.
        """
        conn = get_connection()
        ph = "%s" if is_postgres() else "?"
        merged = 0

        try:
            for cluster in clusters:
                # Sort by completeness: salary > description length
                cluster.sort(key=lambda x: (x["has_salary"], x["description_len"]), reverse=True)

                # Keep the best, deactivate the rest
                cluster[0]
                duplicates = cluster[1:]

                for dup in duplicates:
                    conn.execute(
                        f"UPDATE jobs SET is_active = 0, status = 'archived' WHERE internal_hash = {ph}",
                        (dup["internal_hash"],),
                    )
                    merged += 1

            conn.commit()
            return merged

        finally:
            conn.close()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    dedup = JobDeduplicator(threshold=0.6)
    clusters = dedup.find_duplicates()

    print(f"Found {len(clusters)} duplicate clusters:")
    for i, cluster in enumerate(clusters[:10]):
        print(f"\n  Cluster {i + 1} ({len(cluster)} listings):")
        for item in cluster:
            print(
                f"    [{item['source_ats']}] {item['title']} @ {item['company']} "
                f"(desc={item['description_len']} chars, salary={'yes' if item['has_salary'] else 'no'})"
            )
