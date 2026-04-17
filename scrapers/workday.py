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


def _tenant_from_base(base: str) -> str:
    host = base.replace("https://", "").replace("http://", "")
    return host.split(".")[0]


class WorkdayScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        base = self.company["workday_base"].rstrip("/")
        path = self.company["workday_path"]
        tenant = _tenant_from_base(base)
        api_url = JOBS_ENDPOINT.format(base=base, tenant=tenant, path=path)

        # Workday requires a CSRF token obtained from the page session.
        session = requests.Session()
        session.headers.update(_HEADERS)

        # Prime session cookies + grab CSRF token
        page_url = f"{base}/{path}"
        page_resp = session.get(page_url, timeout=30, allow_redirects=True)
        # Workday behind Cloudflare returns 500 for automated requests;
        # log a warning and return empty rather than raising.
        if page_resp.status_code >= 400:
            import logging
            logging.getLogger("job-scrapr").warning(
                "Workday page returned %d for %s — may require a browser. "
                "Consider switching to type=generic in companies.yaml.",
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
                timeout=30,
            )
            if resp.status_code == 422:
                # Some tenants return 422; fall back to returning what we have
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
