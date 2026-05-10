import sys

from db import load, merge, save
from scraper import get_highlights


def main() -> int:
    print("Scraping highlights from Amazon...")
    scraped = get_highlights()
    if not scraped:
        print("Scraper returned no highlights. Aborting (DB unchanged).", file=sys.stderr)
        return 1

    existing = load()
    merged = merge(existing, scraped)
    added = len(merged) - len(existing)

    save(merged)
    print(f"DB had {len(existing)} quotes, added {added}, total {len(merged)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
