import hashlib
import time
import requests
from .base import BaseScraper, Job

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
_RETRIES = 3
_BACKOFF = [5, 15]  # seconds to wait before retry 2 and 3


class AshbyScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        slug = self.company["board_token"]
        last_exc = None
        for attempt in range(_RETRIES):
            if attempt:
                time.sleep(_BACKOFF[attempt - 1])
            try:
                resp = requests.get(
                    API.format(slug=slug),
                    timeout=self.request_timeout,
                    headers={"User-Agent": "job-scrapr/1.0"},
                )
                resp.raise_for_status()
                break
            except requests.exceptions.Timeout as exc:
                last_exc = exc
        else:
            raise last_exc

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
