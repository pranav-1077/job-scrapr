"""Scraper registry mapping company type strings to scraper classes"""

from .ashby import AshbyScraper
from .cffi_scraper import CffiScraper
from .eightfold import EightfoldScraper
from .generic import GenericScraper
from .greenhouse import GreenhouseScraper
from .jibe import JibeScraper
from .lever import LeverScraper
from .linkedin import LinkedInScraper
from .pinpoint import PinpointScraper
from .playwright_scraper import PlaywrightScraper
from .salesforce import SalesforceScraper
from .workable import WorkableScraper
from .workday import WorkdayScraper
from .wp_ajax import WPAjaxScraper

from .base import Job

_SCRAPER_MAP = {
    "ashby": AshbyScraper,
    "cffi": CffiScraper,
    "eightfold": EightfoldScraper,
    "generic": GenericScraper,
    "greenhouse": GreenhouseScraper,
    "jibe": JibeScraper,
    "lever": LeverScraper,
    "linkedin": LinkedInScraper,
    "pinpoint": PinpointScraper,
    "playwright": PlaywrightScraper,
    "salesforce": SalesforceScraper,
    "workable": WorkableScraper,
    "workday": WorkdayScraper,
    "wp_ajax": WPAjaxScraper,
}


def get_scraper(company: dict, request_timeout: int = 30):
    """Instantiates and returns the appropriate scraper for the given company config"""
    scraper_type = company.get("type", "generic")
    cls = _SCRAPER_MAP.get(scraper_type)
    if not cls:
        raise ValueError(f"Unknown scraper type '{scraper_type}' for {company.get('name')}")
    return cls(company, request_timeout)
