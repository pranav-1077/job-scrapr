#!/usr/bin/env python3
"""job-scrapr — daily job board monitor for quant / trading firms."""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

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
    return load_yaml(config_path)


def load_companies(companies_path: Path) -> list[dict]:
    data = load_yaml(companies_path)
    return data["companies"]


# ── Main scrape loop ──────────────────────────────────────────────────────────

def run(config: dict, companies: list[dict], *, dry_run: bool = False, catalog_only: bool = False):
    state = JobState(config.get("data_dir", "./data"))
    notifier = EmailNotifier(config["email"])
    keyword_filters: list[str] = config.get("keyword_filters", [])
    delay = config.get("delay_between_companies", 1)

    all_new_jobs: list[dict] = []
    errors: list[str] = []
    email_only_companies: list[dict] = [
        c for c in companies
        if not c.get("disabled") and c.get("type") == "email_only"
    ]

    for company in companies:
        if company.get("disabled"):
            log.debug("Skipping disabled company: %s", company["name"])
            continue

        if company.get("type") == "email_only":
            log.debug("Skipping email-only company: %s (%s)", company["name"], company.get("resume_email", ""))
            continue

        name = company["name"]
        log.info("Scraping %s …", name)

        try:
            scraper = get_scraper(company)
            jobs = scraper.fetch_jobs()
            log.debug("  fetched %d job(s) total", len(jobs))

            if catalog_only and state.is_first_run(name):
                log.info("  catalogued %d job(s) (first run, no email)", len(jobs))
                state.update(name, jobs)
                time.sleep(delay)
                continue

            new_jobs = state.get_new_jobs(name, jobs)

            # Apply keyword filter
            if keyword_filters:
                new_jobs = [j for j in new_jobs if j.matches_filters(keyword_filters)]

            if new_jobs:
                log.info("  %d new job(s)", len(new_jobs))
                for j in new_jobs:
                    j.company = name
                    all_new_jobs.append(vars(j))
            else:
                log.info("  no new jobs")

            state.update(name, jobs)

        except Exception as exc:
            log.warning("  ERROR scraping %s: %s", name, exc)
            errors.append(f"{name}: {exc}")

        time.sleep(delay)

    state.save()

    if errors:
        log.warning("Completed with %d error(s):\n  %s", len(errors), "\n  ".join(errors))

    if all_new_jobs and not dry_run:
        log.info("Sending email with %d new posting(s) …", len(all_new_jobs))
        try:
            notifier.send(all_new_jobs, email_only_companies)
            log.info("Email sent.")
        except Exception as exc:
            log.error("Failed to send email: %s", exc)
    elif all_new_jobs:
        log.info("[dry-run] Would send email with %d posting(s).", len(all_new_jobs))
        for j in all_new_jobs:
            log.info("  [%s] %s — %s", j["company"], j["title"], j["url"])
    else:
        log.info("No new jobs found — no email sent.")


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


# ── Cron setup ────────────────────────────────────────────────────────────────

_CRON_SCHEDULES = {
    "hourly": "0 * * * *",
    "daily": "0 {hour} * * *",
    "weekly": "0 {hour} * * 1",
}


def setup_cron(config: dict, config_path: Path):
    frequency = config.get("frequency", "daily")
    hour = config.get("run_hour", 8)
    schedule = _CRON_SCHEDULES.get(frequency, "0 8 * * *").format(hour=hour)

    script = Path(__file__).resolve()
    python = sys.executable
    log_dir = script.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    cmd = (
        f"{schedule}  cd {script.parent} && "
        f"{python} {script} --config {config_path.resolve()} "
        f">> {log_dir}/scraper.log 2>&1"
    )

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    if str(script) in existing:
        print("Cron job already installed. Current crontab entry:")
        for line in existing.splitlines():
            if str(script) in line:
                print(" ", line)
        return

    new_crontab = existing.rstrip("\n") + "\n" + cmd + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode == 0:
        print(f"Cron job installed ({frequency} at {hour}:00):\n  {cmd}")
    else:
        print(f"Failed to install cron job: {proc.stderr}")
        print(f"Add this line manually to your crontab (`crontab -e`):\n  {cmd}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape trading firm job boards and email new postings.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--companies", default="companies.yaml", help="Path to companies.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't send email")
    parser.add_argument("--catalog-only", action="store_true",
                        help="On first run, record all current jobs without emailing")
    parser.add_argument("--setup-cron", action="store_true", help="Install cron job and exit")
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

    if args.setup_cron:
        setup_cron(config, config_path)
        return

    if args.verify_boards:
        verify_boards(companies)
        return

    run(config, companies, dry_run=args.dry_run, catalog_only=args.catalog_only)


if __name__ == "__main__":
    main()
