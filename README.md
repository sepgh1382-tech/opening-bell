# Opening Bell

A daily stock-market news briefing, updated automatically every morning.

Each day is a JSON file in `briefings/`; `publish.sh` rebuilds the index and pushes to GitHub Pages.

For information only. Not financial advice.

## How the daily update works

`.github/workflows/daily-briefing.yml` runs on GitHub's servers several times a day (times are Central in winter; add an hour in summer):

- **Morning**, twice an hour from 7:17 to 9:47 AM, because GitHub often delays or skips scheduled runs. These stop once today's briefing exists.
- **Refreshes on weekdays** around 11:17 AM, 1:17 PM, 3:47 PM (after the close) and 7:17 PM. Each rebuilds today's briefing with the latest headlines and prices, and the page's dateline says when ("Market hours, updated 11:20 a.m. CT").

A briefing written by the Claude task in the app is never replaced by a refresh; only files the free agent made (marked `"source": "free-agent"`) are. Run workflow → "force" rebuilds anyway. Your computer doesn't need to be on, and it costs nothing: there are no API keys or paid services. It:

1. runs `agent.py`, which builds `briefings/<date>.json` from:
   - market prices from Yahoo Finance's public chart data
   - headlines from public RSS feeds (CNBC, MarketWatch, WSJ, Nasdaq, Investing.com, Seeking Alpha, the Federal Reserve)
   - keyword rules plus the VADER sentiment model to group duplicates, rank stories and rate them bullish, bearish or neutral
2. runs `publish.sh`, which rebuilds the index, bakes the page and pushes to `main`

The ratings and "why it matters" lines are rule based, not written by a person or an AI, so treat them as a rough guide. If a run fails (for example when the feeds are down), GitHub emails you and nothing is published.

To run it by hand: Actions tab → Daily briefing → Run workflow.

### Running it on your computer

```bash
pip3 install -r requirements.txt
python3 agent.py --dry-run   # print the briefing without saving it
python3 agent.py && ./publish.sh
```

Needs Python 3.9 or newer. To tune it, edit the lists at the top of `agent.py`: `FEEDS`, `SNAPSHOT`, `TOPICS`, `COMPANIES` and `FINANCE_LEXICON`.
