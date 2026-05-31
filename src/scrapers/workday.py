"""Scraper for Workday-powered job boards using the internal CXS JSON API"""

import logging
import requests

from .base import BaseScraper, Job

JOBS_ENDPOINT = "{base}/wday/cxs/{tenant}/{path}/jobs"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
}

log = logging.getLogger("job-scrapr")


def _tenant_from_base(base: str) -> str:
    """Extracts the Workday tenant name from the base URL"""
    host = base.replace("https://", "").replace("http://", "")
    return host.split(".")[0]


class WorkdayScraper(BaseScraper):
    """Fetches jobs from the Workday CXS internal API with CSRF token handling"""

    def fetch_jobs(self) -> list[Job]:
        """Returns all active job listings from the Workday board"""
        base = self.company["workday_base"].rstrip("/")
        path = self.company["workday_path"]
        tenant = _tenant_from_base(base)
        api_url = JOBS_ENDPOINT.format(base=base, tenant=tenant, path=path)

        # prime session cookies and extract the CSRF token required by the API
        session = requests.Session()
        session.headers.update(_HEADERS)
        page_url = f"{base}/{path}"
        page_resp = session.get(page_url, timeout=self.request_timeout, allow_redirects=True)

        # Workday behind Cloudflare returns 4xx/5xx for automated requests
        if page_resp.status_code >= 400:
            log.warning(
                "Workday page returned %d for %s, consider switching to type=generic",
                page_resp.status_code, page_url,
            )
            return []

        csrf = (
            page_resp.cookies.get("CALYPSO_CSRF_TOKEN")
            or page_resp.cookies.get("wd-browser-id")
            or "fetch"
        )
        session.headers["X-Csrf-Token"] = csrf

        jobs: list[Job] = []
        offset = 0
        limit = 20

        while True:
            resp = session.post(
                api_url,
                json={"limit": limit, "offset": offset, "searchText": "", "locations": []},
                timeout=self.request_timeout,
            )
            if resp.status_code == 422:
                # some tenants return 422 on the last page rather than an empty list
                break
            resp.raise_for_status()

            data = resp.json()
            postings = data.get("jobPostings") or []
            if not postings:
                break

            for item in postings:
                bullet = (item.get("bulletFields") or [""])[0]
                ext_url = item.get("externalUrl") or f"{page_url}/job/{bullet}"
                jobs.append(Job(
                    id=bullet or str(hash(item.get("title", "") + str(offset))),
                    title=item.get("title", ""),
                    location=item.get("locationsText", ""),
                    url=ext_url,
                    department="",
                ))

            if len(postings) < limit:
                break
            offset += limit

        return jobs
