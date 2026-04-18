from .greenhouse import GreenhouseScraper
from .lever import LeverScraper
from .workday import WorkdayScraper
from .generic import GenericScraper
from .ashby import AshbyScraper
from .base import Job

_SCRAPER_MAP = {
    "greenhouse": GreenhouseScraper,
    "lever": LeverScraper,
    "workday": WorkdayScraper,
    "generic": GenericScraper,
    "ashby": AshbyScraper,
}


def get_scraper(company: dict):
    scraper_type = company.get("type", "generic")
    cls = _SCRAPER_MAP.get(scraper_type)
    if not cls:
        raise ValueError(f"Unknown scraper type '{scraper_type}' for {company.get('name')}")
    return cls(company)
