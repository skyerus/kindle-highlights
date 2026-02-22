import random
import sys

from scraper import get_highlights
from sender import send


def main():
    print("Fetching Kindle highlights...")
    highlights = get_highlights()

    if not highlights:
        print("Error: No highlights found. Exiting.", file=sys.stderr)
        sys.exit(1)

    chosen = random.choice(highlights)
    print(f"Selected highlight from '{chosen['book_title']}': {chosen['highlight'][:80]}...")

    print("Sending WhatsApp message...")
    send(chosen)
    print("Done.")


if __name__ == "__main__":
    main()
