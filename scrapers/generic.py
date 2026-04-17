import hashlib
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Job

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Patterns that suggest a link is a job posting (not just navigation)
JOB_URL_TERMS = re.compile(
    r"/(job|jobs|career|careers|position|positions|role|roles|opening|openings|"
    r"apply|hire|hiring|vacancy|vacancies|opportunity|opportunities)/",
    re.I,
)

# Words that strongly suggest a link text is a job title
JOB_TITLE_TERMS = re.compile(
    r"\b(engineer|developer|researcher|scientist|analyst|trader|quant|"
    r"quantitative|developer|programmer|architect|manager|director|"
    r"internship|intern|associate|strategist|designer|sre|devops|mlops|"
    r"data|software|hardware|algorithm|systems|platform|infrastructure|"
    r"machine learning|deep learning|python|c\+\+|java)\b",
    re.I,
)

# Link text that indicates a "next page" pagination link
NEXT_PAGE_TEXT = re.compile(r"^(next|next page|›|»|>)$", re.I)

MAX_PAGES = 20


def _uid(text: str, url: str) -> str:
    return hashlib.md5(f"{text}|{url}".encode()).hexdigest()[:16]


def _find_next_page(soup: BeautifulSoup, base: str, current_url: str) -> str | None:
    # Prefer rel="next"
    tag = soup.find("a", rel="next", href=True)
    if tag:
        return urljoin(current_url, tag["href"])
    # Fall back to text-based next link
    for a in soup.find_all("a", href=True):
        if NEXT_PAGE_TEXT.match(a.get_text(strip=True)):
            return urljoin(current_url, a["href"])
    return None


class GenericScraper(BaseScraper):
    def fetch_jobs(self) -> list[Job]:
        careers_url = self.company["careers_url"]
        link_pattern = self.company.get("link_pattern")
        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"

        jobs = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()
        page_url: str | None = careers_url

        while page_url and len(visited_pages) < MAX_PAGES:
            if page_url in visited_pages:
                break
            visited_pages.add(page_url)

            resp = requests.get(page_url, headers=HEADERS, timeout=30, allow_redirects=True)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            # Remove navigation, footer, header noise
            for tag in soup.find_all(["nav", "footer", "header", "script", "style"]):
                tag.decompose()

            for a in soup.find_all("a", href=True):
                text = a.get_text(" ", strip=True)
                href = a["href"]

                # Skip empty / very long / obviously non-job links
                if not text or len(text) < 4 or len(text) > 200:
                    continue

                # Resolve URL
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = base + href
                elif not href.startswith("http"):
                    href = urljoin(page_url, href)

                # Filter by optional link_pattern from config
                if link_pattern and link_pattern not in href:
                    continue

                # Heuristic: either the URL or the link text suggests a job
                url_looks_like_job = bool(JOB_URL_TERMS.search(href))
                text_looks_like_job = bool(JOB_TITLE_TERMS.search(text))

                if not (url_looks_like_job or text_looks_like_job):
                    continue

                # Deduplicate by URL — prefer the first (usually longer/more descriptive) link text
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                uid = _uid(text, href)
                jobs.append(Job(id=uid, title=text, url=href, location="", department=""))

            page_url = _find_next_page(soup, base, page_url)

        return jobs
