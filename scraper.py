import os
import time
import pyotp
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def get_highlights() -> list[dict]:
    """
    Log in to Amazon and scrape all Kindle highlights from read.amazon.com/notebook.
    Returns a list of dicts: [{highlight, book_title, author}, ...]
    """
    email = os.environ["AMAZON_EMAIL"]
    password = os.environ["AMAZON_PASSWORD"]
    otp_secret = os.environ.get("AMAZON_OTP_SECRET", "")

    highlights = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # Step 1: Sign in
        print("Navigating to Amazon sign-in...")
        page.goto("https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=usflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")

        # Enter email
        page.wait_for_selector("#ap_email", timeout=15000)
        page.fill("#ap_email", email)
        page.click("#continue")

        # Enter password
        page.wait_for_selector("#ap_password", timeout=15000)
        page.fill("#ap_password", password)
        page.click("#signInSubmit")

        # Handle OTP if prompted
        if otp_secret:
            try:
                page.wait_for_selector("#auth-mfa-otpcode", timeout=8000)
                totp_code = pyotp.TOTP(otp_secret).now()
                print(f"Entering OTP code...")
                page.fill("#auth-mfa-otpcode", totp_code)
                # Uncheck "don't require OTP on this browser" to keep things clean
                try:
                    page.uncheck("#auth-mfa-remember-device")
                except Exception:
                    pass
                page.click("#auth-signin-button")
            except PlaywrightTimeoutError:
                # No OTP prompt — either not required or already handled
                print("No OTP prompt detected, continuing...")

        # Step 2: Navigate to Kindle notebook
        print("Navigating to Kindle notebook...")
        page.wait_for_load_state("networkidle", timeout=20000)
        page.goto("https://read.amazon.com/notebook")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Wait for book list sidebar
        try:
            page.wait_for_selector("#kp-notebook-library", timeout=30000)
        except PlaywrightTimeoutError:
            print("Could not load notebook library. Checking page state...")
            print(f"Current URL: {page.url}")
            browser.close()
            return []

        # Collect all book elements
        book_elements = page.query_selector_all("#kp-notebook-library .kp-notebook-library-each-book")
        print(f"Found {len(book_elements)} books.")

        for i in range(len(book_elements)):
            # Re-query to avoid stale element refs after each click
            books = page.query_selector_all("#kp-notebook-library .kp-notebook-library-each-book")
            if i >= len(books):
                break

            book = books[i]

            # Extract title and author before clicking
            try:
                title_el = book.query_selector("h2.kp-notebook-searchable")
                author_el = book.query_selector("p.kp-notebook-searchable")
                book_title = title_el.inner_text().strip() if title_el else "Unknown Title"
                author = author_el.inner_text().strip() if author_el else "Unknown Author"
            except Exception:
                book_title = "Unknown Title"
                author = "Unknown Author"

            print(f"Scraping: {book_title}")
            book.click()

            # Wait for highlights to load
            try:
                page.wait_for_selector("#kp-notebook-annotations", timeout=15000)
                # Small wait to ensure all highlights render
                time.sleep(1)
            except PlaywrightTimeoutError:
                print(f"  No highlights panel for: {book_title}")
                continue

            # Scrape highlight text
            highlight_els = page.query_selector_all("#kp-notebook-annotations .kp-notebook-highlight")
            for el in highlight_els:
                try:
                    text = el.inner_text().strip()
                    if text:
                        highlights.append({
                            "highlight": text,
                            "book_title": book_title,
                            "author": author,
                        })
                except Exception:
                    continue

            print(f"  Found {len(highlight_els)} highlights.")

        browser.close()

    print(f"Total highlights scraped: {len(highlights)}")
    return highlights
