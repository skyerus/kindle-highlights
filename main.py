import random
import sys
from pathlib import Path

from db import load
from renderer import render_quote_to_png
from sender import send

QUOTE_PNG = Path(__file__).parent / "quote.png"


def main() -> int:
    quotes = load()
    if not quotes:
        print("DB is empty. Trigger refresh.yml to populate it.", file=sys.stderr)
        return 1

    chosen = random.choice(quotes)
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
