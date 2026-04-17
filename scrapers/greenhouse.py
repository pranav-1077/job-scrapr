import requests
from .base import BaseScraper, Job

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


class GreenhouseScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        token = self.company["board_token"]
        resp = requests.get(
            API.format(token=token),
            params={"content": "true"},
            timeout=30,
            headers={"User-Agent": "job-scrapr/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            dept = ""
            depts = item.get("departments") or []
            if depts:
                dept = depts[0].get("name", "")

            jobs.append(Job(
                id=str(item["id"]),
                title=item.get("title", ""),
                location=item.get("location", {}).get("name", ""),
                url=item.get("absolute_url", ""),
                department=dept,
            ))
        return jobs
