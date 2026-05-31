from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    id: str
    title: str
    url: str
    location: str = ""
    department: str = ""
    company: str = ""  # filled in by main after scraping
    posted_at: Optional[str] = None  # ISO date string, only set for API-based boards

    def matches_filters(self, keywords: list[str]) -> bool:
        if not keywords:
            return True
        text = f"{self.title} {self.department}".lower()
        return any(kw.lower() in text for kw in keywords)


class BaseScraper:
    def __init__(self, company: dict, request_timeout: int = 30):
        self.company = company
        self.request_timeout = request_timeout

    def fetch_jobs(self) -> list[Job]:
        raise NotImplementedError
