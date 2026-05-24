import hashlib
import requests
from .base import BaseScraper, Job

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class AshbyScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        slug = self.company["board_token"]
        resp = requests.get(
            API.format(slug=slug),
            timeout=30,
            headers={"User-Agent": "job-scrapr/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            uid = hashlib.md5(item["id"].encode()).hexdigest()[:16]
            raw_date = item.get("publishedAt")
            posted_at = raw_date[:10] if raw_date else None
            jobs.append(Job(
                id=uid,
                title=item.get("title", ""),
                location=item.get("location", ""),
                url=item.get("jobUrl", ""),
                department=item.get("department", ""),
                posted_at=posted_at,
            ))
        return jobs
