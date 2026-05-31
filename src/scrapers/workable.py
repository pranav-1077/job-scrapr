"""Scraper for Workable-powered job boards using the public API"""

import requests
from urllib.parse import urlparse

from .base import BaseScraper, Job

API = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
JOB_URL = "https://apply.workable.com/{slug}/j/{shortcode}/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
}


class WorkableScraper(BaseScraper):
    """Fetches jobs from the Workable public jobs API"""

    def fetch_jobs(self) -> list[Job]:
        """Returns all active job listings from the Workable board"""
        url = self.company["careers_url"].rstrip("/")
        # extract the account slug from the careers URL path
        slug = urlparse(url).path.strip("/").split("/")[0]

        resp = requests.post(
            API.format(slug=slug),
            headers=_HEADERS,
            json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
            timeout=self.request_timeout,
        )
        resp.raise_for_status()

        jobs = []
        for item in resp.json().get("results", []):
            loc = item.get("location") or {}
            city = loc.get("city", "")
            region = loc.get("region", "")
            location = ", ".join(filter(None, [city, region]))
            shortcode = item.get("shortcode", "")
            dept = ", ".join(item.get("department") or [])
            jobs.append(Job(
                id=str(item.get("id", shortcode)),
                title=item.get("title", ""),
                location=location,
                url=JOB_URL.format(slug=slug, shortcode=shortcode),
                department=dept,
                posted_at=(item.get("published") or "")[:10] or None,
            ))

        return jobs
