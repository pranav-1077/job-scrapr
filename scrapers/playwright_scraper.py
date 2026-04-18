import logging
from urllib.parse import urlparse

from .base import BaseScraper, Job
from .generic import HEADERS, MAX_PAGES, _parse_jobs_from_html

log = logging.getLogger("job-scrapr")


class PlaywrightScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )

        careers_url = self.company["careers_url"]
        wait_for = self.company.get("playwright_wait_for")
        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"

        jobs = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()
        page_url: str | None = careers_url

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            while page_url and len(visited_pages) < MAX_PAGES:
                if page_url in visited_pages:
                    break
                visited_pages.add(page_url)

                # Open a fresh page per URL so client-side routers don't carry
                # over stale DOM content from the previous page into the next.
                context = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
                )
                pw_page = context.new_page()

                log.debug("  [playwright] fetching %s", page_url)
                pw_page.goto(page_url, wait_until="load", timeout=30000)

                if wait_for:
                    try:
                        pw_page.wait_for_selector(wait_for, timeout=15000)
                    except Exception:
                        log.debug("  [playwright] wait_for selector '%s' not found", wait_for)
                else:
                    # Give JS frameworks a moment to render after load
                    pw_page.wait_for_timeout(2000)

                html = pw_page.content()
                new_jobs, page_url = _parse_jobs_from_html(html, self.company, pw_page.url, base, seen_urls)
                jobs.extend(new_jobs)
                context.close()

            browser.close()

        return jobs
