import json
from pathlib import Path

from scrapers.base import Job


class JobState:
    def __init__(self, data_dir: str):
        self._path = Path(data_dir) / "seen_jobs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, list[str]] = self._load()
        self._dirty = False

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                return json.load(f)
        return {}

    def is_first_run(self, company: str) -> bool:
        return company not in self._state

    def get_new_jobs(self, company: str, jobs: list[Job]) -> list[Job]:
        seen = set(self._state.get(company, []))
        return [j for j in jobs if j.id not in seen]

    def update(self, company: str, jobs: list[Job]):
        self._state[company] = [j.id for j in jobs]
        self._dirty = True

    def save(self):
        if self._dirty:
            with open(self._path, "w") as f:
                json.dump(self._state, f, indent=2, sort_keys=True)
