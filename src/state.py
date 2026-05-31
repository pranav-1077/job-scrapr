"""Persists and diffs job listings across scraper runs using a JSON file"""

import json
from pathlib import Path

from scrapers.base import Job

# define fields to store for job list
_STORED_FIELDS = ("id", "title", "url", "location", "department")


class JobState:
    def __init__(self, data_dir: str):
        """Loads existing state from disk and prepares the jobs store"""
        self._path = Path(data_dir) / "seen_jobs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, list[dict]] = self._load()
        self._dirty = False

    def _load(self) -> dict:
        """Reads the JSON state file and migrates any old string-ID format to dicts"""
        if not self._path.exists():
            return {}
        with open(self._path) as f:
            data = json.load(f)
        # older versions stored job IDs as plain strings rather than dicts
        # convert them so downstream code can always assume dict entries
        for company, entries in data.items():
            if entries and isinstance(entries[0], str):
                data[company] = [{"id": e, "title": "", "url": ""} for e in entries]
        return data

    def is_first_run(self, company: str) -> bool:
        """Returns True if no jobs have been recorded for this company yet"""
        return company not in self._state

    def count(self, company: str) -> int:
        """Returns the number of jobs stored from the previous run for this company"""
        return len(self._state.get(company, []))

    def get_new_jobs(self, company: str, jobs: list[Job]) -> list[Job]:
        """Returns jobs not seen in the previous state for this company"""
        seen_ids = {e["id"] for e in self._state.get(company, [])}
        return [j for j in jobs if j.id not in seen_ids]

    def get_removed_jobs(self, company: str, jobs: list[Job]) -> list[dict]:
        """Returns previously stored jobs that are absent from the current scrape"""
        current_ids = {j.id for j in jobs}
        # only include entries with a title so removed alerts are meaningful
        return [
            {**e, "company": company}
            for e in self._state.get(company, [])
            if e["id"] not in current_ids and e.get("title")
        ]

    def update(self, company: str, jobs: list[Job]):
        """Replaces the stored job list for a company with the latest scrape results"""
        self._state[company] = [
            {k: getattr(j, k) for k in _STORED_FIELDS}
            for j in jobs
        ]
        self._dirty = True

    def save(self):
        """Writes the in-memory state to disk if any updates were made"""
        if self._dirty:
            with open(self._path, "w") as f:
                json.dump(self._state, f, indent=2, sort_keys=True)
