#!/bin/bash
# Rebuilds briefings/index.json from the files in briefings/, then commits and pushes to GitHub.
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
import json, os, re
dates = sorted((f[:-5] for f in os.listdir("briefings") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f)), reverse=True)
for d in dates:
    json.load(open(f"briefings/{d}.json"))  # fail loudly on invalid JSON
json.dump({"dates": dates}, open("briefings/index.json", "w"), indent=2)
print("Briefings:", len(dates), "latest:", dates[0] if dates else None)
PY
git add -A
git diff --cached --quiet && { echo "Nothing new to publish."; exit 0; }
git commit -q -m "Briefing for $(date +%Y-%m-%d)"
git push -q origin main
echo "Published."
