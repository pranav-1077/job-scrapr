import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from curl_cffi.const import CurlOpt

from .base import BaseScraper, Job

MAX_PAGES = 20


class CffiScraper(BaseScraper):
    """Scraper for Cloudflare-protected sites using curl_cffi browser impersonation.

    Config keys:
      careers_url    — URL of the careers listing page
      link_pattern   — substring that job hrefs must contain
      title_selector — CSS selector for the title element within each job <a>
      location_selector — CSS selector for the location element within each job <a>
    """

    def fetch_jobs(self) -> list[Job]:
        careers_url = self.company["careers_url"]
        link_pattern = self.company.get("link_pattern", "")
        title_selector = self.company.get("title_selector", "")
        location_selector = self.company.get("location_selector", "")
        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"

        jobs: list[Job] = []
        seen_urls: set[str] = set()
        page_url: str | None = careers_url
        pages_visited = 0

        while page_url and pages_visited < MAX_PAGES:
            pages_visited += 1
            resp = cffi_requests.get(
                page_url,
                impersonate="chrome120",
                timeout=self.request_timeout,
                # curl_easy_impersonate() resets all curl options (including TIMEOUT_MS),
                # so re-apply the timeout via curl_options, which are set after impersonation.
                curl_options={CurlOpt.TIMEOUT_MS: self.request_timeout * 1000},
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("/"):
                    href = base + href
                elif href.startswith("//"):
                    href = "https:" + href
                elif not href.startswith("http"):
                    href = urljoin(page_url, href)

                if link_pattern and link_pattern not in href:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                if title_selector:
                    title_el = a.select_one(title_selector)
                    title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
                else:
                    title = a.get_text(" ", strip=True)

                if location_selector:
                    loc_el = a.select_one(location_selector)
                    location = loc_el.get_text(" ", strip=True) if loc_el else ""
                else:
                    location = ""

                if not title or len(title) < 4:
                    continue

                # use URL slug as stable id
                slug = href.rstrip("/").rsplit("/", 1)[-1]
                jobs.append(Job(id=slug, title=title, url=href, location=location))

            # follow URL-based pagination
            next_a = soup.find("a", class_=re.compile(r"next", re.I), href=True)
            if not next_a:
                next_a = soup.find("a", rel="next", href=True)
            if next_a:
                next_href = next_a["href"]
                if next_href.startswith("/"):
                    next_href = base + next_href
                elif not next_href.startswith("http"):
                    next_href = urljoin(page_url, next_href)
                page_url = next_href if next_href not in seen_urls else None
            else:
                page_url = None

        return jobs
