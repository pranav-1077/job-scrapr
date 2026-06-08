"""Scraper for Gem-powered job boards using the public GraphQL API"""

import requests

from .base import BaseScraper, Job

_ENDPOINT = "https://jobs.gem.com/api/public/graphql/batch"
_BOARD_URL = "https://jobs.gem.com/{slug}/{ext_id}"

_QUERY = """query JobBoardList($boardId: String!) {
  oatsExternalJobPostings(boardId: $boardId) {
    jobPostings {
      extId
      title
      locations { name isRemote }
      job { department { name } }
    }
  }
}"""


class GemScraper(BaseScraper):
    """Fetches jobs from Gem-powered job boards via the public GraphQL API"""

    def fetch_jobs(self) -> list[Job]:
        slug = self.company["board_slug"]
        payload = [{"operationName": "JobBoardList", "variables": {"boardId": slug}, "query": _QUERY}]
        resp = requests.post(
            _ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=self.request_timeout,
        )
        resp.raise_for_status()

        postings = resp.json()[0]["data"]["oatsExternalJobPostings"]["jobPostings"]
        jobs = []
        for item in postings:
            locs = item.get("locations") or []
            location = locs[0]["name"] if locs else ""
            dept = ((item.get("job") or {}).get("department") or {}).get("name", "")
            jobs.append(Job(
                id=item["extId"],
                title=item["title"],
                location=location,
                url=_BOARD_URL.format(slug=slug, ext_id=item["extId"]),
                department=dept,
            ))
        return jobs
