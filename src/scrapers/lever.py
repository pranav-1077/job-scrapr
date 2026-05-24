import datetime
import requests
from .base import BaseScraper, Job

API = "https://api.lever.co/v0/postings/{company}"


class LeverScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        company_id = self.company["company_id"]
        resp = requests.get(
            API.format(company=company_id),
            params={"mode": "json", "limit": 500},
            timeout=30,
            headers={"User-Agent": "job-scrapr/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data:
            cats = item.get("categories") or {}
            created_ms = item.get("createdAt")
            posted_at = (
                datetime.datetime.fromtimestamp(created_ms / 1000, tz=datetime.timezone.utc)
                .date().isoformat()
                if created_ms else None
            )
            jobs.append(Job(
                id=item["id"],
                title=item.get("text", ""),
                location=cats.get("location", ""),
                url=item.get("hostedUrl", ""),
                department=cats.get("team", ""),
                posted_at=posted_at,
            ))
        return jobs
