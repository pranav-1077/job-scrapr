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

### Cloudflare-protected sites

Citadel and Citadel Securities use `type: cffi`, which bypasses Cloudflare's TLS fingerprinting when run from a residential IP. **GitHub Actions runners use Azure datacenter IPs that Cloudflare blocks with a 403 regardless of TLS fingerprint.** Both companies have `disabled_on_ci: true` in `companies.yaml` — they are skipped on CI and should be scraped via a local scheduled run instead.

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
data/seen_jobs.json — persisted job state (committed by CI after each run)
logs/              — stdout/stderr from local launchd runs
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
  # disabled_on_ci: true # skip on GitHub Actions only (e.g. Cloudflare-protected)
```

## Scheduled runs

### Local (macOS launchd) — recommended for full coverage

A launchd plist is included at `~/Library/LaunchAgents/com.pranav.job-scrapr.plist`. It runs at **8:00 AM daily** and fires on next wake if the Mac was asleep at that time.

```bash
# Load (run once after cloning or editing the plist)
launchctl load ~/Library/LaunchAgents/com.pranav.job-scrapr.plist

# Trigger manually without waiting for 8 AM
launchctl start com.pranav.job-scrapr

# Check status / last exit code
launchctl list | grep job-scrapr

# View logs
tail -f logs/job-scrapr.log
tail -f logs/job-scrapr-error.log

# Unload (to stop scheduling)
launchctl unload ~/Library/LaunchAgents/com.pranav.job-scrapr.plist
```

### GitHub Actions — partial coverage

The workflow in `.github/workflows/scrape.yml` runs on a schedule and commits updated state back to `main`. Companies with `disabled_on_ci: true` (currently Citadel and Citadel Securities) are skipped.

**One-time setup:**

1. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `SMTP_PASSWORD` — Gmail App Password
   - `EMAIL_SENDER` — sending address (e.g. `you@gmail.com`)
   - `EMAIL_RECIPIENTS` — comma-separated recipients

2. Push `main` to GitHub — the workflow appears under the Actions tab.

3. **First run:** trigger manually via **Actions → Daily Job Scrape → Run workflow** with the **"Catalog jobs without sending email"** box checked. This snapshots all current jobs so the next run only emails genuinely new postings.

Runs weekdays at **8:00 AM PT** (`0 15 * * 1-5` UTC). Adjust the cron in `.github/workflows/scrape.yml` to change the schedule.
