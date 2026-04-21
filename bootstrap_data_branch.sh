#!/usr/bin/env bash
# Creates the orphan `data` branch that stores seen_jobs.json between workflow runs.
# Run this once before pushing to GitHub, then never again.
set -euo pipefail

BRANCH="data"

if git ls-remote --exit-code --heads origin "$BRANCH" &>/dev/null; then
  echo "Branch '$BRANCH' already exists on origin — nothing to do."
  exit 0
fi

echo "Creating orphan branch '$BRANCH'..."
git checkout --orphan "$BRANCH"
git rm -rf . --quiet
mkdir -p data
echo '{}' > data/seen_jobs.json
git add data/seen_jobs.json
git commit -m "chore: initialise data branch"
git push -u origin "$BRANCH"

# Return to main
git checkout main
echo "Done. Branch '$BRANCH' pushed to origin."
