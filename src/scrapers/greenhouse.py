"""Scraper for Greenhouse-powered job boards using the public JSON API"""

import requests

from .base import BaseScraper, Job

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


class GreenhouseScraper(BaseScraper):
    """Fetches jobs from the Greenhouse public board API"""

    def fetch_jobs(self) -> list[Job]:
        """Returns all active job listings from the Greenhouse board"""
        token = self.company["board_token"]
        resp = requests.get(
            API.format(token=token),
            params={"content": "true"},
            timeout=self.request_timeout,
            headers={"User-Agent": "job-scrapr/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            # take the first department if multiple are listed
            depts = item.get("departments") or []
            dept = depts[0].get("name", "") if depts else ""

            # prefer first_published over updated_at for the post date
            raw_date = item.get("first_published") or item.get("updated_at")
            posted_at = raw_date[:10] if raw_date else None

            jobs.append(Job(
                id=str(item["id"]),
                title=item.get("title", ""),
                location=item.get("location", {}).get("name", ""),
                url=item.get("absolute_url", ""),
                department=dept,
                posted_at=posted_at,
            ))
        return jobs
