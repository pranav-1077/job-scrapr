import requests
from urllib.parse import urlparse
from .base import BaseScraper, Job

API = "https://{subdomain}.pinpointhq.com/en/jobs.json"
JOB_URL = "https://{subdomain}.pinpointhq.com/en/jobs/{job_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class PinpointScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        url = self.company["careers_url"].rstrip("/")
        subdomain = urlparse(url).hostname.split(".")[0]

        resp = requests.get(API.format(subdomain=subdomain), headers=_HEADERS, timeout=self.request_timeout)
        resp.raise_for_status()

        jobs = []
        for item in resp.json().get("data", []):
            loc = item.get("location") or {}
            dept = (item.get("department") or {})
            jobs.append(Job(
                id=str(item["id"]),
                title=item.get("title", ""),
                location=loc.get("name", "") if isinstance(loc, dict) else str(loc),
                url=item.get("url") or JOB_URL.format(subdomain=subdomain, job_id=item["id"]),
                department=dept.get("name", "") if isinstance(dept, dict) else str(dept),
            ))

        return jobs
