from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    id: str
    title: str
    url: str
    location: str = ""
    department: str = ""
    company: str = ""  # filled in by main after scraping

    def matches_filters(self, keywords: list[str]) -> bool:
        if not keywords:
            return True
        text = f"{self.title} {self.department}".lower()
        return any(kw.lower() in text for kw in keywords)


class BaseScraper:
    def __init__(self, company: dict):
        self.company = company

    def fetch_jobs(self) -> list[Job]:
        raise NotImplementedError
