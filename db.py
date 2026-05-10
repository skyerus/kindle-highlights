import hashlib
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "highlights.json"


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load() -> list[dict]:
    if not DB_PATH.exists():
        return []
    return json.loads(DB_PATH.read_text())


def save(quotes: list[dict]) -> None:
    DB_PATH.write_text(json.dumps(quotes, indent=2, ensure_ascii=False) + "\n")


def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    """Union-merge: keep all existing quotes, append scraped ones not already present (dedup by SHA1 of highlight text). Backfills cover_url onto pre-existing entries that lack it."""
    by_hash = {_hash(q["highlight"]): q for q in existing}
    merged = list(existing)
    for q in scraped:
        h = _hash(q["highlight"])
        if h not in by_hash:
            merged.append(q)
            by_hash[h] = q
        elif not by_hash[h].get("cover_url") and q.get("cover_url"):
            by_hash[h]["cover_url"] = q["cover_url"]
    return merged
