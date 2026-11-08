# Opening Bell

A daily stock-market news briefing, updated automatically every morning.

Each day is a JSON file in `briefings/`; `publish.sh` rebuilds the index and pushes to GitHub Pages.

For information only. Not financial advice.

## How the daily update works

`.github/workflows/daily-briefing.yml` runs on GitHub's servers every morning (13:17 UTC: 7:17 AM Central in winter, 8:17 AM in summer). Your computer doesn't need to be on, and it costs nothing: there are no API keys or paid services. It:

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
