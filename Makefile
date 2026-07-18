.PHONY: setup install run catalog-only dry-run verify-boards launchd clean

setup: install
	uv run playwright install chromium
	@[ -f .env ] || cp .env.example .env

install:
	uv sync

run:
	uv run python src/main.py

catalog-only:
	uv run python src/main.py --catalog-only

dry-run:
	uv run python src/main.py --dry-run

verify-boards:
	uv run python src/main.py --verify-boards

launchd:
	uv run python scripts/setup_launchd.py

clean:
	rm -rf .venv __pycache__ src/__pycache__ src/scrapers/__pycache__
