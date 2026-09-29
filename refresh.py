import argparse
import json
import sys
from pathlib import Path

from db import load, load_tombstones, merge, save
from scraper import get_highlights


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the shared quote archive from Amazon.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scrape-output", type=Path, help="Save only the incoming Amazon batch, without changing the archive")
    mode.add_argument("--merge-input", type=Path, help="Merge a previously scraped batch into the current archive")
    args = parser.parse_args(argv)

    if args.merge_input:
        scraped = json.loads(args.merge_input.read_text(encoding="utf-8"))
    else:
        print("Scraping highlights from Amazon...")
        scraped = get_highlights()
    if not isinstance(scraped, list) or not scraped:
        print("Scraper returned no highlights. Aborting (DB unchanged).", file=sys.stderr)
        return 1
    if any(not isinstance(q, dict) or not isinstance(q.get("highlight"), str)
           or not q["highlight"].strip() for q in scraped):
        print("Invalid incoming highlight batch. Aborting (DB unchanged).", file=sys.stderr)
        return 1

    if args.scrape_output:
        args.scrape_output.write_text(json.dumps(scraped, ensure_ascii=False), encoding="utf-8")
        print(f"Saved {len(scraped)} incoming highlights for merge.")
        return 0

    existing = load()
    merged = merge(existing, scraped, tombstones=load_tombstones())
    save(merged)
    print(f"DB had {len(existing)} quotes; after merge and deletion filtering: {len(merged)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
