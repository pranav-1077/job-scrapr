import hashlib
from urllib.parse import urlparse

import requests

from .base import BaseScraper, Job

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

PAGE_SIZE = 50


class EightfoldScraper(BaseScraper):
    """Scraper for eightfold.ai-powered career sites.

    Config keys:
      careers_url      — public careers page (used to build job links)
      eightfold_domain — value of the `domain` query param (e.g. 'mlp.com')
    """

    def fetch_jobs(self) -> list[Job]:
        careers_url = self.company["careers_url"]
        domain = self.company["eightfold_domain"]
        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"
        api_base = f"{base}/api/apply/v2/jobs"

        jobs: list[Job] = []
        start = 0

        while True:
            resp = requests.get(
                api_base,
                params={"domain": domain, "start": start, "num": PAGE_SIZE, "sort_by": "relevance"},
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            positions = data.get("positions", [])
            if not positions:
                break

            for pos in positions:
                job_id = str(pos["id"])
                title = pos.get("name") or pos.get("posting_name") or ""
                location = pos.get("location") or ""
                department = pos.get("department") or ""
                url = f"{careers_url}?pid={job_id}&domain={domain}"

                uid = hashlib.md5(job_id.encode()).hexdigest()[:16]
                jobs.append(Job(
                    id=uid,
                    title=title,
                    url=url,
                    location=location,
                    department=department,
                ))

            total = data.get("count", 0)
            start += len(positions)
            if start >= total:
                break

        return jobs
