"""daily job board monitor for quant / trading firms"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import requests
import yaml
from dotenv import load_dotenv

from scrapers import get_scraper
from state import JobState
from notifier import EmailNotifier

log = logging.getLogger("job-scrapr")


def load_config(config_path: Path, companies_path: Path) -> tuple[dict, list[dict]]:
    """Loads config and companies from YAML and injects email credentials from environment variables"""
    load_dotenv()
    with open(config_path) as f:
        config = yaml.safe_load(f)
    with open(companies_path) as f:
        companies = yaml.safe_load(f)["companies"]
    config.setdefault("email", {})
    config["email"]["sender"] = os.environ["EMAIL_SENDER"]
    config["email"]["recipients"] = [r.strip() for r in os.environ["EMAIL_RECIPIENTS"].split(",")]
    return config, companies


@dataclass
class _ScrapeResult:
    name: str
    jobs: list
    new_jobs: list
    removed_jobs: list
    error: Optional[str] = None
    catalog_only: bool = False


def _scrape_one(
    company: dict,
    state: JobState,
    keyword_filters: list[str],
    catalog_only: bool,
    cutoff: Optional[date],
    request_timeout: int = 30,
    playwright_timeout: int = 120,
) -> _ScrapeResult:
    """Runs a single company's scraper and returns the diff against stored state"""
    name = company["name"]
    log.info("Scraping %s …", name)
    try:
        # playwright-based scrapers need more time per page than simple HTTP requests
        timeout = playwright_timeout if company.get("type") in ("playwright", "salesforce") else request_timeout
        scraper = get_scraper(company, timeout)
        jobs = scraper.fetch_jobs()
        log.debug("  [%s] fetched %d job(s)", name, len(jobs))

        # on the very first run with --catalog-only, snapshot without alerting
        if catalog_only and state.is_first_run(name):
            log.info("  [%s] first run — catalogued %d job(s)", name, len(jobs))
            return _ScrapeResult(name=name, jobs=jobs, new_jobs=[], removed_jobs=[], catalog_only=True)

        new_jobs = state.get_new_jobs(name, jobs)
        removed_jobs = state.get_removed_jobs(name, jobs)

        # date and keyword filters apply only to new-job alerts, not to state or removed detection
        if cutoff:
            new_jobs = [j for j in new_jobs if j.posted_at is None or date.fromisoformat(j.posted_at) >= cutoff]
        if keyword_filters:
            new_jobs = [j for j in new_jobs if j.matches_filters(keyword_filters)]

        log.info("  [%s] %d new, %d removed", name, len(new_jobs), len(removed_jobs))
        return _ScrapeResult(name=name, jobs=jobs, new_jobs=new_jobs, removed_jobs=removed_jobs)
    except Exception as exc:
        log.warning("  [%s] ERROR: %s", name, exc)
        return _ScrapeResult(name=name, jobs=[], new_jobs=[], removed_jobs=[], error=str(exc))


def _run_batch(
    companies: list[dict],
    executor: ThreadPoolExecutor,
    state: JobState,
    keyword_filters: list[str],
    catalog_only: bool,
    cutoff: Optional[date],
    request_timeout: int = 30,
    playwright_timeout: int = 120,
) -> list[_ScrapeResult]:
    """Submits all companies to the executor and collects results as they complete"""
    if not companies:
        return []
    futures = {
        executor.submit(
            _scrape_one, c, state, keyword_filters, catalog_only, cutoff,
            request_timeout, playwright_timeout
        ): c
        for c in companies
    }
    # as_completed yields futures in completion order, not submission order
    return [future.result() for future in as_completed(futures)]


