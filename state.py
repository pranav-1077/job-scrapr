import json
from pathlib import Path

from scrapers.base import Job

_STORED_FIELDS = ("id", "title", "url", "location", "department")


class JobState:
    def __init__(self, data_dir: str):
        self._path = Path(data_dir) / "seen_jobs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, list[dict]] = self._load()
        self._dirty = False

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        with open(self._path) as f:
            data = json.load(f)
        # Migrate old format (list of ID strings → list of dicts)
        for company, entries in data.items():
            if entries and isinstance(entries[0], str):
                data[company] = [{"id": e, "title": "", "url": ""} for e in entries]
        return data

    def is_first_run(self, company: str) -> bool:
        return company not in self._state

    def get_new_jobs(self, company: str, jobs: list[Job]) -> list[Job]:
        seen_ids = {e["id"] for e in self._state.get(company, [])}
        return [j for j in jobs if j.id not in seen_ids]

    def get_removed_jobs(self, company: str, jobs: list[Job]) -> list[dict]:
        """Return stored jobs that are no longer in the current scrape results."""
        current_ids = {j.id for j in jobs}
        return [
            {**e, "company": company}
            for e in self._state.get(company, [])
            if e["id"] not in current_ids and e.get("title")
        ]

    def update(self, company: str, jobs: list[Job]):
        self._state[company] = [
            {k: getattr(j, k) for k in _STORED_FIELDS}
            for j in jobs
        ]
        self._dirty = True

    def save(self):
        if self._dirty:
            with open(self._path, "w") as f:
                json.dump(self._state, f, indent=2, sort_keys=True)
