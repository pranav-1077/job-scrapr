"""Base classes and shared data types for all scrapers"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    """Represents a single job posting"""
    id: str
    title: str
    url: str
    location: str = ""
    department: str = ""
    company: str = ""
    posted_at: Optional[str] = None

    def matches_filters(self, keywords: list[str]) -> bool:
        """Returns True if the job title or department contains any of the given keywords"""
        if not keywords:
            return True
        text = f"{self.title} {self.department}".lower()
        return any(kw.lower() in text for kw in keywords)


class BaseScraper:
    """Base class all scrapers inherit from"""
    def __init__(self, company: dict, request_timeout: int = 30):
        self.company = company
        self.request_timeout = request_timeout

    def fetch_jobs(self) -> list[Job]:
        """Fetches and returns all current job listings for this company"""
        raise NotImplementedError