def run(config: dict, companies: list[dict], dry_run: bool = False, catalog_only: bool = False):
    """Orchestrates the full scrape, diff, state update, and email dispatch"""

    # resolve relative paths against the repo root, load config params
    raw_data_dir = config.get("data_dir", "./data")
    data_dir = raw_data_dir if Path(raw_data_dir).is_absolute() else Path(__file__).parent.parent / raw_data_dir
    state = JobState(str(data_dir))
    notifier = EmailNotifier(config["email"])
    keyword_filters: list[str] = config.get("keyword_filters", [])
    max_workers: int = config.get("max_workers", 10)
    request_timeout: int = config.get("request_timeout", 30)
    playwright_scraper_timeout: int = config.get("playwright_scraper_timeout", 120)
    notify_removed: bool = config.get("notify_removed_jobs", True)
    max_job_age_days: int = config.get("max_job_age_days", 60)

    # ignore jobs posted before this date to reduce noise from old postings
    cutoff: Optional[date] = date.today() - timedelta(days=max_job_age_days) if max_job_age_days else None

    # skip disabled companies and email-only entries
    active_companies = [c for c in companies if not c.get("disabled") and c.get("type") != "email_only"]
    email_only_companies: list[dict] = [c for c in companies if not c.get("disabled") and c.get("type") == "email_only"]

    # submit playwright/salesforce scrapers first so they claim worker slots immediately
    slow = [c for c in active_companies if c.get("type") in ("playwright", "salesforce")]
    fast = [c for c in active_companies if c.get("type") not in ("playwright", "salesforce")]

    log.info("Scraping %d companies (%d Playwright, %d fast) …", len(active_companies), len(slow), len(fast))

    # parallelized scrape execution
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        completed_results = _run_batch(
            slow + fast, executor, state, keyword_filters, catalog_only, cutoff,
            request_timeout, playwright_scraper_timeout
        )
    finally:
        executor.shutdown(wait=True)

    # aggregate results across all scrapers
    all_new_jobs: list[dict] = []
    all_removed_jobs: list[dict] = []
    errors: list[str] = []

    for result in completed_results:
        if result.error:
            errors.append(f"{result.name}: {result.error}")
            continue
        if result.catalog_only:
            # catalog-only first runs just snapshot state without sending alerts
            state.update(result.name, result.jobs)
            continue
        for j in result.new_jobs:
            j.company = result.name
            all_new_jobs.append(vars(j))
        all_removed_jobs.extend(result.removed_jobs)
        state.update(result.name, result.jobs)

    if errors:
        log.warning("Completed with %d error(s):\n  %s", len(errors), "\n  ".join(errors))

    should_email = bool(all_new_jobs) or (notify_removed and bool(all_removed_jobs))
    removed_for_email = all_removed_jobs if notify_removed else []

    if should_email and not dry_run:
        log.info("Sending email — %d new, %d removed posting(s) …",
                 len(all_new_jobs), len(all_removed_jobs))
        try:
            notifier.send(all_new_jobs, email_only_companies, removed_for_email)
            log.info("Email sent.")
            state.save()
        except Exception as exc:
            log.error("Failed to send email: %s", exc)
            log.warning("State not saved — new jobs will be re-reported on next successful run.")
    elif should_email:
        log.info("[dry-run] Would send email with %d new, %d removed posting(s).",
                 len(all_new_jobs), len(all_removed_jobs))
        for j in all_new_jobs:
            log.info("  [NEW]     [%s] %s — %s", j["company"], j["title"], j["url"])
        for r in all_removed_jobs:
            log.info("  [REMOVED] [%s] %s — %s", r["company"], r["title"], r.get("url", ""))
        state.save()
    else:
        log.info("No new or removed jobs found — no email sent.")
        state.save()


def verify_boards(companies: list[dict]):
    """Sends a HEAD or GET request to each board URL and reports which are reachable"""
    log.info("Verifying %d company boards …", len(companies))
    ok, fail = [], []

    for company in companies:
        if company.get("disabled"):
            continue

        name = company["name"]
        t = company.get("type", "generic")

        if t == "email_only":
            log.info("  –  %s  (email-only, skipping)", name)
            continue

        # derive the canonical URL to check based on scraper type
        if t == "greenhouse":
            url = f"https://boards-api.greenhouse.io/v1/boards/{company['board_token']}/jobs"
        elif t == "lever":
            url = f"https://api.lever.co/v0/postings/{company['company_id']}"
        elif t == "ashby":
            url = f"https://api.ashbyhq.com/posting-api/job-board/{company['board_token']}"
        elif t == "workday":
            url = company["workday_base"]
        else:
            url = company.get("careers_url", "")

        try:
            headers = {"User-Agent": "job-scrapr/1.0"}
            r = requests.head(url, timeout=10, allow_redirects=True, headers=headers)
            # some servers reject HEAD; fall back to GET in that case
            if r.status_code == 405:
                r = requests.get(url, timeout=10, allow_redirects=True, headers=headers)
            if r.status_code < 400:
                log.info("  ✓  %s  (%s)", name, url)
                ok.append(name)
            else:
                log.warning("  ✗  %s — HTTP %d  (%s)", name, r.status_code, url)
                fail.append((name, r.status_code, url))
        except Exception as exc:
            log.warning("  ✗  %s — %s", name, exc)
            fail.append((name, "error", url))

    print(f"\n{len(ok)} reachable, {len(fail)} failed.")
    if fail:
        print("Failed:")
        for name, code, url in fail:
            print(f"  {name}  [{code}]  {url}")


def main():
    """Parses CLI args, sets up logging, and dispatches to run or verify_boards"""

    parser = argparse.ArgumentParser(description="Scrape trading firm job boards and email new postings.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--companies", default="companies.yaml", help="Path to companies.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't send email")
    parser.add_argument("--catalog-only", action="store_true",
                        help="On first run, record all current jobs without emailing")
    parser.add_argument("--verify-boards", action="store_true", help="Check all board URLs are reachable")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    log_file = root / "logs" / "job-scrapr.log"
    log_file.parent.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            # mode="w" truncates the log on each run so it only shows the latest
            logging.FileHandler(log_file, mode="w"),
        ],
    )

    # resolve config paths relative to repo root if not absolute
    config_path = Path(args.config) if Path(args.config).is_absolute() else root / args.config
    companies_path = Path(args.companies) if Path(args.companies).is_absolute() else root / args.companies
    config, companies = load_config(config_path, companies_path)

    if args.verify_boards:
        verify_boards(companies)
        return

    run(config, companies, dry_run=args.dry_run, catalog_only=args.catalog_only)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger("job-scrapr").exception("Fatal error")
        sys.exit(1)
