"""Scraper for LinkedIn company job pages using the public guest API"""

import re
import time
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Job

GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_JOB_ID_RE = re.compile(r"-(\d+)$")


def _parse_page(html: str) -> list[Job]:
    """Parses a LinkedIn guest API HTML response and extracts job listings"""
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for li in soup.find_all("li"):
        title_el = li.find("h3")
        link_el = li.find("a", href=True)
        loc_el = li.find("span", class_=lambda c: c and "location" in c.lower())
        time_el = li.find("time")

        if not title_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        # strip tracking params from the URL
        url = link_el["href"].split("?")[0]
        location = loc_el.get_text(strip=True) if loc_el else ""
        posted_at = time_el.get("datetime", "")[:10] if time_el else None

        # use the numeric job ID at the end of the URL as a stable identifier
        m = _JOB_ID_RE.search(url)
        job_id = m.group(1) if m else url

        jobs.append(Job(
            id=job_id,
            title=title,
            url=url,
            location=location,
            posted_at=posted_at or None,
        ))
    return jobs


class LinkedInScraper(BaseScraper):
    """Fetches jobs from the LinkedIn public guest API without requiring login"""

    def fetch_jobs(self) -> list[Job]:
        """Returns all job listings by paginating through the LinkedIn guest API"""
        company_id = self.company["linkedin_company_id"]
        jobs = []
        start = 0

        while True:
            resp = requests.get(
                GUEST_API,
                params={"f_C": company_id, "start": start},
                headers=HEADERS,
                timeout=self.request_timeout,
            )
            resp.raise_for_status()

            page_jobs = _parse_page(resp.text)
            if not page_jobs:
                break

            jobs.extend(page_jobs)
            start += PAGE_SIZE
            # small delay to avoid rate limiting
            time.sleep(0.5)

        return jobs
