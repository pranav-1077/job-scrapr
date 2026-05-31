from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests
from curl_cffi.const import CurlOpt

from .base import BaseScraper, Job


class JibeScraper(BaseScraper):
    """Scraper for iCIMS/Jibe-powered career sites.

    The API caps results at 100 per request regardless of limit. To retrieve all
    jobs, we first fetch the tags1 facet list then query each category separately,
    deduplicating by req_id.

    Config keys:
      careers_url — public careers listing URL; base and path are derived from it
    """

    def _get(self, base: str, path: str, **params) -> dict:
        resp = cffi_requests.get(
            f"{base}/api/jobs",
            params={"path": path, "limit": 100, **params},
            impersonate="chrome120",
            timeout=self.request_timeout,
            curl_options={CurlOpt.TIMEOUT_MS: self.request_timeout * 1000},
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_jobs(self) -> list[Job]:
        careers_url = self.company["careers_url"]
        parsed = urlparse(careers_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path

        # fetch first page to get the full category facet list
        first = self._get(base, path)
        categories = [
            f["term"]
            for f in first.get("filter", {}).get("facetList", {}).get("tags1", [])
        ]

        seen_ids: set[str] = set()
        jobs: list[Job] = []

        def _parse(data: dict) -> None:
            for item in data.get("jobs", []):
                d = item["data"]
                req_id = str(d["req_id"])
                if req_id in seen_ids:
                    continue
                seen_ids.add(req_id)
                posted_raw = d.get("posted_date", "")
                jobs.append(Job(
                    id=req_id,
                    title=d.get("title", ""),
                    location=d.get("full_location") or d.get("location_name") or "",
                    url=f"{base}{path}/{req_id}/job",
                    department=d.get("department") or "",
                    posted_at=posted_raw[:10] if posted_raw else None,
                ))

        # collect jobs from initial fetch, then re-query per category for the rest
        _parse(first)

        for cat in categories:
            if len(seen_ids) >= first.get("totalCount", 0):
                break
            data = self._get(base, path, tags1=cat)
            _parse(data)

        return jobs
