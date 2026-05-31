"""Generic HTML scraper using BeautifulSoup with heuristic job link detection"""

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

# URL path segments that suggest a link points to a job posting
JOB_URL_TERMS = re.compile(
    r"/(job|jobs|career|careers|position|positions|role|roles|opening|openings|"
    r"apply|hire|hiring|vacancy|vacancies|opportunity|opportunities)/",
    re.I,
)

# words in link text that suggest the link is a job title
JOB_TITLE_TERMS = re.compile(
    r"\b(engineer|developer|researcher|scientist|analyst|trader|quant|"
    r"quantitative|developer|programmer|architect|manager|director|"
    r"internship|intern|associate|strategist|designer|sre|devops|mlops|"
    r"data|software|hardware|algorithm|systems|platform|infrastructure|"
    r"machine learning|deep learning|python|c\+\+|java)\b",
    re.I,
)

NEXT_PAGE_TEXT = re.compile(r"^(next|next page|›|»|>)$", re.I)

MAX_PAGES = 20


def _uid(text: str, url: str) -> str:
    """Generates a short stable ID from job title and URL"""
    return hashlib.md5(f"{text}|{url}".encode()).hexdigest()[:16]


def _find_next_page(soup: BeautifulSoup, base: str, current_url: str) -> str | None:
    """Returns the URL of the next pagination page or None if no next page exists"""
    # prefer rel="next" as the most reliable signal
    tag = soup.find("a", rel="next", href=True)
    if tag:
        return urljoin(current_url, tag["href"])
    # fall back to text-based detection
    for a in soup.find_all("a", href=True):
        if NEXT_PAGE_TEXT.match(a.get_text(strip=True)):
            return urljoin(current_url, a["href"])
    return None


def _parse_jobs_from_html(
    html: str,
    company: dict,
    page_url: str,
    base: str,
    seen_urls: set[str],
) -> tuple[list[Job], str | None]:
    """Extracts job links from rendered HTML and returns jobs plus the next page URL"""
    soup = BeautifulSoup(html, "lxml")

    # strip nav, footer, and scripts to reduce false positives
    for tag in soup.find_all(["nav", "footer", "script", "style"]):
        tag.decompose()

    link_pattern = company.get("link_pattern")
    title_selector = company.get("title_selector")
    jobs = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]

        # skip empty, very short, or very long link text
        # length check is skipped when title_selector is set since the selector
        # extracts the title independently of the anchor text length
        if not text or len(text) < 4 or (not title_selector and len(text) > 200):
            continue

        # skip links to documents and media files
        if re.search(r"\.(pdf|doc|docx|xls|xlsx|png|jpg|jpeg|gif|svg|zip)(\?|$)", href, re.I):
            continue

        # resolve relative URLs
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = base + href
        elif not href.startswith("http"):
            href = urljoin(page_url, href)

        if link_pattern and link_pattern not in href:
            continue

        # require either the URL or the link text to look job-related
        url_looks_like_job = bool(JOB_URL_TERMS.search(href))
        text_looks_like_job = bool(JOB_TITLE_TERMS.search(text))
        if not (url_looks_like_job or text_looks_like_job):
            continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        if title_selector:
            title_el = a.select_one(title_selector)
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
        else:
            title = text

        uid = _uid(title, href)
        jobs.append(Job(id=uid, title=title, url=href, location="", department=""))

    next_page = _find_next_page(soup, base, page_url)
    return jobs, next_page


class GenericScraper(BaseScraper):
    """Scrapes career pages by fetching HTML and applying heuristic job link detection"""

    def fetch_jobs(self) -> list[Job]:
        """Returns all job listings found by crawling the careers page"""
        careers_url = self.company["careers_url"]
        base = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"

        jobs = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()
        page_url: str | None = careers_url

        while page_url and len(visited_pages) < MAX_PAGES:
            if page_url in visited_pages:
                break
            visited_pages.add(page_url)

            resp = requests.get(page_url, headers=HEADERS, timeout=self.request_timeout, allow_redirects=True)
            resp.raise_for_status()

            new_jobs, page_url = _parse_jobs_from_html(resp.text, self.company, page_url, base, seen_urls)
            jobs.extend(new_jobs)

        return jobs
