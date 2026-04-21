# job-scrapr

Scrapes job boards at 96 quant/trading firms and emails new postings daily.

## How it works

Each company in `companies.yaml` is assigned a scraper type:

- **greenhouse / lever / workday / ashby / eightfold** — hits the firm's public jobs API directly (fast, structured)
- **generic** — fetches the careers page with a plain HTTP request and extracts job links via BeautifulSoup heuristics
- **playwright** — launches a headless Chromium browser for JS-rendered pages that require JavaScript execution
- **email_only** — no scraping; just reminds you to check the site manually

On each run, newly found jobs are diffed against the last saved state and only fresh postings (and any removed ones) are emailed. State is stored in `data/seen_jobs.json`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

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

# Check which boards are reachable
python main.py --verify-boards

# Scrape without sending email (for testing)
python main.py --dry-run
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
  type: greenhouse       # or: generic
  board_token: acme      # greenhouse only
  # careers_url: "..."   # generic only
  # disabled: true       # to skip without deleting
```

## GitHub Actions (automated daily runs)

The workflow in `.github/workflows/scrape.yml` runs the scraper on a schedule and
emails new postings automatically. State is persisted in an orphan `data` branch so
`main` stays clean.

### One-time setup

**1. Bootstrap the data branch** (run once locally before pushing):
```bash
bash bootstrap_data_branch.sh
```

**2. Add three repository secrets:**
- Go to **Settings → Secrets and variables → Actions → New repository secret**
- `SMTP_PASSWORD` — your Gmail App Password (generate at myaccount.google.com/apppasswords)
- `EMAIL_SENDER` — the Gmail address sending the email (e.g. `you@gmail.com`)
- `EMAIL_RECIPIENTS` — comma-separated list of recipient addresses (e.g. `you@gmail.com`)

**3. Push `main` to GitHub** — the workflow will appear under the Actions tab.

**4. First run — catalog without emailing:**  
Trigger the workflow manually via **Actions → Daily Job Scrape → Run workflow**, and
check the **"Catalog jobs without sending email"** box. This snapshots all current
jobs so the next scheduled run only emails genuinely new postings.

### Schedule

Runs weekdays at **8:00 AM PT** (`0 15 * * 1-5` UTC). Adjust the cron expression in
`.github/workflows/scrape.yml` to change the time or add weekends.

### Manual trigger

You can run the workflow any time from **Actions → Daily Job Scrape → Run workflow**,
with optional `dry_run` or `catalog_only` flags.
