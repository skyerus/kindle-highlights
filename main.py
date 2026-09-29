import argparse
import random
import sys
from pathlib import Path

from db import load, load_tombstones, merge, quote_key

QUOTE_PNG = Path(__file__).parent / "quote.png"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quote-key-output", type=Path)
    mode.add_argument("--check-quote-key", type=Path)
    args = parser.parse_args(argv)
    tombstones = load_tombstones()
    if args.check_quote_key:
        key = args.check_quote_key.read_text().strip()
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid selected quote key")
        return 3 if key in tombstones else 0

    from renderer import render_quote_to_png
    from sender import send

    quotes = merge(load(), [], tombstones=tombstones)
    if not quotes:
        print("DB is empty. Trigger refresh.yml to populate it.", file=sys.stderr)
        return 1

    chosen = random.choice(quotes)
    if args.quote_key_output:
        args.quote_key_output.write_text(quote_key(chosen) + "\n")
    print(f"Selected from '{chosen['book_title']}': {chosen['highlight'][:80]}...")

    print(f"Rendering PNG to {QUOTE_PNG}")
    render_quote_to_png(chosen, QUOTE_PNG)

    print("Sending Discord message...")
    try:
        send(chosen)
    except Exception as e:
        # PNG is already on disk; the workflow's commit step will still publish it for the Kindle.
        print(f"Discord send failed: {e}", file=sys.stderr)
        return 0

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
