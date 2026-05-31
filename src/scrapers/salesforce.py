import re

from .base import BaseScraper, Job

_META_RE = re.compile(r'^(REQ\d+)\s*\|\s*([^|]+?)\s*\|\s*Posted', re.I)


class SalesforceScraper(BaseScraper):
    """Scraper for Salesforce Experience Cloud career sites.

    Config keys:
      careers_url      — URL of the careers listing page
      data_id_contains — substring that job <a data-id> values contain (e.g. 'REQ')
      job_url_template — URL template with {data_id} placeholder for job detail links
    """

    def fetch_jobs(self) -> list[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("playwright is not installed. Run: pip install playwright && playwright install chromium")

        careers_url = self.company["careers_url"]
        data_id_contains = self.company.get("data_id_contains", "REQ")
        job_url_template = self.company["job_url_template"]
        card_selector = f"a[data-id*='{data_id_contains}']"
        container_selector = f"lightning-layout-item:has({card_selector})"

        from playwright_stealth import Stealth

        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            page.goto(careers_url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
            # wait for first job card to appear
            page.wait_for_selector(card_selector, timeout=self.request_timeout * 1000)
            page.wait_for_timeout(2000)

            # each lightning-layout-item containing a job card has exactly 2 lines:
            # line 0 = title, line 1 = "REQ1234 | Location | Posted X"
            for container in page.locator(container_selector).all():
                lines = [l.strip() for l in container.inner_text().splitlines() if l.strip()]
                if len(lines) != 2:
                    continue
                title = lines[0]
                meta_match = _META_RE.match(lines[1])
                if not meta_match:
                    continue
                req_id = meta_match.group(1)
                location = meta_match.group(2).strip()

                # get the data-id from the <a> to construct the URL
                link = container.locator(card_selector).first
                data_id = link.get_attribute("data-id") or req_id
                url = job_url_template.format(data_id=data_id)

                jobs.append(Job(
                    id=req_id,
                    title=title,
                    url=url,
                    location=location,
                ))

            browser.close()

        return jobs
