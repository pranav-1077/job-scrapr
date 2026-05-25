# job-scrapr

Scrapes job boards at 100 quant/trading firms and emails new postings daily.

## How it works

Each company in `companies.yaml` is assigned a scraper type:

- **greenhouse / lever / workday / ashby / eightfold** — hits the firm's public jobs API directly (fast, structured)
- **generic** — fetches the careers page with a plain HTTP request and extracts job links via BeautifulSoup heuristics
- **cffi** — uses `curl_cffi` to impersonate a real Chrome TLS fingerprint, bypassing Cloudflare bot detection without a browser
- **playwright** — launches a headless Chromium browser for JS-rendered pages that require JavaScript execution
- **salesforce** — Playwright-based scraper for Salesforce Experience Cloud career sites (pierces shadow DOM via locator API)
- **linkedin** — scrapes a company's jobs tab via LinkedIn's public guest API (no login required)
- **email_only** — no scraping; just reminds you to check the site manually

On each run, newly found jobs are diffed against the last saved state and only fresh postings (and any removed ones) are emailed. State is stored in `data/seen_jobs.json`.


## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# add your Gmail App Password to .env
# generate one at https://myaccount.google.com/apppasswords
```

## Project structure

```
src/
  main.py          — entry point: config loading, parallel scraping, email dispatch
  notifier.py      — builds and sends the HTML/plain-text digest email
  state.py         — tracks seen jobs in data/seen_jobs.json
  scrapers/
    base.py               — Job dataclass and BaseScraper interface
    greenhouse.py         — Greenhouse JSON API
    lever.py              — Lever JSON API
    ashby.py              — Ashby JSON API
    eightfold.py          — Eightfold AI paginated API
    generic.py            — generic HTML scraper (BeautifulSoup)
    cffi_scraper.py       — curl_cffi Chrome impersonation (Cloudflare bypass)
    playwright_scraper.py — headless Chromium for JS-rendered pages
    salesforce.py         — Salesforce Experience Cloud (Playwright + shadow DOM)
    linkedin.py           — LinkedIn guest API (no login)
companies.yaml     — list of firms and their scraper config
config.yaml        — email settings, filters, timeouts
data/seen_jobs.json — persisted job state
logs/job-scrapr.log — overwritten on each run; logs both terminal and scheduled runs
```

## Usage

```bash
# First run: snapshot current jobs without sending email
python src/main.py --catalog-only

# Normal run: email any new postings since last run
python src/main.py

# Check which boards are reachable
python src/main.py --verify-boards

# Scrape without sending email (for testing)
python src/main.py --dry-run
```

## Config

**`config.yaml`** — keyword filters, request settings  
**`companies.yaml`** — add/remove/disable companies  
**`.env`** — secrets for local runs:
```
SMTP_PASSWORD=your_gmail_app_password
EMAIL_SENDER=you@gmail.com
EMAIL_RECIPIENTS=you@gmail.com
```

To add a company:
```yaml
- name: "Acme Capital"
  type: greenhouse       # or: generic, cffi, lever, ashby, ...
  board_token: acme      # greenhouse only
  # careers_url: "..."   # generic/cffi only
  # disabled: true       # skip without deleting
```

## Scheduled runs (macOS launchd)

launchd runs the job at **8:00 AM daily** and fires on next wake if the Mac was asleep at that time — no missed runs.

**1. Install the schedule:**

```bash
venv/bin/python scripts/setup_launchd.py
```

This fills in your local paths in the plist template (`launchd/com.job-scrapr.daily.plist`) and installs it into `~/Library/LaunchAgents/`. Re-run if you ever move the repo.

**2. Manage:**

```bash
# Trigger manually without waiting for 8 AM
launchctl start com.job-scrapr.daily

# Check status / last exit code
launchctl list | grep job-scrapr

# View logs
tail -f logs/job-scrapr.log

# Unload (stop scheduling)
launchctl unload ~/Library/LaunchAgents/com.job-scrapr.daily.plist
```
