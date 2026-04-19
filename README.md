# job-scrapr

Scrapes job boards at 94 quant/trading firms and emails new postings daily.

## How it works

Each company in `companies.yaml` is assigned a scraper type:

- **greenhouse / lever / workday / ashby / eightfold** — hits the firm's public jobs API directly (fast, structured)
- **generic** — fetches the careers page with a plain HTTP request and extracts job links via BeautifulSoup heuristics
- **playwright** — launches a headless Chromium browser for JS-rendered pages that require JavaScript execution
- **email_only** — no scraping; just reminds you to check the site manually

On each run, newly found jobs are diffed against the last saved state and only fresh postings (and any removed ones) are emailed. Results are stored in `data/` as JSON.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# add your Gmail App Password to .env
# generate one at https://myaccount.google.com/apppasswords
```

## Usage

```bash
# First run: snapshot current jobs without sending email
python main.py --catalog-only

# Normal run: email any new postings since last run
python main.py

# Install launchd job (runs on wake if Mac was asleep at schedule time)
python main.py --setup-cron

# Check which boards are reachable
python main.py --verify-boards

# Scrape without sending email (for testing)
python main.py --dry-run
```

## Config

**`config.yaml`** — set your email, frequency, and keyword filters  
**`companies.yaml`** — add/remove/disable companies  
**`.env`** — `SMTP_PASSWORD=your_gmail_app_password`

To add a company:
```yaml
- name: "Acme Capital"
  type: greenhouse       # or: generic
  board_token: acme      # greenhouse only
  # careers_url: "..."   # generic only
  # disabled: true       # to skip without deleting
```
