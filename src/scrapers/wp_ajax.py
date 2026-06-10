"""Scraper for WordPress admin-ajax.php job listing pages"""

import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from curl_cffi.const import CurlOpt  # re-applied after impersonate resets curl options

from .base import BaseScraper, Job

_RETRIES = 3
_BACKOFF = [3, 8]  # seconds to wait before each retry after a transient block
# statuses that come from intermittent anti-bot or rate-limit responses worth retrying
_RETRYABLE = (403, 429)

_SITE_CONFIGS = {
    "https://www.citadel.com/careers/open-opportunities/": {
        "selected_sections": "388,389,387,390",
        "title_selector": "h2.visible",
        "location_selector": "span.careers-listing-card__location",
    },
    "https://www.citadelsecurities.com/careers/open-opportunities/": {
        "selected_sections": "323,325,324,326",
        "title_selector": "h2.visible",
        "location_selector": "div.careers-listing-card__location",
    },
}


class WPAjaxScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        careers_url = self.company["careers_url"]
        cfg = _SITE_CONFIGS[careers_url]

        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"
        ajax_url = f"{base}/wp-admin/admin-ajax.php"

        curl_opts = {CurlOpt.TIMEOUT_MS: self.request_timeout * 1000}
        data = [
            ("action", "careers_listing_filter"),
            ("current_page", "1"),
            ("sort_order", "DESC"),
            ("per_page", "200"),
            ("selected-job-sections", cfg["selected_sections"]),
            ("jobTitle", ""),
        ]

        # retry the intermittent Cloudflare 403 with backoff before giving up
        for attempt in range(_RETRIES):
            if attempt:
                time.sleep(_BACKOFF[attempt - 1])
            resp = cffi_requests.post(
                ajax_url,
                data=data,
                headers={"Referer": careers_url},
                impersonate="chrome",
                timeout=self.request_timeout,
                curl_options=curl_opts,
            )
            if resp.status_code not in _RETRYABLE:
                break
        resp.raise_for_status()

        soup = BeautifulSoup(resp.json()["content"], "lxml")
        jobs: list[Job] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/careers/details/" not in href or href in seen:
                continue
            seen.add(href)

            title_el = a.select_one(cfg["title_selector"])
            title = title_el.get_text(strip=True) if title_el else a.get("data-position", "")
            loc_el = a.select_one(cfg["location_selector"])
            location = loc_el.get_text(strip=True) if loc_el else ""

            if not title or len(title) < 4:
                continue

            slug = href.rstrip("/").rsplit("/", 1)[-1]
            jobs.append(Job(id=slug, title=title, url=href, location=location))

        return jobs
