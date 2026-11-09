"""Bakes the latest briefing into index.html so it reads without JavaScript (the script re-renders it on load).

The markup here mirrors render(), threeBlock() and renderLots() in index.html; change both together.
"""
import json, html, re, datetime, sys
e = lambda s: html.escape(str(s if s is not None else ""), quote=True)
dates = json.load(open("briefings/index.json"))["dates"]
if not dates: sys.exit(0)
d = dates[0]; b = json.load(open(f"briefings/{d}.json"))

def direction(ch):
    s = str(ch or "").strip()
    return "up" if s.startswith("+") else "down" if s.startswith(("-", "−")) else "flat"
signed = lambda s: re.sub(r"^-(?=\d)", "−", str(s or ""))
try: day = datetime.date.fromisoformat(d).strftime("%A, %B %-d, %Y")
except Exception: day = d
mood = (b.get("mood") or "mixed").lower()
cov = re.sub(r"\s+·\s+", ", ", b.get("coverage") or "")
marks = {"bullish": "▲ ", "bearish": "▼ ", "neutral": ""}
labels = {"bullish": "Bullish", "bearish": "Bearish", "neutral": "Neutral"}
stories = b.get("stories") or []
ups = sum(s.get("effect") == "bullish" for s in stories); downs = sum(s.get("effect") == "bearish" for s in stories)

def verdict(s):
    eff = (s.get("effect") or "neutral").lower(); imp = (s.get("impact") or "").lower()
    return (f'<p class="verdict"><span class="effect">{marks.get(eff, "")}{e(labels.get(eff, eff.capitalize()))}</span>'
            + (f', {e(imp)} impact' if imp else '') + '</p>')
def tags(s):
    return ('<ul class="tags" aria-label="Affected">' + "".join(f'<li>{e(a)}</li>' for a in s["affected"]) + '</ul>') if s.get("affected") else ''
def sources(s):
    links = "".join(f'<a href="{e(x.get("url"))}" target="_blank" rel="noopener">{e(x.get("title") or "Source")}</a>'
                    for x in (s.get("sources") or []) if str(x.get("url", "")).startswith("http"))
    return f'<p class="sources"><span>Sources</span>{links}</p>' if links else ''
def why(s):
    return f'<p class="why"><strong>Why it matters:</strong> {e(s.get("why"))}</p>' if s.get("why") else ''
def eff(s): return e((s.get("effect") or "neutral").lower())

# ---- top: dateline, the mood deck, the market figures, then the top stories as headlines ----
top = [
  '<section class="deck" aria-label="Market mood"><div class="container">'
  f'<p class="dateline"><span class="day">{e(day)}</span>' + (f'<span>{e(cov)}</span>' if cov else '') + '</p>'
  f'<div class="mood {e(mood)}"><h2 class="mood-label">Market mood</h2><p class="mood-word">{marks.get(mood, "")}{e(mood)}</p></div>'
  f'<p class="deck-reason">{e(b.get("moodReason"))}</p></div></section>']
if b.get("snapshot"):
    top.append('<section class="ticker" aria-label="Market snapshot"><div class="container"><ul class="figures">' + "".join(
      f'<li><span class="small">{e(t.get("asset"))}</span><span class="v">{e(t.get("value"))}</span><span class="c {direction(t.get("change"))}">{e(signed(t.get("change")))}</span></li>'
      for t in b["snapshot"]) + '</ul></div></section>')
three = stories[:3]
if three:
    head = "1 thing to know" if len(three) == 1 else f"{len(three)} things to know"
    top.append('<section class="three" aria-labelledby="three-h"><div class="container">'
               f'<h2 id="three-h" class="section-head">{head}</h2><ol class="three-list">'
               + "".join(f'<li class="{eff(s)}"><h3>{e(s.get("headline"))}</h3>{verdict(s)}</li>' for s in three)
               + '</ol></div></section>')

# ---- desk (inside the "See all" disclosure): the front page ----
def lead_story(s):
    return (f'<article class="lead-story {eff(s)}"><h2 class="headline">{e(s.get("headline"))}</h2>{verdict(s)}'
            f'<p class="standfirst">{e(s.get("what"))}</p>{why(s)}{tags(s)}{sources(s)}</article>')
def story(s):
    more = why(s) + sources(s)
    return (f'<article class="story {eff(s)}"><h3>{e(s.get("headline"))}</h3>{verdict(s)}<p>{e(s.get("what"))}</p>{tags(s)}'
            + (f'<details class="more"><summary>{"Why it matters" if s.get("why") else "Sources"}</summary>{more}</details>' if more else '')
            + '</article>')
watch = ''
if b.get("watch"):
    watch = ('<section class="watch sheet" aria-labelledby="watch-h"><h2 id="watch-h" class="section-head">What to watch</h2><dl>' + "".join(
      f'<div class="item"><dt>{e(w.get("when"))}</dt><dd>{e(w.get("item"))}</dd></div>' for w in b["watch"]) + '</dl></section>')
grid = '<div class="front-grid">'
if stories: grid += lead_story(stories[0])
col = ''
if stories[1:3]:
    col += '<section class="also" aria-labelledby="also-h"><h2 id="also-h" class="section-head">Also today</h2>' + "".join(story(s) for s in stories[1:3]) + '</section>'
grid += f'<div class="front-col">{col}{watch}</div>'
if stories[3:]:
    grid += ('<section class="brief" aria-labelledby="brief-h"><h2 id="brief-h" class="section-head">In brief</h2><div class="brief-grid">'
             + "".join(story(s) for s in stories[3:]) + '</div></section>')
grid += '</div>'
desk = []
desk.append(
  '<div class="container front">'
  f'<div class="frontbar"><p class="small">{len(stories)} stories, {ups} bullish, {downs} bearish</p></div>'
  f'<section class="stories" aria-label="Top stories"><div id="lots-list">{grid}</div></section>'
  + (f'<section class="band" aria-labelledby="bottom-h"><h2 id="bottom-h" class="section-head">Bottom line</h2><p>{e(b["bottomLine"])}</p></section>' if b.get("bottomLine") else '')
  + '</div>')

label = f'See all {len(stories)} {"story" if len(stories) == 1 else "stories"}' if stories else 'See the full briefing'

# Two baked regions, the top (#top) and the front page (#desk), plus the disclosure's label.
def bake(page, name, parts):
    return re.sub(rf"<!-- baked:{name}:start -->.*?<!-- baked:{name}:end -->",
                  lambda m: f"<!-- baked:{name}:start -->\n" + "\n".join(parts) + f"\n<!-- baked:{name}:end -->", page, flags=re.S)
page = open("index.html").read()
page = bake(bake(page, "top", top), "desk", desk)
page = re.sub(r'(<span class="when-closed" id="full-label">)[^<]*(</span>)', lambda m: m.group(1) + e(label) + m.group(2), page)
open("index.html", "w").write(page)
print("Baked", d, "into index.html")
