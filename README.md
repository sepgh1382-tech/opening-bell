# Opening Bell

A daily stock-market news briefing, updated automatically every morning by an AI news agent.

Each day is a JSON file in `briefings/`; `publish.sh` rebuilds the index and pushes to GitHub Pages.

For information only. Not financial advice.

## How the daily update works

`.github/workflows/daily-briefing.yml` runs on GitHub's servers every morning (13:17 UTC: 7:17 AM Central in winter, 8:17 AM in summer). Your computer doesn't need to be on. It:

1. runs `agent.py`, which uses the Claude API (with web search) to research the news and write `briefings/<date>.json`
2. runs `publish.sh`, which rebuilds the index, bakes the page and pushes to `main`

If a run fails, GitHub emails you and nothing is published.

### One-time setup

1. Create an API key at https://console.anthropic.com (API usage is billed there, separately from any Claude subscription; add credit and consider setting a monthly spend limit).
2. In this repo on GitHub: Settings → Secrets and variables → Actions → New repository secret. Name it `ANTHROPIC_API_KEY` and paste the key.
3. Actions tab → Daily briefing → Run workflow, to test it once.

### Running it on your computer

```bash
pip3 install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python3 agent.py --dry-run   # print the briefing without saving it
python3 agent.py && ./publish.sh
```

Optional settings (environment variables): `OPENING_BELL_MODEL` (default `claude-opus-5-5`), `OPENING_BELL_EFFORT` (`low`, `medium` or `high`; default `medium`), `OPENING_BELL_TZ` (default `America/Chicago`).
