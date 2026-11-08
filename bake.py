"""Bakes the latest briefing into index.html so it reads without JavaScript (the script re-renders it on load)."""
import json, html, re, datetime, sys
e = lambda s: html.escape(str(s if s is not None else ""), quote=True)
dates = json.load(open("briefings/index.json"))["dates"]
if not dates: sys.exit(0)
d = dates[0]; b = json.load(open(f"briefings/{d}.json"))
def direction(ch):
    s = str(ch or "").strip()
    return "up" if s.startswith("+") else "down" if s.startswith(("-", "−")) else "flat"
signed = lambda s: re.sub(r"^-(?=\d)", "\u2212", str(s or ""))
try: day = datetime.date.fromisoformat(d).strftime("%A, %B %-d, %Y")
except Exception: day = d
mood = (b.get("mood") or "mixed").lower()
cov = re.sub(r"\s+·\s+", ", ", b.get("coverage") or "")
marks = {"bullish": "▲ ", "bearish": "▼ ", "neutral": ""}
stories = b.get("stories") or []
ups = sum(s.get("effect") == "bullish" for s in stories); downs = sum(s.get("effect") == "bearish" for s in stories)
out = [f'<section class="mood" aria-label="Market mood"><div class="container">',
  f'<p class="dateline small"><span class="day">{e(day)}</span>' + (f'<span>{e(cov)}</span>' if cov else '') + '</p>',
  f'<div class="gauge {e(mood)}"><h1><span class="visually-hidden">Market mood: </span><span class="fit">{e(mood)}</span></h1></div>',
  f'<div class="reason"><p class="small">Overall market mood</p><p class="lead">{e(b.get("moodReason"))}</p></div></div></section>']
if b.get("snapshot"):
    out.append('<section aria-label="Market snapshot"><div class="container"><ul class="figures">' + "".join(
      f'<li><span class="small">{e(t.get("asset"))}</span><span class="v">{e(t.get("value"))}</span><span class="c {direction(t.get("change"))}">{e(signed(t.get("change")))}</span></li>'
      for t in b["snapshot"]) + '</ul></div></section>')
lots = []
for s in stories:
    eff = (s.get("effect") or "neutral").lower(); imp = (s.get("impact") or "").lower()
    lots.append(f'<li class="lot {e(eff)}"><div class="verdict"><span class="effect">{marks.get(eff,"")}{e(eff.capitalize())}</span>'
      + (f'<span class="small">{e(imp.capitalize())} impact</span>' if imp else '') + '</div><div class="body">'
      + f'<h3>{e(s.get("headline"))}</h3><p>{e(s.get("what"))}</p>'
      + (('<ul class="tags" aria-label="Affected">' + "".join(f'<li>{e(a)}</li>' for a in s["affected"]) + '</ul>') if s.get("affected") else '')
      + (f'<p class="why"><strong>Why it matters:</strong> {e(s.get("why"))}</p>' if s.get("why") else '')
      + (('<p class="sources"><span class="small">Sources</span>' + "".join(f'<a href="{e(x.get("url"))}" target="_blank" rel="noopener">{e(x.get("title") or "Source")}</a>' for x in s["sources"] if str(x.get("url","")).startswith("http")) + '</p>') if s.get("sources") else '')
      + '</div></li>')
side = ''
if b.get("watch"):
    side += '<section class="particulars" aria-labelledby="watch-h"><h2 id="watch-h">What to watch</h2><dl>' + "".join(
      f'<div class="item"><dt>{e(w.get("when"))}</dt><dd>{e(w.get("item"))}</dd></div>' for w in b["watch"]) + '</dl></section>'
if b.get("bottomLine"):
    side += f'<section class="band" aria-labelledby="bottom-h"><h2 id="bottom-h">Bottom line</h2><p>{e(b["bottomLine"])}</p></section>'
out.append('<div class="container desk"><section aria-labelledby="lots-h"><div class="lots-head rule-bar"><div class="row">'
  f'<h2 id="lots-h">Top stories</h2><p class="small">{len(stories)} stories, {ups} bullish, {downs} bearish</p></div></div>'
  f'<ol class="lots">{"".join(lots)}</ol></section><aside class="side">{side}</aside></div>')
page = open("index.html").read()
# Two baked regions: the mood and figures above the live-markets section, the stories below it.
def bake(page, name, parts):
    return re.sub(rf"<!-- baked:{name}:start -->.*?<!-- baked:{name}:end -->",
                  lambda m: f"<!-- baked:{name}:start -->\n" + "\n".join(parts) + f"\n<!-- baked:{name}:end -->", page, flags=re.S)
new = bake(bake(page, "top", out[:-1]), "desk", out[-1:])
open("index.html", "w").write(new)
print("Baked", d, "into index.html")
