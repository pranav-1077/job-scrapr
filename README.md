# job-scrapr

Most job boards fail to reliably capture postings from niche hedge funds / trading firms. This tool scrapes job boards at 115 quant/trading firms and emails new postings daily.

## How it works

Each company in `companies.yaml` is assigned a scraper type:

| Type | How it works |
|---|---|
| `greenhouse` `lever` `workday` `ashby` `eightfold` `workable` `pinpoint` `gem` | Public jobs API |
| `jibe` | iCIMS/Jibe JSON API with category-facet pagination |
| `generic` | HTTP request + BeautifulSoup |
| `cffi` | HTTP client with a real browser TLS fingerprint, for sites that reject plain scripts |
| `wp_ajax` | WordPress admin-ajax.php job listing API |
| `playwright` | Headless Chromium for JS-rendered pages |
| `salesforce` | Headless browser for Salesforce Experience Cloud pages |
| `linkedin` | LinkedIn public guest API |
| `email_only` | No scraping — manual check reminder |

On each run, newly found jobs are diffed against the last saved state and only fresh postings (and any removed ones) are emailed. State is stored in `data/seen_jobs.json`.


## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
make setup
# add your Gmail App Password to .env
# generate one at https://myaccount.google.com/apppasswords
```

`make setup` runs `uv sync` (installs deps into `.venv`), installs the Playwright Chromium browser, and copies `.env.example` to `.env` if it doesn't exist yet.

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
    cffi_scraper.py       — curl_cffi client using a browser-compatible fingerprint
    wp_ajax.py            — WordPress admin-ajax.php API
    playwright_scraper.py — headless Chromium for JS-rendered pages
    salesforce.py         — Salesforce Experience Cloud via headless browser
    jibe.py               — iCIMS/Jibe JSON API with category-facet pagination
    linkedin.py           — LinkedIn guest API (no login)
    workable.py           — Workable public jobs API
    pinpoint.py           — Pinpoint HQ public jobs API
companies.yaml     — list of firms and their scraper config
config.yaml        — email settings, filters, timeouts
data/seen_jobs.json — persisted job state
logs/job-scrapr.log — overwritten on each run; logs both terminal and scheduled runs
```

## Usage

```bash
# First run: snapshot current jobs without sending email
make catalog-only

# Normal run: email any new postings since last run
make run

# Check which boards are reachable
make verify-boards

# Scrape without sending email (for testing)
make dry-run
```

Equivalent `uv run` commands work too, e.g. `uv run python src/main.py --dry-run`.

## Config

**`config.yaml`** — keyword filters, request settings, daily run `schedule`
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
  type: greenhouse          # or: lever, workday, ashby, eightfold, workable, pinpoint,
                            #     jibe, generic, cffi, wp_ajax, playwright, salesforce, linkedin, email_only
  board_token: acme         # greenhouse / ashby
  # company_id: acme        # lever
  # workday_base: "https://acme.wd5.myworkdayjobs.com"  # workday
  # workday_path: "Acme"                                # workday
  # careers_url: "..."      # generic / cffi / playwright / jibe / workable / pinpoint
  # playwright_wait_for: "a[href*='/job/']"  # playwright: CSS selector to wait for before scraping
  # disabled: true          # skip without deleting
```

## Scheduled runs (macOS launchd)

Set the run time in `config.yaml` (`schedule.hour` 0-23, `schedule.timezone` PST/EST/CST), then install:

```bash
make launchd
```

Re-run after changing the schedule or moving the repo. launchd only fires when the Mac is awake at that time.

Manage:

```bash
# Trigger manually without waiting for the scheduled time
launchctl start com.job-scrapr.daily

# Check status / last exit code
launchctl list | grep job-scrapr

# View logs
tail -f logs/job-scrapr.log

# Unload (stop scheduling)
launchctl unload ~/Library/LaunchAgents/com.job-scrapr.daily.plist
```