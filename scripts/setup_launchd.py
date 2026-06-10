"""Installs the launchd schedule for job-scrapr on macOS"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PLIST_NAME = "com.job-scrapr.daily.plist"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

# friendly timezone names accepted in config mapped to IANA zones
# IANA zones handle daylight saving automatically so PST also covers PDT
TZ_ALIASES = {
    "PST": "America/Los_Angeles",
    "EST": "America/New_York",
    "CST": "America/Chicago",
}

repo_dir = Path(__file__).parent.parent.resolve()
python = repo_dir / "venv" / "bin" / "python"
template = repo_dir / "launchd" / PLIST_NAME
config_file = repo_dir / "config.yaml"
dest = LAUNCH_AGENTS / PLIST_NAME


def _load_schedule() -> tuple[int, str]:
    """Reads the hour and timezone from the schedule block in config"""
    with open(config_file) as f:
        config = yaml.safe_load(f) or {}
    sched = config.get("schedule", {})
    hour = int(sched.get("hour", 8))
    tz_name = str(sched.get("timezone", "EST")).upper()

    if not 0 <= hour <= 23:
        print(f"schedule.hour must be between 0 and 23 but got {hour}")
        sys.exit(1)
    if tz_name not in TZ_ALIASES:
        allowed = " ".join(TZ_ALIASES)
        print(f"schedule.timezone must be one of {allowed} but got {tz_name}")
        sys.exit(1)
    return hour, tz_name


def _local_run_time(hour: int, tz_name: str) -> datetime:
    """Returns the configured hour in its timezone expressed in machine local time"""
    target = datetime.now(ZoneInfo(TZ_ALIASES[tz_name])).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return target.astimezone()


def main():
    """Fills in the plist template and installs it into LaunchAgents"""
    if sys.platform != "darwin":
        print("launchd is macOS only")
        sys.exit(1)

    if not python.exists():
        print(f"venv not found at {python}")
        print("Run python3 -m venv venv && venv/bin/pip install -r requirements.txt")
        sys.exit(1)

    hour, tz_name = _load_schedule()
    run_at = _local_run_time(hour, tz_name)

    # substitute repo paths and the computed local run time into the template
    content = template.read_text()
    content = content.replace("{{REPO_DIR}}", str(repo_dir))
    content = content.replace("{{PYTHON}}", str(python))
    content = content.replace("{{HOUR}}", str(run_at.hour))
    content = content.replace("{{MINUTE}}", str(run_at.minute))

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)

    # unload any previously installed version before overwriting
    if dest.exists():
        subprocess.run(["launchctl", "unload", str(dest)], capture_output=True)

    dest.write_text(content)
    subprocess.run(["launchctl", "load", str(dest)], check=True)

    print(f"Installed {dest}")
    print(f"Configured for {hour:02d}:00 {tz_name} which is "
          f"{run_at.strftime('%H:%M %Z')} on this machine")
    print("Note launchd only fires when the Mac is awake at the scheduled time")
    print()
    print("To trigger manually  launchctl start com.job-scrapr.daily")
    print("To unschedule        launchctl unload ~/Library/LaunchAgents/com.job-scrapr.daily.plist")


if __name__ == "__main__":
    main()
