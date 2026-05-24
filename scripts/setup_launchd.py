#!/usr/bin/env python3
"""Install the launchd schedule for job-scrapr on macOS."""

import subprocess
import sys
from pathlib import Path

PLIST_NAME = "com.job-scrapr.daily.plist"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

repo_dir = Path(__file__).parent.parent.resolve()
python = repo_dir / "venv" / "bin" / "python"
template = repo_dir / "launchd" / PLIST_NAME
dest = LAUNCH_AGENTS / PLIST_NAME


def main():
    if sys.platform != "darwin":
        print("launchd is macOS-only.")
        sys.exit(1)

    if not python.exists():
        print(f"venv not found at {python}")
        print("Run: python3 -m venv venv && venv/bin/pip install -r requirements.txt")
        sys.exit(1)

    content = template.read_text()
    content = content.replace("{{REPO_DIR}}", str(repo_dir))
    content = content.replace("{{PYTHON}}", str(python))

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)

    # unload existing job if present
    if dest.exists():
        subprocess.run(["launchctl", "unload", str(dest)], capture_output=True)

    dest.write_text(content)
    subprocess.run(["launchctl", "load", str(dest)], check=True)

    print(f"Installed: {dest}")
    print("Runs daily at 8:00 AM (fires on next wake if Mac is asleep).")
    print()
    print("To trigger manually:  launchctl start com.job-scrapr.daily")
    print("To unschedule:        launchctl unload ~/Library/LaunchAgents/com.job-scrapr.daily.plist")


if __name__ == "__main__":
    main()
