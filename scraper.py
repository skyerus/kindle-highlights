import os
import time


# Amazon uses both the original sign-in form and a newer claim/email form.
EMAIL_SELECTOR = ', '.join((
    '#ap_email:visible', '#ap_email_login:visible',
    'input[name="email"]:visible', 'input[autocomplete="username"]:visible',
))


def enter_email(page, email: str) -> None:
    field = page.locator(EMAIL_SELECTOR).first
    field.wait_for(state="visible", timeout=15000)
    field.fill(email)
    page.get_by_role("button", name="Continue", exact=True).click()


def get_highlights() -> list[dict]:
    """
    Log in to Amazon and scrape all Kindle highlights from read.amazon.com/notebook.
    Returns a list of dicts: [{highlight, book_title, author}, ...]
    """
    import pyotp
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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

        # Step 1: Navigate to notebook — it will redirect to the correct amazon.com sign-in
        # with return_to=read.amazon.com/notebook already set
        print("Navigating to Kindle notebook (will redirect to sign-in)...")
        page.goto("https://read.amazon.com/notebook")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        print("Arrived at Amazon sign-in.")

        # Amazon sometimes shows a bot-check interstitial ("Continue shopping") — click through it
        try:
            page.get_by_text("Continue shopping", exact=True).first.click(timeout=5000)
            print("Bot check detected, clicking through...")
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            print("Continued past the interstitial.")
        except Exception:
            pass  # No interstitial, proceed normally

        # Enter email
        try:
            enter_email(page, email)
        except PlaywrightTimeoutError:
            print("Amazon sign-in email form did not appear; inspect the debug screenshot.")
            page.screenshot(path="debug_signin.png")
            browser.close()
            raise

        # Enter password
        page.wait_for_selector("#ap_password", timeout=15000)
        page.fill("#ap_password", password)
        page.click("#signInSubmit")

        # Handle OTP if prompted
        if otp_secret:
            try:
                page.wait_for_selector("#auth-mfa-otpcode", timeout=8000)
                totp_code = pyotp.TOTP(otp_secret).now()
                print("Entering OTP code...")
                page.fill("#auth-mfa-otpcode", totp_code)
                try:
                    page.uncheck("#auth-mfa-remember-device")
                except Exception:
                    pass
                page.click("#auth-signin-button")
            except PlaywrightTimeoutError:
                print("No OTP prompt detected, continuing...")

        # Step 2: Should now land on the notebook — wait for the book list sidebar
        print("Waiting for Kindle notebook to load...")
        try:
            page.wait_for_selector("#kp-notebook-library", timeout=30000)
        except PlaywrightTimeoutError:
            print("Notebook did not load; authentication may require attention. Inspect the debug screenshot.")
            page.screenshot(path="debug_notebook.png")
            browser.close()
            return []

        print("Notebook loaded.")

        # Collect all book elements
        book_elements = page.query_selector_all("#kp-notebook-library .kp-notebook-library-each-book")
        print(f"Found {len(book_elements)} books.")

        for i in range(len(book_elements)):
            # Re-query to avoid stale element refs after each click
            books = page.query_selector_all("#kp-notebook-library .kp-notebook-library-each-book")
            if i >= len(books):
                break

            book = books[i]

            # Extract title, author, and cover URL before clicking
            try:
                title_el = book.query_selector("h2.kp-notebook-searchable")
                author_el = book.query_selector("p.kp-notebook-searchable")
                book_title = title_el.inner_text().strip() if title_el else "Unknown Title"
                author = author_el.inner_text().strip() if author_el else "Unknown Author"
            except Exception:
                book_title = "Unknown Title"
                author = "Unknown Author"

            author = author.removeprefix("By: ")

            try:
                img_el = book.query_selector("img")
                cover_url = img_el.get_attribute("src") if img_el else None
            except Exception:
                cover_url = None

            print(f"Scraping: {book_title}")
            book.click()

            # Wait for highlights to load
            try:
                page.wait_for_selector("#kp-notebook-annotations", timeout=15000)
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
                            "cover_url": cover_url,
                        })
                except Exception:
                    continue

            print(f"  Found {len(highlight_els)} highlights.")

        browser.close()

    print(f"Total highlights scraped: {len(highlights)}")
    return highlights
