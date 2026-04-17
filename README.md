# job-scrapr

Scrapes job boards at ~100 quant/trading firms and emails new postings daily.

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

# Schedule daily via cron
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
