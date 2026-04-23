#!/usr/bin/env python3
"""job-scrapr — daily job board monitor for quant / trading firms."""

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from scrapers import get_scraper
from state import JobState
from notifier import EmailNotifier

load_dotenv()

log = logging.getLogger("job-scrapr")


# ── Config loading ────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict | list:
    with open(path) as f:
        return yaml.safe_load(f)


def load_config(config_path: Path) -> dict:
    config = load_yaml(config_path)
    email = config.setdefault("email", {})
    if not email.get("sender"):
        email["sender"] = os.environ["EMAIL_SENDER"]
    if not email.get("recipients"):
        raw = os.environ["EMAIL_RECIPIENTS"]
        email["recipients"] = [r.strip() for r in raw.split(",")]
    return config


def load_companies(companies_path: Path) -> list[dict]:
    data = load_yaml(companies_path)
    return data["companies"]


# ── Parallel scraping ─────────────────────────────────────────────────────────

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
) -> _ScrapeResult:
    name = company["name"]
    log.info("Scraping %s …", name)
    try:
        scraper = get_scraper(company)
        jobs = scraper.fetch_jobs()
        log.debug("  [%s] fetched %d job(s)", name, len(jobs))
        if catalog_only and state.is_first_run(name):
            log.info("  [%s] first run — catalogued %d job(s)", name, len(jobs))
            return _ScrapeResult(name=name, jobs=jobs, new_jobs=[], removed_jobs=[], catalog_only=True)
        new_jobs = state.get_new_jobs(name, jobs)
        removed_jobs = state.get_removed_jobs(name, jobs)
        # Date and keyword filters apply only to new-job alerts, not to state or removed detection.
        if cutoff:
            new_jobs = [j for j in new_jobs if j.posted_at is None or date.fromisoformat(j.posted_at) >= cutoff]
        if keyword_filters:
            new_jobs = [j for j in new_jobs if j.matches_filters(keyword_filters)]
        log.info("  [%s] %d new, %d removed", name, len(new_jobs), len(removed_jobs))
        return _ScrapeResult(name=name, jobs=jobs, new_jobs=new_jobs, removed_jobs=removed_jobs)
    except Exception as exc:
        log.warning("  [%s] ERROR: %s", name, exc)
        return _ScrapeResult(name=name, jobs=[], new_jobs=[], removed_jobs=[], error=str(exc))


# ── Main scrape loop ──────────────────────────────────────────────────────────

def _run_batch(
    companies: list[dict],
    executor: ThreadPoolExecutor,
    state: JobState,
    keyword_filters: list[str],
    catalog_only: bool,
    cutoff: Optional[date],
    total_timeout: int,
) -> tuple[list[_ScrapeResult], list[str]]:
    """Submit a batch of companies to the executor and collect results."""
    if not companies:
        return [], []
    future_to_company = {
        executor.submit(_scrape_one, c, state, keyword_filters, catalog_only, cutoff): c
        for c in companies
    }
    completed: list[_ScrapeResult] = []
    timed_out: list[str] = []
    try:
        for future in as_completed(future_to_company, timeout=total_timeout):
            completed.append(future.result())
    except FuturesTimeoutError:
        for future, company in future_to_company.items():
            if not future.done():
                timed_out.append(company["name"])
                log.warning("Scraper timed out (hung): %s", company["name"])
    return completed, timed_out


def run(config: dict, companies: list[dict], *, dry_run: bool = False, catalog_only: bool = False):
    raw_data_dir = config.get("data_dir", "./data")
    data_dir = raw_data_dir if Path(raw_data_dir).is_absolute() else Path(__file__).parent / raw_data_dir
    state = JobState(str(data_dir))
    notifier = EmailNotifier(config["email"])
    keyword_filters: list[str] = config.get("keyword_filters", [])
    max_workers: int = config.get("max_workers", 10)
    scraper_timeout: int = config.get("scraper_timeout", 60)
    playwright_scraper_timeout: int = config.get("playwright_scraper_timeout", 120)
    notify_removed: bool = config.get("notify_removed_jobs", True)
    max_job_age_days: int = config.get("max_job_age_days", 60)
    cutoff: Optional[date] = date.today() - timedelta(days=max_job_age_days) if max_job_age_days else None

    active_companies = [c for c in companies if not c.get("disabled") and c.get("type") != "email_only"]
    email_only_companies: list[dict] = [c for c in companies if not c.get("disabled") and c.get("type") == "email_only"]

    fast = [c for c in active_companies if c.get("type") != "playwright"]
    slow = [c for c in active_companies if c.get("type") == "playwright"]

    completed_results: list[_ScrapeResult] = []
    timed_out_names: list[str] = []

    # Playwright scrapers are submitted first so they get immediate worker slots.
    # Fast scrapers fill remaining workers in parallel rather than waiting for a second phase.
    # Total budget = playwright ceiling + one fast-scraper ceiling to cover stragglers.
    total_timeout = playwright_scraper_timeout + scraper_timeout
    log.info("Scraping %d companies (%d Playwright, %d fast) …", len(active_companies), len(slow), len(fast))

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        completed_results, timed_out_names = _run_batch(
            slow + fast, executor, state, keyword_filters, catalog_only, cutoff, total_timeout
        )
    finally:
        # Don't block shutdown on threads that are genuinely stuck.
        executor.shutdown(wait=False, cancel_futures=True)

    all_new_jobs: list[dict] = []
    all_removed_jobs: list[dict] = []
    errors: list[str] = [f"{n}: timed out after {total_timeout}s" for n in timed_out_names]

    for result in completed_results:
        if result.error:
            errors.append(f"{result.name}: {result.error}")
            continue
        if result.catalog_only:
            state.update(result.name, result.jobs)
            continue
        for j in result.new_jobs:
            j.company = result.name
            all_new_jobs.append(vars(j))
        all_removed_jobs.extend(result.removed_jobs)
        state.update(result.name, result.jobs)

    state.save()

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
        except Exception as exc:
            log.error("Failed to send email: %s", exc)
    elif should_email:
        log.info("[dry-run] Would send email with %d new, %d removed posting(s).",
                 len(all_new_jobs), len(all_removed_jobs))
        for j in all_new_jobs:
            log.info("  [NEW]     [%s] %s — %s", j["company"], j["title"], j["url"])
        for r in all_removed_jobs:
            log.info("  [REMOVED] [%s] %s — %s", r["company"], r["title"], r.get("url", ""))
    else:
        log.info("No new or removed jobs found — no email sent.")


# ── Board verification ────────────────────────────────────────────────────────

def verify_boards(companies: list[dict]):
    """Quick HEAD/GET check that each board URL is reachable."""
    import requests

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


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape trading firm job boards and email new postings.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--companies", default="companies.yaml", help="Path to companies.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't send email")
    parser.add_argument("--catalog-only", action="store_true",
                        help="On first run, record all current jobs without emailing")
    parser.add_argument("--verify-boards", action="store_true", help="Check all board URLs are reachable")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = Path(__file__).parent
    config_path = Path(args.config) if Path(args.config).is_absolute() else root / args.config
    companies_path = Path(args.companies) if Path(args.companies).is_absolute() else root / args.companies

    config = load_config(config_path)
    companies = load_companies(companies_path)

    if args.verify_boards:
        verify_boards(companies)
        return

    run(config, companies, dry_run=args.dry_run, catalog_only=args.catalog_only)


if __name__ == "__main__":
    main()
