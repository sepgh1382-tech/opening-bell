"""Opening Bell news agent (no AI): builds briefings/<date>.json from free news feeds and market data.

  python agent.py               write today's briefing to briefings/<date>.json
  python agent.py --dry-run     print the briefing instead of writing it
  python agent.py --check FILE  only validate an existing briefing file

How it works:
  * prices come from Yahoo Finance's public chart data
  * headlines come from public RSS feeds (CNBC, MarketWatch, WSJ, Nasdaq, Investing.com, Seeking Alpha, the Fed)
  * duplicate headlines are grouped, scored for market relevance with keyword rules,
    and rated bullish or bearish with the VADER sentiment model plus a finance word list

The ratings are keyword based, so they are rough. Publishing (index rebuild, bake, git push) is done by publish.sh.
"""
import argparse, calendar, datetime, html, json, os, re, sys, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).resolve().parent
TIMEZONE = ZoneInfo(os.environ.get("OPENING_BELL_TZ", "America/Chicago"))
USER_AGENT = "Mozilla/5.0 (compatible; OpeningBell/1.0)"
MAX_STORIES = 10

FEEDS = [  # (outlet name, url); earlier feeds win when the same story appears twice
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),     # top news
    ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),      # economy
    ("CNBC", "https://www.cnbc.com/id/15839135/device/rss/rss.html"),      # earnings
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),      # finance
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("WSJ", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("Nasdaq", "https://www.nasdaq.com/feed/rssoutbound?category=Markets"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss"),
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
]

SNAPSHOT = [  # (label, Yahoo symbol, kind)
    ("S&P 500", "^GSPC", "index"), ("Nasdaq", "^IXIC", "index"), ("Dow", "^DJI", "index"),
    ("Russell 2000", "^RUT", "index"), ("VIX", "^VIX", "level"), ("10Y yield", "^TNX", "yield"),
    ("Oil (WTI)", "CL=F", "price"), ("Bitcoin", "BTC-USD", "price"),
]

# Topic rules: (name, regex, relevance weight, affected, why it matters)
TOPICS = [
    ("rates", r"\b(fed|fomc|powell|federal reserve|rate (hike|cut|increase|decrease)s?|interest rates?|central bank|ecb|bank of (japan|england))\b", 3,
     ["S&P 500", "Treasuries", "Financials"],
     "Interest rate expectations feed straight into stock valuations and borrowing costs, so central bank news tends to move the whole market."),
    ("inflation", r"\b(cpi|ppi|pce|inflation|consumer prices)\b", 3, ["S&P 500", "Treasuries"],
     "Inflation readings shape what the Fed does next: hotter numbers pressure stocks and bonds, cooler ones support them."),
    ("jobs", r"\b(jobs report|payrolls?|unemployment|jobless claims|labor market|hiring)\b", 3, ["S&P 500", "Treasuries"],
     "The job market drives consumer spending and Fed policy, so labor data can shift rate expectations and stock prices."),
    ("economy", r"\b(gdp|recession|retail sales|consumer (spending|confidence|sentiment)|manufacturing|pmi|housing starts|home sales)\b", 2, ["S&P 500"],
     "Economic data shows whether growth is speeding up or slowing down, which sets the outlook for corporate profits."),
    ("bonds", r"\b(treasury|treasuries|bond yields?|10-year|yields? (rise|fall|jump|climb|drop))\b", 2, ["Treasuries", "Rate sensitive stocks"],
     "Rising yields make stocks look less attractive next to bonds and raise borrowing costs; falling yields do the opposite."),
    ("trade", r"\b(tariffs?|trade (war|deal|talks)|export controls?|sanctions?)\b", 2, ["S&P 500", "Industrials"],
     "Trade policy changes costs and access to markets for exporters and importers, which can hit earnings across sectors."),
    ("earnings", r"\b(earnings|quarterly|revenue|guidance|profit|eps|results|beats?|miss(es)?|outlook|forecast)\b", 2, [],
     "Earnings and guidance show how companies are really doing, which moves their shares and can set the tone for their sector."),
    ("ai", r"\b(ai|artificial intelligence|chips?|chipmakers?|semiconductors?|data centers?)\b", 2, ["Nasdaq", "Semiconductors"],
     "AI and chip stocks are a large part of the major indexes, so big moves in the group sway the whole market."),
    ("deals", r"\b(acquires?|acquisition|merger|takeover|buyout|to buy|deal (to|for))\b", 1, [],
     "Deals often lift the target's shares and can signal confidence about valuations in the sector."),
    ("energy", r"\b(oil|crude|opec|natural gas|gasoline|brent)\b", 1, ["Energy", "Oil"],
     "Energy prices affect energy company profits, inflation and costs for consumers and businesses."),
    ("crypto", r"\b(bitcoin|crypto|ether(eum)?|stablecoins?)\b", 1, ["Bitcoin", "Crypto stocks"],
     "Crypto swings are a gauge of risk appetite and move crypto linked stocks."),
    ("politics", r"\b(war|missile|ukraine|russia|china|israel|iran|election|midterms?|shutdown|congress|white house|trump)\b", 1, ["S&P 500"],
     "Political and geopolitical events can change policy, trade and risk appetite, which investors price in quickly."),
    ("markets", r"\b(stocks?|s&p|dow|nasdaq|wall street|futures|market|selloff|sell-off|rally|shares)\b", 1, ["S&P 500"],
     "Broad market moves show how investors are pricing the latest news and set the tone for the next session."),
]

COMPANIES = {  # name pattern -> ticker
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN", "alphabet|google": "GOOGL",
    "meta|facebook": "META", "tesla": "TSLA", "amd|advanced micro": "AMD", "micron": "MU", "broadcom": "AVGO",
    "intel": "INTC", "netflix": "NFLX", "oracle": "ORCL", "salesforce": "CRM", "palantir": "PLTR", "qualcomm": "QCOM",
    "jpmorgan": "JPM", "goldman": "GS", "morgan stanley": "MS", "bank of america": "BAC", "wells fargo": "WFC",
    "berkshire": "BRK.B", "walmart": "WMT", "costco": "COST", "target": "TGT", "home depot": "HD", "disney": "DIS",
    "boeing": "BA", "exxon": "XOM", "chevron": "CVX", "pfizer": "PFE", "eli lilly|lilly": "LLY", "novo nordisk": "NVO",
    "unitedhealth": "UNH", "coca-cola": "KO", "pepsico": "PEP", "mcdonald": "MCD", "starbucks": "SBUX", "nike": "NKE",
    "uber": "UBER", "coinbase": "COIN", "openai": "Private: OpenAI", "tsmc|taiwan semiconductor": "TSM",
}

FINANCE_LEXICON = {  # extra words for VADER, scale roughly -4..4
    "surge": 2.5, "surges": 2.5, "soar": 2.8, "soars": 2.8, "rally": 2.0, "rallies": 2.0, "jump": 1.6, "jumps": 1.6,
    "gain": 1.3, "gains": 1.3, "rise": 1.0, "rises": 1.0, "climb": 1.2, "climbs": 1.2, "beat": 1.6, "beats": 1.6,
    "record": 1.2, "upgrade": 1.6, "upgraded": 1.6, "bullish": 2.2, "upbeat": 1.6, "rebound": 1.6, "rebounds": 1.6,
    "strong": 1.2, "stronger": 1.2, "boost": 1.5, "boosts": 1.5, "tops": 1.2, "outperform": 1.5, "cooler": 1.0,
    "plunge": -2.8, "plunges": -2.8, "tumble": -2.5, "tumbles": -2.5, "slump": -2.2, "slumps": -2.2, "sink": -2.0,
    "sinks": -2.0, "slide": -1.6, "slides": -1.6, "drop": -1.4, "drops": -1.4, "fall": -1.3, "falls": -1.3,
    "miss": -1.6, "misses": -1.6, "downgrade": -1.6, "downgraded": -1.6, "selloff": -2.5, "sell-off": -2.5,
    "rout": -2.6, "layoffs": -1.6, "recession": -2.0, "tariff": -1.0, "tariffs": -1.0, "hike": -1.0, "bearish": -2.2,
    "bankruptcy": -3.0, "default": -2.0, "warns": -1.6, "crash": -3.0, "weak": -1.5, "weaker": -1.5, "slowdown": -1.6,
    "hotter": -1.2, "hikes": -1.2, "looms": -1.0, "cuts": -0.6, "fears": -1.6, "worst": -2.0, "lowers": -1.2, "probe": -1.2, "lawsuit": -1.2,
}

STOPWORDS = set("""a an the and or but of to in on for with at by from as is are was were be been it its this that these those
after before over under into out up down new says say said will would could may might than then their there here what why how
who about more most just now not no yes you your we our they them he she his her has have had do does did amid vs""".split())


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- market data ----------

def fmt_num(x, decimals=2):
    return f"{x:,.{decimals}f}"


def signed_pct(p):
    return ("+" if p >= 0 else "-") + f"{abs(p):.1f}%"


def snapshot(weekly):
    out, spx_change = [], None
    for label, symbol, kind in SNAPSHOT:
        try:
            data = json.loads(fetch("https://query1.finance.yahoo.com/v8/finance/chart/"
                                    + urllib.parse.quote(symbol) + "?range=1mo&interval=1d"))
            res = data["chart"]["result"][0]
            pts = [(t, c) for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
            if len(pts) < 6:
                continue
            last_t, last = pts[-1]
            back = (8 if symbol == "BTC-USD" else 6) if weekly else 2  # bitcoin trades every day
            if len(pts) < back:
                continue
            prev = pts[-back][1]
        except Exception as err:  # one bad symbol shouldn't sink the briefing
            print(f"price fetch failed for {symbol}: {err}", file=sys.stderr)
            continue
        when = "wk" if weekly else datetime.datetime.fromtimestamp(last_t, TIMEZONE).strftime("%a")
        if kind == "yield":
            bp = round((last - prev) * 100)
            value, change = f"{last:.2f}%", f"{'+' if bp >= 0 else '-'}{abs(bp)} bp {when}"
        else:
            pct = (last - prev) / prev * 100
            decimals = 0 if symbol == "BTC-USD" else 2
            value = ("$" if kind == "price" else "") + fmt_num(last, decimals)
            change = f"{signed_pct(pct)} {when}"
            if symbol == "^GSPC":
                spx_change = pct
        out.append({"asset": label, "value": value, "change": change})
    return out, spx_change


# ---------- news ----------

def clean_html(s):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    s = re.sub(r"^\s*(Key Points|Summary)\s*:?\s*", "", s)  # labels some feeds put in front
    return re.sub(r"\s+", " ", s).strip()


def first_sentences(text, n=2, limit=320):
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(parts[:n]).strip()
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return out


def tokens(title):
    words = re.findall(r"[a-z0-9&$%.']+", title.lower())
    return {w.strip(".'") for w in words if w.strip(".'") not in STOPWORDS and len(w.strip(".'")) > 2}


def gather_news(since):
    items = []
    for outlet, url in FEEDS:
        try:
            feed = feedparser.parse(fetch(url))
        except Exception as err:
            print(f"feed failed: {url}: {err}", file=sys.stderr)
            continue
        for e in feed.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            title = clean_html(e.get("title"))
            link = e.get("link") or ""
            if not t or not title or not link.startswith("http"):
                continue
            published = datetime.datetime.fromtimestamp(calendar.timegm(t), datetime.timezone.utc)
            if published < since:
                continue
            items.append({"outlet": outlet, "title": title, "url": link, "published": published,
                          "summary": clean_html(e.get("summary") or e.get("description")), "tokens": tokens(title)})
    return items


def cluster(items):
    groups = []
    for it in items:
        for g in groups:
            if it["url"] == g[0]["url"]:
                break
            a, b = it["tokens"], g[0]["tokens"]
            if a and b and len(a & b) / len(a | b) >= 0.34:
                g.append(it)
                break
        else:
            groups.append([it])
    return groups


def topics_for(text):
    low = text.lower()
    return [t for t in TOPICS if re.search(t[1], low)]


def companies_for(text):
    low = text.lower()
    return [tk for pat, tk in COMPANIES.items() if re.search(r"\b(" + pat + r")\b", low)]


BEARISH_MACRO = r"\b(rate hikes?|hikes? (interest )?rates?|hikes interest rate|raises? (interest )?rates|higher for longer|inflation (hits|rises|jumps|climbs|accelerates|heats|surges)|hot(ter)? inflation)\b"
BULLISH_MACRO = r"\b(rate cuts?|cuts? (interest )?rates?|inflation (cools|eases|slows|falls|drops)|cool(er)? inflation)\b"
LOW_VALUE = r"\b(cramer|podcast|video|watch|here's|how to|quiz|opinion)\b"


def rate_effect(analyzer, text):
    """Bullish, bearish or neutral for stocks. Macro rules first, then word sentiment."""
    low = text.lower()
    bear, bull = re.search(BEARISH_MACRO, low), re.search(BULLISH_MACRO, low)
    if bear and not bull:
        return "bearish"
    if bull and not bear and not re.search(r"\b(fewer|no|delay|doubts?|odds fall)\b", low):
        return "bullish"
    score = analyzer.polarity_scores(text)["compound"]
    return "bullish" if score >= 0.2 else "bearish" if score <= -0.2 else "neutral"


def build_stories(groups, analyzer):
    stories = []
    for g in groups:
        lead = g[0]
        text = f"{lead['title']}. {lead['summary']}"
        tops = topics_for(text)
        tickers = companies_for(lead["title"])
        relevance = sum(t[2] for t in tops) + 2 * len(set(x["outlet"] for x in g)) + (1 if tickers else 0)
        if re.search(LOW_VALUE, lead["title"].lower()):
            continue  # skip shows, videos and explainers
        if not tops or relevance < 4:
            continue
        main = max(tops, key=lambda t: t[2])
        affected = list(dict.fromkeys(tickers + [a for t in tops for a in t[3]]))[:6] or ["S&P 500"]
        why = main[4]
        if main[0] == "earnings" and tickers:
            why = f"Results and outlook from {tickers[0]} move its shares and can set the tone for its sector."
        impact = "high" if relevance >= 9 else "medium" if relevance >= 6 else "low"
        sources = []
        for x in g:
            if x["url"] not in [s["url"] for s in sources]:
                sources.append({"title": x["outlet"], "url": x["url"]})
        stories.append({
            "headline": lead["title"],
            "what": first_sentences(lead["summary"]) if len(lead["summary"]) > 40 else lead["title"] + ".",
            "effect": rate_effect(analyzer, lead["title"] + ". " + first_sentences(lead["summary"], 1)),
            "impact": impact,
            "affected": affected,
            "why": why,
            "sources": sources[:3],
            "_score": relevance,
            "_topic": main[0],
            "_published": lead["published"],
        })
    stories.sort(key=lambda s: (s["_score"], s["_published"]), reverse=True)
    return stories[:MAX_STORIES]


# ---------- assembly ----------

TOPIC_NAMES = {"rates": "interest rates", "inflation": "inflation", "jobs": "the job market", "economy": "the economy",
               "bonds": "bond yields", "trade": "trade policy", "earnings": "earnings", "ai": "AI and chip stocks",
               "deals": "deals", "energy": "energy", "crypto": "crypto", "politics": "politics", "markets": "the broad market"}


def join_words(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def build_briefing(day, now):
    weekend = day.weekday() >= 5
    lookback = {5: 7, 6: 7, 0: 3}.get(day.weekday(), 1)
    since = now - datetime.timedelta(days=lookback, hours=2)

    snap, spx = snapshot(weekend)
    analyzer = SentimentIntensityAnalyzer()
    analyzer.lexicon.update(FINANCE_LEXICON)
    stories = build_stories(cluster(gather_news(since)), analyzer)

    ups = sum(s["effect"] == "bullish" for s in stories)
    downs = sum(s["effect"] == "bearish" for s in stories)
    if spx is not None and (spx >= 0.5 or (spx > 0 and ups > downs)):
        mood = "bullish"
    elif spx is not None and (spx <= -0.5 or (spx < 0 and downs > ups)):
        mood = "bearish"
    elif spx is None and ups != downs:
        mood = "bullish" if ups > downs else "bearish"
    else:
        mood = "mixed"

    period = "over the past week" if weekend else "in the last session"
    reason = []
    if spx is not None:
        reason.append(f"The S&P 500 {'rose' if spx >= 0 else 'fell'} {abs(spx):.1f}% {period}.")
    reason.append(f"Of today's top {len(stories)} stories, {ups} lean bullish and {downs} lean bearish.")

    themes = list(dict.fromkeys(TOPIC_NAMES[s["_topic"]] for s in stories))[:3]
    bottom = []
    if themes:
        bottom.append(f"The biggest themes right now are {join_words(themes)}.")
    if stories:
        bottom.append(f"The top story: {stories[0]['headline'].rstrip('.')}.")
    bottom.append(reason[-1])
    bottom.append("This briefing is put together automatically from headlines and market data, and the bullish or bearish "
                  "ratings come from keyword rules, so read the linked articles before drawing conclusions.")

    if weekend:
        monday = day - datetime.timedelta(days=day.weekday())
        start, end = monday, monday + datetime.timedelta(days=4)  # the trading week that just ended
        span = f"{start:%b} {start.day} to {end.day}" if start.month == end.month else f"{start:%b} {start.day} to {end:%b} {end.day}"
        coverage = f"Weekend edition, week of {span}"
    else:
        coverage = f"Pre-market, {day:%a %b} {day.day}"

    for s in stories:
        for k in ("_score", "_topic", "_published"):
            s.pop(k, None)
    return {
        "date": day.isoformat(),
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage": coverage,
        "mood": mood,
        "moodReason": " ".join(reason),
        "snapshot": snap,
        "stories": stories,
        "watch": [],
        "bottomLine": " ".join(bottom),
    }


def clean_text(value):
    """House style for the site: no en or em dashes, no middle dots."""
    if isinstance(value, str):
        value = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1 to \2", value)
        value = re.sub(r"\s*[–—]\s*", ", ", value)
        return re.sub(r"\s*·\s*", ", ", value)
    if isinstance(value, list):
        return [clean_text(v) for v in value]
    if isinstance(value, dict):
        return {k: (v if k == "url" else clean_text(v)) for k, v in value.items()}
    return value


def validate(b, day=None):
    """Return a list of problems; empty means the briefing is safe to publish."""
    problems = []
    for key, kind in [("date", str), ("coverage", str), ("mood", str), ("moodReason", str),
                      ("snapshot", list), ("stories", list), ("watch", list), ("bottomLine", str)]:
        if not isinstance(b.get(key), kind):
            problems.append(f"missing or wrong type: {key}")
    if problems:
        return problems
    if day and b["date"] != day.isoformat():
        problems.append(f"date is {b['date']}, expected {day.isoformat()}")
    if b["mood"] not in ("bullish", "bearish", "mixed"):
        problems.append(f"bad mood: {b['mood']}")
    if not 3 <= len(b["stories"]) <= 15:
        problems.append(f"only {len(b['stories'])} stories (news feeds may be down)")
    if not b["snapshot"]:
        problems.append("no market data (price source may be down)")
    for i, s in enumerate(b["stories"]):
        for key in ("headline", "what", "why"):
            if not isinstance(s.get(key), str) or not s[key].strip():
                problems.append(f"story {i + 1}: missing {key}")
        if s.get("effect") not in ("bullish", "bearish", "neutral"):
            problems.append(f"story {i + 1}: bad effect {s.get('effect')}")
        if s.get("impact") not in ("high", "medium", "low"):
            problems.append(f"story {i + 1}: bad impact {s.get('impact')}")
        if not any(str(x.get("url", "")).startswith("http") for x in s.get("sources") or []):
            problems.append(f"story {i + 1}: no source URL")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the briefing instead of writing it")
    ap.add_argument("--check", metavar="FILE", help="validate an existing briefing file and exit")
    args = ap.parse_args()

    if args.check:
        problems = validate(json.loads(Path(args.check).read_text()))
        print("\n".join(problems) or "OK")
        sys.exit(1 if problems else 0)

    now = datetime.datetime.now(datetime.timezone.utc)
    day = now.astimezone(TIMEZONE).date()
    briefing = clean_text(build_briefing(day, now))
    problems = validate(briefing, day)
    if problems:
        sys.exit("Briefing failed validation, not publishing:\n- " + "\n- ".join(problems))

    out = json.dumps(briefing, indent=2, ensure_ascii=False, sort_keys=True)
    if args.dry_run:
        print(out)
        return
    path = ROOT / "briefings" / f"{day.isoformat()}.json"
    path.write_text(out + "\n")
    print(f"Wrote {path.relative_to(ROOT)}: {briefing['mood']}, {len(briefing['stories'])} stories")


if __name__ == "__main__":
    main()
