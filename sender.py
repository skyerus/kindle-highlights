import os
import requests


def send(highlight: dict) -> None:
    """
    Send a Kindle highlight to a Discord channel via webhook.
    highlight: {highlight, book_title, author}
    """
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

    message = f'"{highlight["highlight"]}"\n— {highlight["book_title"]}, {highlight["author"]}'

    response = requests.post(webhook_url, json={"content": message}, timeout=30)

    if response.ok:
        print("Message sent successfully.")
    else:
        raise RuntimeError(
            f"Failed to send Discord message: {response.status_code} {response.text}"
        )
