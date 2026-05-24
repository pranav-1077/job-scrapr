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

### Local (macOS launchd)

launchd is macOS's scheduler. It runs the job at **8:00 AM daily** and fires on next wake if the Mac was asleep at that time — no missed runs.

**1. Create the plist file:**

```bash
mkdir -p ~/Library/LaunchAgents
```

Create `~/Library/LaunchAgents/com.job-scrapr.daily.plist` with the following content, replacing the paths with your own:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.job-scrapr.daily</string>

    <key>ProgramArguments</key>
    <array>
        <string>/path/to/job-scrapr/venv/bin/python</string>
        <string>/path/to/job-scrapr/src/main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/path/to/job-scrapr</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/path/to/job-scrapr/logs/job-scrapr.log</string>

    <key>StandardErrorPath</key>
    <string>/path/to/job-scrapr/logs/job-scrapr-error.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

**2. Load and manage:**

```bash
# Register the schedule (run once, and again after any edits to the plist)
launchctl load ~/Library/LaunchAgents/com.job-scrapr.daily.plist

# Trigger manually without waiting for 8 AM
launchctl start com.job-scrapr.daily

# Check status / last exit code
launchctl list | grep job-scrapr

# View logs
tail -f logs/job-scrapr.log
tail -f logs/job-scrapr-error.log

# Unload (stop scheduling)
launchctl unload ~/Library/LaunchAgents/com.job-scrapr.daily.plist
```

### GitHub Actions

The workflow in `.github/workflows/scrape.yml` runs on a schedule and commits updated state back to `main`.

> **Note:** Companies with `disabled_on_ci: true` in `companies.yaml` are automatically skipped when running on GitHub Actions (the `CI=true` environment variable is set automatically). Use this flag for any company whose career site blocks datacenter IPs.

**One-time setup:**

1. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `SMTP_PASSWORD` — Gmail App Password
   - `EMAIL_SENDER` — sending address (e.g. `you@gmail.com`)
   - `EMAIL_RECIPIENTS` — comma-separated recipients

2. Push `main` to GitHub — the workflow appears under the Actions tab.

3. **First run:** trigger manually via **Actions → Daily Job Scrape → Run workflow** with the **"Catalog jobs without sending email"** box checked. This snapshots all current jobs so the next run only emails genuinely new postings.

Runs weekdays at **8:00 AM PT** (`0 15 * * 1-5` UTC). Adjust the cron in `.github/workflows/scrape.yml` to change the schedule.
