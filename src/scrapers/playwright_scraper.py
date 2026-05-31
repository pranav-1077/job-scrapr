"""Scraper for JS-rendered career pages using headless Chromium via Playwright"""

import logging
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

from .base import BaseScraper, Job
from .generic import HEADERS, MAX_PAGES, _parse_jobs_from_html

log = logging.getLogger("job-scrapr")


class PlaywrightScraper(BaseScraper):
    """Renders career pages in a headless browser to capture JS-rendered job listings

    Config keys:
      careers_url        - URL of the careers listing page
      link_pattern       - substring that job hrefs must contain
      playwright_wait_for - optional CSS selector to wait for before extracting jobs
    """

    def fetch_jobs(self) -> list[Job]:
        """Returns all job listings by rendering the careers page in a headless browser"""
        careers_url = self.company["careers_url"]
        wait_for = self.company.get("playwright_wait_for")
        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"

        jobs = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()
        page_url: str | None = careers_url

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                while page_url and len(visited_pages) < MAX_PAGES:
                    if page_url in visited_pages:
                        break
                    visited_pages.add(page_url)

                    # open a fresh context per page so client-side routers
                    # don't carry stale DOM state between navigations
                    context = browser.new_context(
                        user_agent=HEADERS["User-Agent"],
                        extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
                    )
                    pw_page = context.new_page()
                    log.debug("  [playwright] fetching %s", page_url)
                    pw_page.goto(page_url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)

                    if wait_for:
                        # wait for a specific element to confirm jobs have rendered
                        try:
                            pw_page.wait_for_selector(wait_for, timeout=self.request_timeout * 1000)
                        except Exception:
                            log.debug("  [playwright] wait_for selector '%s' not found", wait_for)
                    else:
                        # give JS frameworks a moment to render after DOM is ready
                        pw_page.wait_for_timeout(2000)

                    html = pw_page.content()
                    new_jobs, page_url = _parse_jobs_from_html(html, self.company, pw_page.url, base, seen_urls)
                    jobs.extend(new_jobs)
                    context.close()
            finally:
                browser.close()

        return jobs
