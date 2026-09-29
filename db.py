import copy
import json
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent / "highlights.json"


def load() -> list[dict]:
    if not DB_PATH.exists():
        return []
    return json.loads(DB_PATH.read_text())


def save(quotes: list[dict]) -> None:
    DB_PATH.write_text(json.dumps(quotes, indent=2, ensure_ascii=False) + "\n")


def _normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _key(quote):
    # Include book and author: identical short passages in different books remain distinct.
    return tuple(_normalized(quote.get(k, "")) for k in ("book_title", "author", "highlight"))


def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    """Union without truncating text or dropping legacy entries; preserve legacy metadata."""
    merged = copy.deepcopy(existing)
    by_key = {_key(q): q for q in merged}
    covers = {(_normalized(q.get("book_title", "")), _normalized(q.get("author", ""))): q["cover_url"] for q in merged if q.get("cover_url")}
    for incoming in scraped:
        q = copy.deepcopy(incoming)
        key = _key(q)
        if not q.get("cover_url"):
            q["cover_url"] = covers.get(key[:2], "")
        if key not in by_key:
            merged.append(q)
            by_key[key] = q
        else:
            target = by_key[key]
            if not target.get("cover_url") and q.get("cover_url"):
                target["cover_url"] = q["cover_url"]
    return merged
