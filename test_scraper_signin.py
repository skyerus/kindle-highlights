"""Run with Playwright and its Chromium installed; uses only local HTML fixtures."""
import importlib.util
import unittest

from scraper import enter_email


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright is not installed')
class SignInFormTests(unittest.TestCase):
    def test_original_and_current_amazon_email_forms(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                for attributes in ['id="ap_email"', 'id="ap_email_login"', 'name="email"', 'autocomplete="username"']:
                    with self.subTest(attributes=attributes):
                        page.set_content(
                            '<input id="ap_email" style="display:none">'
                            f'<form><input {attributes}><input type="submit" value="Continue"></form>'
                        )
                        page.evaluate('''() => {
                            window.submitted = false;
                            document.querySelector('form').onsubmit = event => {
                                event.preventDefault(); window.submitted = true;
                            };
                        }''')
                        enter_email(page, 'fixture@example.test')
                        self.assertTrue(page.evaluate('window.submitted'))
                        self.assertEqual(page.locator('form input').first.input_value(), 'fixture@example.test')
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
