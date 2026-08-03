#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ND Capital — static site generator.

Reads the research repository and emits the whole public site. No dependencies:
runs on a clean Python 3.8+ install so the site can be rebuilt on any machine.

    python website/build.py

Inputs
    website/config.json                  site settings + Formspree form ID
    website/data/coverage.json           structured ratings (from write_research.py)
    website/data/fundamentals.json       vendor market data
    website/data/themes.json             theme index (from write_themes.py)
    Research/Companies/<T>/00_THESIS.md  full company research
    Research/Themes/<slug>/00_THEME.md   full theme research
    website/content/briefs/*.md          morning briefs
    website/content/insights/*.md        long-form articles

Outputs (all inside website/)
    index.html
    coverage/index.html, coverage/<TICKER>.html
    themes/index.html, themes/<slug>.html
    insights/index.html, insights/<slug>.html
    briefs/index.html, briefs/<date>.html
    methodology.html, track-record.html

The cross-reference that makes the stock pages work: every brief and insight
declares `tickers:` in its front matter, and build.py inverts that into a
per-ticker feed. Publish a note mentioning MU and it appears on the MU page
automatically — no manual linking anywhere.
"""

import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime

import md

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
CONTENT = os.path.join(HERE, "content")
COMPANY_DIR = os.path.join(ROOT, "Research", "Companies")
THEME_DIR = os.path.join(ROOT, "Research", "Themes")

BUILT = datetime.now().strftime("%Y-%m-%d %H:%M")


# ============================================================ helpers

def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(rel, content):
    path = os.path.join(HERE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return rel


def money(v, dp=2):
    if v is None:
        return "—"
    if abs(v) >= 1e12:
        return f"${v/1e12:.2f}tn"
    if abs(v) >= 1e9:
        return f"${v/1e9:.0f}bn"
    if abs(v) >= 1e6:
        return f"${v/1e6:.0f}m"
    return f"${v:,.{dp}f}"


def pct(v, dp=1, sign=False):
    if v is None:
        return "—"
    s = "+" if (sign and v > 0) else ""
    return f"{s}{v*100:.{dp}f}%"


def xnum(v, dp=1):
    return "—" if v is None else f"{v:,.{dp}f}x"


def chip(rating):
    cls = {"Overweight": "chip-ow", "Neutral": "chip-n", "Underweight": "chip-uw"}.get(rating, "chip-mute")
    return f'<span class="chip {cls}">{rating}</span>'


def updown(v, dp=1):
    if v is None:
        return '<span class="dim">—</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "dim")
    return f'<span class="{cls}">{v*100:+.{dp}f}%</span>'


def nice_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").strftime("%-d %b %Y")
    except (ValueError, TypeError):
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")
        except (ValueError, TypeError):
            return str(s)


def theme_name(slug, themes):
    for t in themes:
        if t["slug"] == slug:
            return t["name"]
    return slug.replace("-", " ")


# ============================================================ chrome

CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))

NAV = [
    ("Coverage", "coverage/"),
    ("Themes", "themes/"),
    ("Briefs", "briefs/"),
    ("Insights", "insights/"),
    ("Track Record", "track-record.html"),
    ("Methodology", "methodology.html"),
]


def nav_items(up, active):
    out = []
    for label, href in NAV:
        cls = ' class="active"' if label == active else ""
        out.append(f'<li><a href="{up}{href}"{cls}>{label}</a></li>')
    return "".join(out)


def head(title, desc, depth, active=""):
    up = "../" * depth
    links = nav_items(up, active)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<link rel="icon" type="image/png" href="{up}assets/nd-capital-monogram.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}assets/site.css">
</head>
<body{' class="solid-header"' if depth or active else ''}>

<header id="header">
  <div class="wrap nav">
    <a class="nav-logo" href="{up}index.html" aria-label="ND Capital home">
      <img src="{up}assets/nd-capital-reversed-horizontal-lockup.svg" alt="ND Capital"
           onerror="this.onerror=null;this.src='{up}assets/nd-capital-reversed-horizontal-lockup.png';">
    </a>
    <button class="nav-toggle" id="nav-toggle" aria-label="Menu" aria-expanded="false">☰</button>
    <ul class="nav-links" id="nav-links">
      {links}
      <li><a href="{up}index.html#subscribe" class="btn btn-gold btn-sm">Subscribe</a></li>
    </ul>
  </div>
</header>
"""


def subscribe_block(depth, compact=False):
    fid = CFG.get("formspree_id", "").strip()
    action = f'https://formspree.io/f/{fid}' if fid else ""
    live = "true" if fid else "false"
    return f"""
<section class="subscribe {'tight' if compact else ''}" id="subscribe">
  <div class="wrap">
    <div class="sub-card rv">
      <div class="kicker" style="justify-content:center;">The Daily Brief</div>
      <h2>{CFG['newsletter_heading']}</h2>
      <p>{CFG['newsletter_sub']}</p>
      <form class="sub-form" id="sub-form" data-live="{live}" action="{action}" method="POST">
        <input type="email" name="email" id="sub-email" placeholder="you@email.com" required aria-label="Email address">
        <input type="text" name="_gotcha" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true">
        <button class="btn btn-gold" type="submit" id="sub-btn">Subscribe</button>
      </form>
      <div class="sub-msg" id="sub-msg" role="status" aria-live="polite"></div>
      <div class="sub-note">Research and education only — not investment advice.</div>
    </div>
  </div>
</section>
"""


def foot(depth):
    up = "../" * depth
    year = datetime.now().year
    return f"""
<footer>
  <div class="wrap">
    <div class="foot-top">
      <img src="{up}assets/nd-capital-reversed-horizontal-lockup.png" alt="ND Capital">
      <div class="foot-links">
        <div class="col">
          <h4>Research</h4>
          <a href="{up}coverage/">Coverage universe</a>
          <a href="{up}themes/">Themes</a>
          <a href="{up}insights/">Insights</a>
        </div>
        <div class="col">
          <h4>Daily</h4>
          <a href="{up}briefs/">Morning briefs</a>
          <a href="{up}index.html#subscribe">Subscribe</a>
        </div>
        <div class="col">
          <h4>About</h4>
          <a href="{up}methodology.html">Methodology</a>
          <a href="{up}track-record.html">Track record</a>
        </div>
      </div>
    </div>
    <div class="disclaimer">
      © {year} ND Capital. All rights reserved. Site built {BUILT}.<br><br>
      <strong>Disclaimer:</strong> {CFG['disclaimer']}
    </div>
  </div>
</footer>

<script>
(function () {{
  var header = document.getElementById('header');
  function onScroll() {{ header.classList.toggle('scrolled', window.scrollY > 30); }}
  window.addEventListener('scroll', onScroll, {{ passive: true }}); onScroll();

  var t = document.getElementById('nav-toggle'), l = document.getElementById('nav-links');
  if (t) t.addEventListener('click', function () {{
    var open = l.classList.toggle('open');
    t.setAttribute('aria-expanded', open ? 'true' : 'false');
  }});

  var io = new IntersectionObserver(function (es) {{
    es.forEach(function (e) {{ if (e.isIntersecting) {{ e.target.classList.add('in'); io.unobserve(e.target); }} }});
  }}, {{ threshold: 0.08, rootMargin: '0px 0px -5% 0px' }});
  document.querySelectorAll('.rv').forEach(function (el) {{ io.observe(el); }});

  /* ---- Newsletter ---- */
  var f = document.getElementById('sub-form');
  if (f) f.addEventListener('submit', function (e) {{
    e.preventDefault();
    var msg = document.getElementById('sub-msg'), btn = document.getElementById('sub-btn');
    if (f.dataset.live !== 'true') {{
      msg.className = 'sub-msg err';
      msg.textContent = 'The mailing list is not connected yet — please check back shortly.';
      return;
    }}
    btn.disabled = true; btn.textContent = 'Sending…';
    fetch(f.action, {{ method: 'POST', body: new FormData(f), headers: {{ 'Accept': 'application/json' }} }})
      .then(function (r) {{
        if (r.ok) {{ f.style.display = 'none'; msg.className = 'sub-msg ok';
                     msg.textContent = "Thank you — you're on the list."; }}
        else {{ throw new Error('rejected'); }}
      }})
      .catch(function () {{
        btn.disabled = false; btn.textContent = 'Subscribe';
        msg.className = 'sub-msg err';
        msg.textContent = 'Something went wrong. Please try again in a moment.';
      }});
  }});

  /* ---- Sortable tables ---- */
  document.querySelectorAll('table.sortable').forEach(function (tbl) {{
    tbl.querySelectorAll('th[data-sort]').forEach(function (th, idx) {{
      th.addEventListener('click', function () {{
        var body = tbl.tBodies[0], rows = Array.prototype.slice.call(body.rows);
        var col = Array.prototype.indexOf.call(th.parentNode.children, th);
        var desc = !th.classList.contains('desc');
        tbl.querySelectorAll('th').forEach(function (o) {{ o.classList.remove('asc','desc'); }});
        th.classList.add(desc ? 'desc' : 'asc');
        rows.sort(function (a, b) {{
          var x = a.cells[col].dataset.v, y = b.cells[col].dataset.v;
          var nx = parseFloat(x), ny = parseFloat(y);
          if (!isNaN(nx) && !isNaN(ny)) return desc ? ny - nx : nx - ny;
          x = (x || a.cells[col].innerText).toLowerCase();
          y = (y || b.cells[col].innerText).toLowerCase();
          return desc ? (y > x ? 1 : -1) : (x > y ? 1 : -1);
        }});
        rows.forEach(function (r) {{ body.appendChild(r); }});
      }});
    }});
  }});

  /* ---- Coverage filter ---- */
  var filt = document.getElementById('cov-filter');
  if (filt) {{
    var chips = document.querySelectorAll('[data-filter]');
    chips.forEach(function (c) {{
      c.addEventListener('click', function (e) {{
        e.preventDefault();
        chips.forEach(function (o) {{ o.classList.remove('chip-ow'); o.classList.add('chip-mute'); }});
        c.classList.remove('chip-mute'); c.classList.add('chip-ow');
        var want = c.dataset.filter;
        document.querySelectorAll('[data-rating]').forEach(function (row) {{
          row.style.display = (want === 'all' || row.dataset.rating === want) ? '' : 'none';
        }});
      }});
    }});
  }}
}})();
</script>

</body>
</html>
"""


def page(title, desc, depth, body, active="", subscribe=True):
    return (head(title, desc, depth, active) + body
            + (subscribe_block(depth, compact=True) if subscribe else "")
            + foot(depth))


# ============================================================ load

def load_publications():
    """Briefs and insights, newest first, with a ticker -> [pub] reverse index."""
    pubs = []
    for kind, folder in (("brief", "briefs"), ("insight", "insights")):
        d = os.path.join(CONTENT, folder)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            meta, body = md.split_front_matter(read(os.path.join(d, fn)))
            slug = os.path.splitext(fn)[0]
            pubs.append({
                "kind": kind,
                "slug": slug,
                "url": f"{folder}/{slug}.html",
                "title": meta.get("title", slug),
                "subtitle": meta.get("standfirst") or meta.get("subtitle") or "",
                "summary": meta.get("summary") or meta.get("standfirst") or md.strip_md(body, 180),
                "date": str(meta.get("date", ""))[:10],
                "category": meta.get("category", "Morning Brief" if kind == "brief" else "Research"),
                "tickers": meta.get("tickers") or [],
                "tags": meta.get("tags") or [],
                "reading_time": meta.get("reading_time"),
                "body": body,
            })
    pubs.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)

    by_ticker = defaultdict(list)
    for p in pubs:
        for t in p["tickers"]:
            by_ticker[t].append(p)
    return pubs, by_ticker


def load_research():
    """Parsed 00_THESIS.md per ticker and 00_THEME.md per theme."""
    companies, themes = {}, {}
    for slug in sorted(os.listdir(COMPANY_DIR)) if os.path.isdir(COMPANY_DIR) else []:
        f = os.path.join(COMPANY_DIR, slug, "00_THESIS.md")
        if os.path.isfile(f):
            meta, body = md.split_front_matter(read(f))
            if meta.get("ticker"):
                companies[meta["ticker"]] = {"meta": meta, "sections": md.sections(body)}
    for slug in sorted(os.listdir(THEME_DIR)) if os.path.isdir(THEME_DIR) else []:
        f = os.path.join(THEME_DIR, slug, "00_THEME.md")
        if os.path.isfile(f):
            meta, body = md.split_front_matter(read(f))
            themes[slug] = {"meta": meta, "sections": md.sections(body)}
    return companies, themes


# ============================================================ components

def feed_list(pubs, depth, limit=None, empty="Nothing published yet."):
    up = "../" * depth
    items = pubs[:limit] if limit else pubs
    if not items:
        return f'<p class="dim small">{empty}</p>'
    rows = []
    for p in items:
        rt = f" · {p['reading_time']} min read" if p.get("reading_time") else ""
        rows.append(
            f'<li><a href="{up}{p["url"]}">'
            f'<span class="date">{nice_date(p["date"])}</span>'
            f'<span><span class="ti">{p["title"]}</span>'
            f'<span class="su">{p["subtitle"] or p["summary"]}</span>'
            f'<span class="kind">{p["category"]}{rt}</span></span></a></li>')
    return f'<ul class="feed">{"".join(rows)}</ul>'


def cov_card(c, depth):
    up = "../" * depth
    return f"""<a class="card cov-card hoverable" href="{up}coverage/{c['ticker']}.html" data-rating="{c['rating']}">
  <div class="top"><span class="tk">{c['ticker']}</span>{chip(c['rating'])}</div>
  <div class="co">{c['name']}</div>
  <div class="line">{c['one_liner']}</div>
  <div class="foot">
    <span>Target <b>{money(c['target'], 0) if c['target'] else 'n/a'}</b></span>
    <span>Upside <b>{updown(c['upside'])}</b></span>
    <span>Fwd P/E <b>{xnum(c['forward_pe'])}</b></span>
  </div>
</a>"""


# ============================================================ pages

def risk_chip(level):
    cls = {"Low": "risk-low", "Medium": "risk-med",
           "High": "risk-high", "Very high": "risk-high"}.get(level, "chip-mute")
    return f'<span class="risk {cls}">{level or "—"}</span>'


def build_home(cov, themes, pubs, fund, earn):
    cs = cov["companies"]
    ow = [c for c in cs if c["rating"] == "Overweight"]
    n = [c for c in cs if c["rating"] == "Neutral"]
    uw = [c for c in cs if c["rating"] == "Underweight"]
    latest = pubs[0] if pubs else None
    top = sorted([c for c in cs if c["upside"] is not None],
                 key=lambda c: -c["upside"])[:6]

    marquee = "".join(
        f'<span><i>◆</i>{c["ticker"]} {c["rating"]} {money(c["target"],0) if c["target"] else ""}</span>'
        for c in cs[:14])

    brief_html = ""
    if latest:
        brief_html = f"""
    <a class="card hoverable" href="{latest['url']}" style="display:block;padding:40px 44px;position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--gold),transparent 60%);"></div>
      <div style="font-size:11.5px;color:var(--gold);letter-spacing:.22em;text-transform:uppercase;margin-bottom:14px;">
        {nice_date(latest['date'])} · {latest['category']}</div>
      <h3 style="font-family:var(--serif);font-size:27px;font-weight:600;color:var(--ivory);margin-bottom:14px;line-height:1.28;">{latest['title']}</h3>
      <p style="color:var(--text-dim);max-width:800px;">{latest['subtitle'] or latest['summary']}</p>
      <div class="pill-row" style="margin-top:22px;">{''.join(f'<span class="tag">{t}</span>' for t in latest['tags'][:5])}</div>
    </a>"""

    body = f"""
<section class="hero" id="top" style="position:relative;min-height:92vh;display:flex;align-items:center;
  background:radial-gradient(1000px 560px at 80% 16%,rgba(201,164,92,.10),transparent 60%),
             radial-gradient(860px 640px at 10% 84%,rgba(37,76,134,.42),transparent 65%),
             linear-gradient(165deg,var(--navy) 0%,var(--navy-deep) 55%,var(--navy-black) 100%);overflow:hidden;">
  <canvas id="hero-canvas" style="position:absolute;inset:0;width:100%;height:100%;opacity:.85;"></canvas>
  <div style="position:absolute;inset:0;pointer-events:none;z-index:2;
    background:radial-gradient(120% 90% at 50% 40%,transparent 55%,rgba(4,10,22,.55) 100%),
               linear-gradient(180deg,rgba(4,10,22,.5) 0%,transparent 14%,transparent 82%,rgba(4,10,22,.6) 100%);"></div>
  <div class="wrap" style="position:relative;z-index:3;padding:150px 28px 130px;max-width:1180px;">
    <div style="max-width:840px;">
      <div class="kicker rv in">Coverage initiated · 2 August 2026</div>
      <h1 style="font-family:var(--serif);font-weight:700;font-size:clamp(38px,6vw,72px);line-height:1.06;
        margin:24px 0 24px;color:var(--ivory);letter-spacing:-.015em;" class="rv in rv-d1">
        The AI trade stopped being<br>about <em style="font-style:italic;color:var(--gold-bright);">demand</em>.</h1>
      <p class="rv in rv-d2" style="font-size:19px;color:var(--text-dim);max-width:640px;margin-bottom:38px;">
        Semiconductors are in a bear market while memory contract prices keep rising. That is not a demand
        signal — it is the market repricing who pays for the build-out. {len(cs)} names, full research,
        every rating with the evidence that would prove it wrong.</p>
      <div class="rv in rv-d3" style="display:flex;gap:14px;flex-wrap:wrap;">
        <a href="coverage/" class="btn btn-gold">View the coverage book</a>
        <a href="{latest['url'] if latest else 'briefs/'}" class="btn btn-line">Read today's brief</a>
      </div>
    </div>
  </div>
  <div style="position:absolute;bottom:0;left:0;right:0;z-index:4;border-top:1px solid var(--line);
    background:rgba(6,15,33,.6);backdrop-filter:blur(8px);overflow:hidden;padding:14px 0;white-space:nowrap;">
    <div id="marquee-track" style="display:inline-block;animation:marquee 48s linear infinite;
      font-size:11.5px;letter-spacing:.26em;text-transform:uppercase;color:var(--text-dim);">{marquee}</div>
  </div>
</section>
<style>
  @keyframes marquee {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-50%); }} }}
  #marquee-track span {{ margin: 0 30px; }}
  #marquee-track i {{ font-style: normal; color: var(--gold); margin-right: 30px; }}
</style>

<section class="tight">
  <div class="wrap">
    <div class="stats">
      <div class="card stat rv"><div class="v">{len(cs)}</div><div class="k">Names covered</div></div>
      <div class="card stat rv rv-d1"><div class="v" style="color:var(--green);">{len(ow)}</div><div class="k">Overweight</div></div>
      <div class="card stat rv rv-d2"><div class="v" style="color:var(--gold-bright);">{len(n)}</div><div class="k">Neutral</div></div>
      <div class="card stat rv rv-d3"><div class="v" style="color:var(--red);">{len(uw)}</div><div class="k">Underweight</div></div>
      <div class="card stat rv rv-d4"><div class="v">{len(themes['themes'])}</div><div class="k">Themes tracked</div></div>
    </div>
  </div>
</section>

<section id="brief">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">Every morning, before the open</div>
      <h2>The Morning Brief</h2>
      <p>What moved overnight, what matters today, and how it changes the book.</p>
    </div>
    <div class="rv rv-d1">{brief_html or '<p class="dim">First brief publishes Monday.</p>'}</div>
    <div style="margin-top:26px;"><a href="briefs/" class="btn btn-line btn-sm">All briefs</a></div>
  </div>
</section>

<section class="sec-alt" id="conviction">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">Where we see the most upside</div>
      <h2>Highest-conviction ideas</h2>
      <p>Ranked by implied upside to our target. Every one of these has a published bear case and a
         written-down list of what would prove us wrong.</p>
    </div>
    <div class="grid grid-3">
      {''.join(f'<div class="rv rv-d{min(i+1,4)}">{cov_card(c, 0)}</div>' for i, c in enumerate(top))}
    </div>
    <div style="margin-top:30px;"><a href="coverage/" class="btn btn-line btn-sm">Full coverage universe</a></div>
  </div>
</section>

<section id="themes-preview">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">The industry map</div>
      <h2>Themes we track</h2>
      <p>Where each theme sits in its lifecycle, who captures the profit pool, and the bear case for
         the theme itself — argued at full strength.</p>
    </div>
    <div class="grid grid-2">
      {''.join(f'''<a class="card ins-card hoverable rv rv-d{min(i%4+1,4)}" href="themes/{t["slug"]}.html">
        <div class="cat">{t["stage"]}</div>
        <h3>{t["name"]}</h3>
        <p>{t["blurb"]}</p>
        <span class="read">Read the theme</span></a>''' for i, t in enumerate(themes["themes"][:6]))}
    </div>
    <div style="margin-top:30px;"><a href="themes/" class="btn btn-line btn-sm">All {len(themes['themes'])} themes</a></div>
  </div>
</section>

<section class="sec-alt" id="earnings">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">What is coming</div>
      <h2>Next results</h2>
      <p>Coverage names with a confirmed reporting date, and our earnings-risk read — how much the
         stock typically moves on results relative to what is already priced in.</p>
    </div>
    <div class="card table-card rv rv-d1">
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Date</th><th>Name</th><th>Our rating</th>
            <th>Earnings risk</th><th class="num">Consensus EPS</th><th>Timing</th></tr></thead>
          <tbody>{''.join(f'''<tr>
            <td>{nice_date(e["report_date"])}</td>
            <td><a class="tick" href="coverage/{e["ticker"]}.html">{e["ticker"]}</a>
                <div class="dim small" style="margin-top:3px;">{e["company"]}</div></td>
            <td>{chip(e["our_rating"])}</td>
            <td>{risk_chip(e.get("our_earnings_risk"))}</td>
            <td class="num">{f'${e["consensus_eps"]:.2f}' if e.get("consensus_eps") else '—'}</td>
            <td class="dim">{e.get("time_of_day") or "—"}</td>
          </tr>''' for e in earn["upcoming"])}</tbody>
        </table>
      </div>
    </div>
    <p class="dim small" style="margin-top:14px;">
      Earnings risk is our own judgement from the company deep dive, not vendor data. Reporting dates
      from {earn["source"]}; {earn["unconfirmed_count"]} further coverage names have no confirmed date yet
      because our market-data plan is capped at 25 requests a day — we publish the gap rather than an
      estimated date presented as a confirmed one.</p>
  </div>
</section>

<section id="insights-preview">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">Learn with us</div>
      <h2>Insights &amp; Deep Dives</h2>
      <p>Long-form explainers written to teach the method, not to sell a view.</p>
    </div>
    <div class="grid grid-3">
      {''.join(f'''<a class="card ins-card hoverable rv rv-d{min(i+1,4)}" href="{p["url"]}">
        <div class="cat">{p["category"]}</div><h3>{p["title"]}</h3><p>{p["summary"]}</p>
        <span class="read">Read{f' · {p["reading_time"]} min' if p.get("reading_time") else ''}</span></a>'''
        for i, p in enumerate([x for x in pubs if x["kind"] == "insight"][:3]))}
    </div>
  </div>
</section>

<script>
(function () {{
  var c = document.getElementById('hero-canvas'); if (!c) return;
  var ctx = c.getContext('2d'), W, H;
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function resize() {{
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = c.clientWidth; H = c.clientHeight; c.width = W*dpr; c.height = H*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }}
  window.addEventListener('resize', resize); resize();
  var lines = [
    {{amp:50,freq:0.0042,speed:0.00024,y:0.62,a:0.5,w:1.7,g:16,col:'201,164,92'}},
    {{amp:70,freq:0.0030,speed:0.00016,y:0.71,a:0.2,w:1.2,g:9,col:'251,250,247'}},
    {{amp:36,freq:0.0056,speed:0.00032,y:0.54,a:0.26,w:1.1,g:11,col:'227,197,132'}},
    {{amp:88,freq:0.0022,speed:0.00010,y:0.80,a:0.11,w:1.0,g:0,col:'90,130,190'}}
  ];
  function ny(x,s,t,l) {{
    return Math.sin(x*l.freq+t+s)*l.amp + Math.sin(x*l.freq*2.7+t*1.6+s*2)*l.amp*0.35
         + Math.sin(x*l.freq*0.4+t*0.7+s*3)*l.amp*0.6;
  }}
  function draw(now) {{
    ctx.clearRect(0,0,W,H);
    lines.forEach(function (l,i) {{
      var t = now*l.speed; ctx.beginPath();
      for (var x=0;x<=W;x+=6) {{ var y=H*l.y+ny(x,i*7+1,t,l); x===0?ctx.moveTo(x,y):ctx.lineTo(x,y); }}
      ctx.strokeStyle='rgba('+l.col+','+l.a+')'; ctx.lineWidth=l.w;
      ctx.shadowBlur=l.g; ctx.shadowColor='rgba('+l.col+',0.8)'; ctx.stroke(); ctx.shadowBlur=0;
      if (i===0) {{
        ctx.lineTo(W,H); ctx.lineTo(0,H); ctx.closePath();
        var g=ctx.createLinearGradient(0,H*0.45,0,H);
        g.addColorStop(0,'rgba(201,164,92,0.11)'); g.addColorStop(1,'rgba(201,164,92,0)');
        ctx.fillStyle=g; ctx.fill();
      }}
    }});
    if (!reduced) requestAnimationFrame(draw);
  }}
  requestAnimationFrame(draw);
  var tr = document.getElementById('marquee-track'); if (tr) tr.innerHTML += tr.innerHTML;
}})();
</script>
"""
    return write("index.html", page(
        "ND Capital — AI-Powered Technology Equity Research",
        "Institutional-format equity research on the technology sector. Full coverage of 24 names with "
        "ratings, target prices, scenarios and the evidence that would prove us wrong.",
        0, body, subscribe=True))


def build_coverage_index(cov, themes):
    cs = cov["companies"]
    rows = []
    for c in cs:
        rows.append(f"""<tr data-rating="{c['rating']}">
  <td data-v="{c['ticker']}"><a class="tick" href="{c['ticker']}.html">{c['ticker']}</a>
      <div class="dim small" style="margin-top:3px;">{c['name']}</div></td>
  <td data-v="{ {'Overweight':0,'Neutral':1,'Underweight':2}.get(c['rating'],9) }">{chip(c['rating'])}</td>
  <td class="num" data-v="{c['price'] or 0}">{money(c['price'])}</td>
  <td class="num" data-v="{c['target'] or 0}">{money(c['target'],0) if c['target'] else '<span class="dim">n/a</span>'}</td>
  <td class="num" data-v="{c['upside'] if c['upside'] is not None else -9}">{updown(c['upside'])}</td>
  <td class="num" data-v="{c['forward_pe'] or 999}">{xnum(c['forward_pe'])}</td>
  <td class="num" data-v="{c['ev_ebitda'] or 999}">{xnum(c['ev_ebitda'])}</td>
  <td class="num" data-v="{c['rev_growth'] if c['rev_growth'] is not None else -9}">{pct(c['rev_growth'],0,True)}</td>
  <td class="num" data-v="{c['operating_margin'] if c['operating_margin'] is not None else -9}">{pct(c['operating_margin'],0)}</td>
  <td data-v="{c['conviction']}">{c['conviction']}</td>
</tr>""")

    counts = {r: len([c for c in cs if c["rating"] == r]) for r in ("Overweight", "Neutral", "Underweight")}

    body = f"""
<div class="page-head">
  <div class="wrap">
    <div class="kicker">Coverage universe</div>
    <h1>The coverage book</h1>
    <p class="lede">{len(cs)} technology names, each with a rating, a target price, a full scenario table and an
      explicit list of what would prove us wrong. Ratings as of {nice_date(cov.get('as_of'))}.</p>
  </div>
</div>

<section class="tight">
  <div class="wrap">
    <div class="note-box rv" style="margin-bottom:28px;">
      <strong>How to read this.</strong> The rating expresses risk/reward over roughly twelve months; the target
      is our own valuation and frequently sits below the street's. Where those two disagree, that is deliberate —
      we would rather publish a rating we believe with a target we can defend than reconcile the two after the fact.
      Every name links to the full research, including the bear case argued at full strength.
    </div>

    <div class="pill-row rv" id="cov-filter" style="margin-bottom:20px;">
      <a href="#" class="chip chip-ow" data-filter="all">All {len(cs)}</a>
      <a href="#" class="chip chip-mute" data-filter="Overweight">Overweight {counts['Overweight']}</a>
      <a href="#" class="chip chip-mute" data-filter="Neutral">Neutral {counts['Neutral']}</a>
      <a href="#" class="chip chip-mute" data-filter="Underweight">Underweight {counts['Underweight']}</a>
    </div>

    <div class="card table-card rv rv-d1">
      <div class="tbl-wrap">
        <table class="sortable">
          <thead><tr>
            <th data-sort>Name</th><th data-sort>Rating</th>
            <th class="num" data-sort>Price*</th><th class="num" data-sort>Target</th>
            <th class="num" data-sort>Upside</th><th class="num" data-sort>Fwd P/E</th>
            <th class="num" data-sort>EV/EBITDA</th><th class="num" data-sort>Rev growth</th>
            <th class="num" data-sort>Op margin</th><th data-sort>Conviction</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </div>
    <p class="dim small" style="margin-top:14px;">
      * Indicative price derived from vendor trailing P/E × TTM diluted EPS — not an exchange print.
      Click any column header to sort. Market data: Alpha Vantage, pulled {nice_date(cov.get('as_of'))}.</p>
  </div>
</section>

<section class="sec-alt">
  <div class="wrap">
    <div class="sec-head rv"><div class="kicker">At a glance</div><h2>Every name, one line each</h2></div>
    <div class="grid grid-3">
      {''.join(f'<div class="rv">{cov_card(c, 1)}</div>' for c in cs)}
    </div>
  </div>
</section>
"""
    return write("coverage/index.html", page(
        "Coverage Universe — ND Capital", "Ratings, target prices and full research on 24 technology equities.",
        1, body, active="Coverage"))


def build_stock_page(c, research, by_ticker, themes, fund):
    t = c["ticker"]
    r = research.get(t)
    f = fund.get(t, {})
    up = "../"
    pubs = by_ticker.get(t, [])

    secs = r["sections"] if r else []
    sec_map = {re.sub(r"^\d+\s*·\s*", "", k).strip(): v for k, v in secs}

    def sec(*names):
        for nm in names:
            for k, v in sec_map.items():
                if k.lower().startswith(nm.lower()):
                    return v
        return ""

    thesis = sec("Investment thesis")
    missing = sec("What the market is missing")
    scen = sec("Scenarios")
    wrong = sec("What would prove us wrong")
    cats = sec("Catalysts")
    fins = sec("Key financials")
    mgmt = sec("Management")
    expect = sec("Expectations")
    mom = sec("Momentum")
    val = sec("Valuation")
    alt = sec("Alternative data")
    log = sec("Change log")
    teach = ""
    for k, v in secs:
        if "Teaching" in k:
            teach = v

    body_md = read(os.path.join(COMPANY_DIR, c["slug"], "00_THESIS.md")) if r else ""
    m2, b2 = md.split_front_matter(body_md) if body_md else ({}, "")
    teach_m = re.search(r"### Teaching note\s*\n(.*?)(?:\n---|\Z)", b2, re.S)
    if teach_m:
        teach = teach_m.group(1).strip()

    theme_chips = "".join(
        f'<a class="tag" href="{up}themes/{s}.html">{theme_name(s, themes["themes"])}</a>'
        for s in c["themes"])

    rng = c.get("range_position")
    rng_bar = ""
    if rng is not None:
        rng_bar = f"""
      <div style="margin-top:8px;height:4px;background:rgba(251,250,247,.08);border-radius:2px;position:relative;">
        <div style="position:absolute;left:{rng:.0f}%;top:-3px;width:2px;height:10px;background:var(--gold);"></div>
      </div>
      <div class="dim" style="font-size:10px;display:flex;justify-content:space-between;margin-top:5px;">
        <span>{money(c['wk52_low'],0)}</span><span>{money(c['wk52_high'],0)}</span></div>"""

    def acc(title, content, open_=False):
        if not content.strip():
            return ""
        return (f'<details class="acc"{" open" if open_ else ""}><summary>{title}</summary>'
                f'<div class="body prose">{md.render(content)}</div></details>')

    body = f"""
<div class="page-head">
  <div class="wrap">
    <div class="crumbs"><a href="{up}index.html">Home</a> / <a href="{up}coverage/">Coverage</a> / {t}</div>
    <div class="flex-between">
      <div>
        <h1 style="margin-bottom:6px;">{t}</h1>
        <p class="lede" style="font-size:19px;color:var(--text);">{c['name']}</p>
      </div>
      <div style="text-align:right;">
        {chip(c['rating'])}
        <div style="font-family:var(--serif);font-size:38px;font-weight:700;color:var(--ivory);margin-top:10px;line-height:1;">
          {money(c['target'],0) if c['target'] else 'No target'}</div>
        <div class="dim" style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-top:6px;">
          Target · {updown(c['upside'])} implied</div>
      </div>
    </div>
    <div class="pill-row" style="margin-top:22px;">{theme_chips}</div>
  </div>
</div>

<section class="tight">
  <div class="wrap">
    <div class="stats rv">
      <div class="card stat"><div class="v sm">{money(c['price'])}</div><div class="k">Indicative price</div>{rng_bar}</div>
      <div class="card stat"><div class="v sm">{money(c['market_cap'])}</div><div class="k">Market cap</div></div>
      <div class="card stat"><div class="v sm">{xnum(c['forward_pe'])}</div><div class="k">Forward P/E</div></div>
      <div class="card stat"><div class="v sm">{xnum(c['pe'])}</div><div class="k">Trailing P/E</div></div>
      <div class="card stat"><div class="v sm">{xnum(c['ev_ebitda'])}</div><div class="k">EV / EBITDA</div></div>
      <div class="card stat"><div class="v sm">{pct(c['rev_growth'],0,True)}</div><div class="k">Rev growth YoY</div></div>
      <div class="card stat"><div class="v sm">{pct(c['operating_margin'],0)}</div><div class="k">Operating margin</div></div>
      <div class="card stat"><div class="v sm">{c['conviction']}</div><div class="k">Conviction</div></div>
      <div class="card stat"><div class="v sm">{c['earnings_risk']}</div><div class="k">Earnings risk</div></div>
      <div class="card stat"><div class="v sm">{money(c['analyst_target'],0) if c['analyst_target'] else '—'}</div><div class="k">Consensus target</div></div>
    </div>
    <p class="dim small" style="margin-top:12px;">
      Indicative price derived from trailing P/E × TTM diluted EPS — not an exchange print.
      Data: Alpha Vantage, {nice_date(c.get('last_review'))}.</p>
  </div>
</section>

<section class="tight">
  <div class="wrap-narrow">
    <div class="sec-head rv" style="margin-bottom:24px;">
      <div class="kicker">Our view</div><h2>Investment thesis</h2></div>
    <div class="prose rv rv-d1">{md.render(thesis)}</div>
  </div>
</section>

<section class="sec-alt tight">
  <div class="wrap-narrow">
    <div class="sec-head rv" style="margin-bottom:24px;">
      <div class="kicker">The edge, if there is one</div><h2>What the market is missing</h2></div>
    <div class="prose rv rv-d1">{md.render(missing)}</div>
  </div>
</section>

<section class="tight">
  <div class="wrap-narrow">
    <div class="sec-head rv" style="margin-bottom:24px;">
      <div class="kicker">Held to account</div><h2>What would prove us wrong</h2>
      <p>Specific and monitorable. If any of these prints, we change the view in public.</p></div>
    <div class="prose rv rv-d1">{md.render(wrong)}</div>
  </div>
</section>

<section class="tight">
  <div class="wrap">
    <div class="sec-head rv"><div class="kicker">The full research</div><h2>Everything behind the rating</h2></div>
    <div class="rv rv-d1">
      {acc("Scenarios &amp; probability-weighted value", scen, True)}
      {acc("Valuation — and what the multiple requires", val)}
      {acc("Catalysts", cats)}
      {acc("Key financials &amp; sector KPIs", fins)}
      {acc("Expectations &amp; earnings reaction pattern", expect)}
      {acc("Momentum, positioning &amp; narrative", mom)}
      {acc("Management &amp; guidance behaviour", mgmt)}
      {acc("Alternative data &amp; sentiment", alt)}
      {acc("Change log", log)}
    </div>
  </div>
</section>

{f'''<section class="sec-alt tight">
  <div class="wrap-narrow">
    <div class="sec-head rv" style="margin-bottom:24px;">
      <div class="kicker">Teaching note</div><h2>What this name teaches</h2>
      <p>Every piece of our research ends with the transferable lesson. The objective is not only to
         invest well, but to get better at it.</p></div>
    <div class="prose rv rv-d1">{md.render(teach)}</div>
  </div>
</section>''' if teach else ''}

<section class="tight">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">Everything we have published on {t}</div>
      <h2>Research &amp; updates</h2>
      <p>Briefs, notes and articles that reference this name, newest first. This list builds itself —
         anything we publish mentioning {t} appears here automatically.</p></div>
    <div class="rv rv-d1">{feed_list(pubs, 1, empty=f"No notes reference {t} yet. The initiation above is the first published work on this name.")}</div>
  </div>
</section>
"""
    return write(f"coverage/{t}.html", page(
        f"{t} — {c['name']} | ND Capital Research",
        md.strip_md(c["one_liner"], 155), 1, body, active="Coverage"))


def build_themes(themes, research, cov, by_ticker):
    ts = themes["themes"]
    body = f"""
<div class="page-head">
  <div class="wrap">
    <div class="kicker">The industry map</div>
    <h1>Themes</h1>
    <p class="lede">Where each theme sits in its lifecycle, where the profit pool actually accrues, who the
      second-order beneficiaries are — and the bear case for the theme itself, argued at full strength.</p>
  </div>
</div>
<section>
  <div class="wrap">
    <div class="note-box rv" style="margin-bottom:30px;">
      <strong>Why lifecycle stage leads every theme page.</strong> Most money lost in thematic investing is lost
      by arriving at "Crowded" and believing it is "Emerging." We state the stage first, with the evidence for
      that staging, before anything else.
    </div>
    <div class="grid grid-2">
      {''.join(f'''<a class="card ins-card hoverable rv rv-d{min(i%4+1,4)}" href="{t["slug"]}.html">
        <div class="cat">{t["stage"]}</div><h3>{t["name"]}</h3><p>{t["blurb"]}</p>
        <span class="read">{len(t["tickers"])} covered name{"s" if len(t["tickers"])!=1 else ""}</span></a>'''
        for i, t in enumerate(ts))}
    </div>
  </div>
</section>
"""
    out = [write("themes/index.html", page(
        "Themes — ND Capital", "Technology investment themes with lifecycle staging, profit pool mapping and bear cases.",
        1, body, active="Themes"))]

    cov_map = {c["ticker"]: c for c in cov["companies"]}
    for t in ts:
        r = research.get(t["slug"])
        secs = r["sections"] if r else []
        sm = {re.sub(r"^\d+\s*·\s*", "", k).strip(): v for k, v in secs}

        def s(name):
            for k, v in sm.items():
                if k.lower().startswith(name.lower()):
                    return v
            return ""

        members = [cov_map[tk] for tk in t["tickers"] if tk in cov_map]
        related = []
        seen = set()
        for tk in t["tickers"]:
            for p in by_ticker.get(tk, []):
                if p["slug"] not in seen:
                    seen.add(p["slug"])
                    related.append(p)
        related.sort(key=lambda p: p["date"], reverse=True)

        def acc(title, content, open_=False):
            if not content.strip():
                return ""
            return (f'<details class="acc"{" open" if open_ else ""}><summary>{title}</summary>'
                    f'<div class="body prose">{md.render(content)}</div></details>')

        tbody = f"""
<div class="page-head">
  <div class="wrap">
    <div class="crumbs"><a href="../index.html">Home</a> / <a href="./">Themes</a> / {t['name']}</div>
    <h1>{t['name']}</h1>
    <p class="lede">{t['blurb']}</p>
    <div class="pill-row" style="margin-top:20px;"><span class="chip chip-n">Stage · {t['stage']}</span></div>
  </div>
</div>

<section class="tight">
  <div class="wrap-narrow">
    <div class="prose rv">{md.render(s("The theme in three sentences"))}</div>
  </div>
</section>

<section class="sec-alt tight">
  <div class="wrap-narrow">
    <div class="sec-head rv" style="margin-bottom:24px;">
      <div class="kicker">Be honest about lateness</div><h2>Where we are in the lifecycle</h2></div>
    <div class="prose rv rv-d1">{md.render(s("Where we are in the lifecycle"))}</div>
  </div>
</section>

<section class="tight">
  <div class="wrap">
    <div class="sec-head rv"><div class="kicker">Coverage</div><h2>Names in this theme</h2></div>
    <div class="grid grid-3 rv rv-d1">
      {''.join(cov_card(c, 1) for c in members) or '<p class="dim">No covered names yet.</p>'}
    </div>
  </div>
</section>

<section class="sec-alt tight">
  <div class="wrap">
    <div class="sec-head rv"><div class="kicker">The full theme work</div><h2>Profit pool, winners, losers, bear case</h2></div>
    <div class="rv rv-d1">
      {acc("The profit pool — where the money actually accrues", s("The profit pool"), True)}
      {acc("Winners", s("Winners"))}
      {acc("Losers / disintermediated", s("Losers"))}
      {acc("Second- and third-order beneficiaries", s("Second-"))}
      {acc("What the market is rewarding right now", s("What the market is rewarding"))}
      {acc("The bear case for the theme itself", s("The bear case"))}
      {acc("Catalysts", s("Catalysts for the theme"))}
      {acc("ETF expressions", s("ETF expressions"))}
    </div>
  </div>
</section>

<section class="tight">
  <div class="wrap">
    <div class="sec-head rv"><div class="kicker">Related</div><h2>Published on this theme</h2></div>
    <div class="rv rv-d1">{feed_list(related, 1, limit=10, empty="Nothing published on this theme yet.")}</div>
  </div>
</section>
"""
        out.append(write(f"themes/{t['slug']}.html", page(
            f"{t['name']} — ND Capital Themes", md.strip_md(t["blurb"], 155), 1, tbody, active="Themes")))
    return out


def build_pubs(pubs, kind, folder, title, kicker, lede, active):
    items = [p for p in pubs if p["kind"] == kind]
    body = f"""
<div class="page-head">
  <div class="wrap">
    <div class="kicker">{kicker}</div>
    <h1>{title}</h1>
    <p class="lede">{lede}</p>
  </div>
</div>
<section>
  <div class="wrap">
    <div class="rv">{feed_list(items, 1)}</div>
  </div>
</section>
"""
    out = [write(f"{folder}/index.html", page(f"{title} — ND Capital", lede, 1, body, active=active))]

    for i, p in enumerate(items):
        prev_ = items[i + 1] if i + 1 < len(items) else None
        next_ = items[i - 1] if i > 0 else None
        tick_links = "".join(
            f'<a class="tag" href="../coverage/{tk}.html">{tk}</a>' for tk in p["tickers"])
        nav = []
        if next_:
            nav.append(f'<a class="btn btn-line btn-sm" href="{next_["slug"]}.html">← Newer</a>')
        if prev_:
            nav.append(f'<a class="btn btn-line btn-sm" href="{prev_["slug"]}.html">Older →</a>')

        pbody = f"""
<div class="page-head">
  <div class="wrap-narrow">
    <div class="crumbs"><a href="../index.html">Home</a> / <a href="./">{title}</a> / {nice_date(p['date'])}</div>
    <div class="kicker">{nice_date(p['date'])} · {p['category']}{f" · {p['reading_time']} min read" if p.get('reading_time') else ''}</div>
    <h1>{p['title']}</h1>
    {f'<p class="lede">{p["subtitle"]}</p>' if p['subtitle'] else ''}
  </div>
</div>
<section class="tight">
  <div class="wrap-narrow">
    {f'<div class="pill-row rv" style="margin-bottom:30px;">{tick_links}</div>' if tick_links else ''}
    <article class="prose rv rv-d1">{md.render(p['body'])}</article>
    <div class="flex-between" style="margin-top:50px;padding-top:26px;border-top:1px solid var(--line);">
      <div class="pill-row">{''.join(f'<span class="tag">{t}</span>' for t in p['tags'])}</div>
      <div class="pill-row">{''.join(nav)}</div>
    </div>
  </div>
</section>
"""
        out.append(write(f"{folder}/{p['slug']}.html", page(
            f"{p['title']} — ND Capital", md.strip_md(p["summary"], 155), 1, pbody, active=active)))
    return out


def build_methodology(cov, themes):
    body = f"""
<div class="page-head">
  <div class="wrap">
    <div class="kicker">How we work</div>
    <h1>Methodology</h1>
    <p class="lede">What we do, what we refuse to do, and where our analysis is currently incomplete —
      stated rather than hidden.</p>
  </div>
</div>

<section class="tight">
  <div class="wrap-narrow prose rv">
    <h2>What this is</h2>
    <p>ND Capital is an AI-assisted equity research platform covering the technology sector. It exists to
      <strong>learn about markets and to build research infrastructure that improves over time</strong> — not to
      sell investment advice. Everything here is published for education and research. Nothing on this site is
      a recommendation, and no one at ND Capital is a licensed investment adviser.</p>

    <h2>The standing principles</h2>
    <p>Every analysis is written against a fixed set of questions. The full text lives in the research
      repository; the ones that shape what you read on this site are:</p>
    <ul>
      <li><strong>Go beyond the screener.</strong> If an analysis contains only what could be read off a
        screener, it has failed. The edge, if there is one, is in management behaviour over time, in what
        investors are positioned for, and in where a theme sits in its lifecycle.</li>
      <li><strong>Objectivity is unconditional.</strong> The bear case is argued at full strength, by someone
        who wants it to win. "We have no edge here" is a valid and valuable conclusion — eight of our
        {len(cov['companies'])} names are rated Neutral for exactly that reason.</li>
      <li><strong>Momentum is a first-class force.</strong> A company with perfect fundamentals whose stock the
        market has decided to dislike will not go up. We analyse price action alongside fundamentals and let
        neither silently override the other.</li>
      <li><strong>Expectations beat fundamentals.</strong> A beat is only a beat relative to what was priced in.
        Every note answers: what specifically does this stock need to do to go up?</li>
      <li><strong>A multiple is a question, not an answer.</strong> Every valuation is reverse-engineered into a
        concrete operational requirement — what revenue, what margin, over what period.</li>
      <li><strong>Confidence must be proportional to evidence.</strong> Where it is not, we say so.</li>
    </ul>

    <h2>How a rating is built</h2>
    <ol>
      <li><strong>Data.</strong> Market data and fundamentals are pulled from a third-party vendor and stored
        with a timestamp. Nothing is hand-typed.</li>
      <li><strong>Judgement.</strong> The analysis is written separately from the data, so refreshing prices can
        never silently change an argument and editing an argument can never leave a stale number.</li>
      <li><strong>Scenarios.</strong> Bear, base and bull, each with a probability and a plain statement of what
        has to be true. The probability-weighted value informs the target — and where a distribution is
        genuinely bimodal, we say the weighted average is meaningless rather than publishing it as if it were
        a forecast.</li>
      <li><strong>Disconfirming evidence.</strong> Every note lists what would prove it wrong, specifically
        enough to be monitored. Deciding this <em>before</em> the outcome is known is what makes it a process
        rather than an opinion.</li>
      <li><strong>Publication.</strong> The site is regenerated from the research files. What you read is the
        research, not a marketing summary of it.</li>
    </ol>

    <h2>What "target price" means here</h2>
    <p>The rating expresses risk/reward over roughly twelve months. The target is our own valuation. These are
      separate judgements and they frequently disagree with each other and with the street — we hold several
      Overweight ratings with targets <em>below</em> consensus. That is deliberate: a rating that is really just
      a restatement of the target adds nothing, and a target marked to the consensus adds less.</p>

    <h2>Where our analysis is currently incomplete</h2>
    <p>Stating this plainly is part of the method. As of this initiation:</p>
    <ul>
      <li><strong>Guidance track records are not built.</strong> Our standards require an eight-to-twelve quarter
        guided-versus-delivered series and a quantified "sandbag factor" for every name. We do not have it yet,
        so no note assigns one. Management sections say what is observable and flag the gap.</li>
      <li><strong>Alternative data is not instrumented.</strong> Sentiment and positioning commentary is inferred
        from public reporting rather than measured. It is labelled as such and carries no weight in any rating.</li>
      <li><strong>One name has no price target.</strong> SK hynix is covered on the strength of its HBM position,
        but our data vendor does not cover the Korean listing on the current plan. We publish the thesis and
        withhold the valuation rather than fabricate one.</li>
      <li><strong>No track record exists yet.</strong> Coverage was initiated on 2 August 2026. There is nothing
        to show, and we will not present hypothetical performance as if it were real.</li>
    </ul>

    <h2>Hard limits</h2>
    <ul>
      <li>No material non-public information. No sourcing from insiders. Ever.</li>
      <li>No paywall circumvention — freely accessible sources only.</li>
      <li>Illustrative or unverified figures are always labelled as such.</li>
      <li>Indicative prices shown on this site are derived from vendor multiples, not exchange prints, and are
        labelled everywhere they appear.</li>
      <li>No agent trades, moves money or touches execution.</li>
    </ul>

    <h2>Data sources</h2>
    <p>Market data and company fundamentals: Alpha Vantage. Macro and industry context: public reporting, cited
      and dated in-line within each note. Company filings: primary sources. Where a figure comes from a
      secondary source, the note says so.</p>
  </div>
</section>
"""
    return write("methodology.html", page(
        "Methodology — ND Capital", "How ND Capital builds a rating, and where the analysis is currently incomplete.",
        0, body, active="Methodology"))


def build_track_record(cov, bets, earn):
    cs = cov["companies"]
    s = bets["summary"]
    dist = bets["distribution"]
    rows = "".join(f"""<tr>
  <td><a class="tick" href="coverage/{c['ticker']}.html">{c['ticker']}</a></td>
  <td>{chip(c['rating'])}</td>
  <td class="num">{money(c['price'])}</td>
  <td class="num">{money(c['target'],0) if c['target'] else '<span class="dim">n/a</span>'}</td>
  <td class="num">{updown(c['upside'])}</td>
  <td>{c['conviction']}</td>
  <td class="dim">{nice_date(c['last_review'])}</td>
  <td class="dim">Open</td>
</tr>""" for c in cs)

    body = f"""
<div class="page-head">
  <div class="wrap">
    <div class="kicker">Full transparency</div>
    <h1>Track record</h1>
    <p class="lede">Every call we make is logged here with the date it was made — and scored later on both the
      outcome and the reasoning. The losses will be published alongside the wins.</p>
  </div>
</div>

<section class="tight">
  <div class="wrap">
    <div class="note-box rv" style="margin-bottom:30px;">
      <strong>There is no performance to report yet, and we are not going to invent any.</strong>
      Coverage was initiated on {nice_date(cov.get('as_of'))}. The table below is the opening position of the
      record — {len(cs)} calls, each with a target and a review date. Hit rate, calibration and average return
      will appear here once there are outcomes to measure, including the ones that go against us. Any site
      showing a track record on day one is showing you a backtest.
    </div>

    <div class="stats rv rv-d1" style="margin-bottom:16px;">
      <div class="card stat"><div class="v">{s['open_calls']}</div><div class="k">Open calls</div></div>
      <div class="card stat"><div class="v">{s['resolved']}</div><div class="k">Resolved</div></div>
      <div class="card stat"><div class="v" style="color:var(--red);">{s['wrong']}</div><div class="k">Losses</div></div>
      <div class="card stat"><div class="v">—</div><div class="k">Hit rate</div></div>
      <div class="card stat"><div class="v">—</div><div class="k">Calibration score</div></div>
    </div>
    <p class="dim small rv" style="margin-bottom:30px;">
      Hit rate and calibration are <strong>null, not withheld</strong> — no call has reached its evaluation
      date. First scheduled review: 1 November 2026. The losses counter is on this page permanently, in the
      same row as everything else, so that it can never quietly be the one number that fails to render.</p>

    <div class="grid grid-2 rv rv-d1" style="margin-bottom:30px;">
      <div class="card" style="padding:26px 28px;">
        <div class="kicker" style="margin-bottom:14px;">Calls by rating</div>
        <table style="font-size:14px;"><tbody>
          <tr><td>Overweight</td><td class="num"><b>{dist['by_rating']['Overweight']}</b></td></tr>
          <tr><td>Neutral</td><td class="num"><b>{dist['by_rating']['Neutral']}</b></td></tr>
          <tr><td>Underweight</td><td class="num"><b>{dist['by_rating']['Underweight']}</b></td></tr>
        </tbody></table>
      </div>
      <div class="card" style="padding:26px 28px;">
        <div class="kicker" style="margin-bottom:14px;">Calls by conviction</div>
        <table style="font-size:14px;"><tbody>
          <tr><td>High</td><td class="num"><b>{dist['by_conviction']['High']}</b></td></tr>
          <tr><td>Medium</td><td class="num"><b>{dist['by_conviction']['Medium']}</b></td></tr>
          <tr><td>Low</td><td class="num"><b>{dist['by_conviction']['Low']}</b></td></tr>
        </tbody></table>
        <p class="dim small" style="margin-top:12px;">Recorded now so that the conviction label can be tested
          later: high-conviction calls must beat the overall hit rate, or the label carries no information.</p>
      </div>
    </div>

    <div class="card rv rv-d2">
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Ticker</th><th>Rating</th><th class="num">Price at initiation*</th>
            <th class="num">Target</th><th class="num">Implied</th><th>Conviction</th>
            <th>Initiated</th><th>Status</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    <p class="dim small" style="margin-top:14px;">
      * Indicative price derived from vendor trailing P/E × TTM diluted EPS — not an exchange print.</p>
  </div>
</section>

<section class="tight">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">Resolved calls</div>
      <h2>The losses, alongside the wins</h2>
      <p>When a call reaches its evaluation date it moves here — scored on the outcome and, separately,
         on whether the reasoning was sound. Nothing is removed from this table.</p>
    </div>
    <div class="card rv rv-d1" style="padding:44px;text-align:center;">
      <p class="dim">No call has resolved yet. This table is empty because coverage is
        { (datetime.strptime(BUILT[:10], "%Y-%m-%d") - datetime.strptime(str(cov.get('as_of'))[:10], "%Y-%m-%d")).days }
        day(s) old — not because the losses have been filtered out. There is no view of this page that
        shows wins without showing losses.</p>
    </div>
  </div>
</section>

<section class="tight">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">Next test of the record</div>
      <h2>Where the calls get marked</h2>
      <p>Confirmed reporting dates for covered names, with the earnings risk we assigned before the event.</p>
    </div>
    <div class="card table-card rv rv-d1">
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Date</th><th>Ticker</th><th>Our rating</th><th>Conviction</th>
            <th>Earnings risk</th><th class="num">Consensus EPS</th></tr></thead>
          <tbody>{''.join(f'''<tr>
            <td>{nice_date(e["report_date"])}</td>
            <td><a class="tick" href="coverage/{e["ticker"]}.html">{e["ticker"]}</a></td>
            <td>{chip(e["our_rating"])}</td><td>{e.get("conviction") or "—"}</td>
            <td>{risk_chip(e.get("our_earnings_risk"))}</td>
            <td class="num">{f'${e["consensus_eps"]:.2f}' if e.get("consensus_eps") else '—'}</td>
          </tr>''' for e in earn["upcoming"])}</tbody>
        </table>
      </div>
    </div>
    <p class="dim small" style="margin-top:14px;">
      {earn["unconfirmed_count"]} further coverage names have no confirmed date — our market-data plan is
      capped at 25 requests a day. We publish the gap rather than an estimate dressed up as a schedule.</p>
  </div>
</section>

<section class="sec-alt tight">
  <div class="wrap-narrow prose rv">
    <h2>How we will score this</h2>
    <p>Two scores, kept separate, because they measure different things:</p>
    <ul>
      <li><strong>Outcome.</strong> Did the price go where we said, over the horizon we said?</li>
      <li><strong>Reasoning.</strong> Was the argument correct, independent of the outcome? A right answer from
        wrong logic is recorded as a <em>failure</em>, because it will not repeat. A wrong answer from sound
        logic against an unforeseeable event is recorded as such.</li>
    </ul>
    <p>We will also score <strong>calibration</strong>: when we say 30% probability, does it happen roughly 30%
      of the time? Over enough calls that is a more honest measure of research quality than hit rate, which
      rewards making only safe predictions.</p>
    <p>Every rating carries a written list of what would prove it wrong. When one of those triggers prints, the
      change is published here and in the note's change log. <strong>Prior views are never deleted.</strong></p>
    <p>The full reasoning behind this scoring system — including why a right answer from flawed logic is
      recorded as a failure — is set out in
      <a href="insights/scoring-your-own-calls.html">How to Score Your Own Calls</a>.</p>

    <h2>Known gaps in this record</h2>
    <p>Stated here rather than discovered later:</p>
    <ul>
      <li><strong>The scorecard workbook is not yet populated.</strong> The {len(cs)} calls above are live and
        dated, but they have not been mirrored into the prediction workbook that Agent F1 scores from. Until
        they are, the monthly review has nothing to grade. Flagged ahead of the first review.</li>
      <li><strong>One name has no target.</strong> SK hynix is covered on its HBM position, but our data vendor
        does not cover the Korean listing on the current plan. The thesis is published and the valuation is
        withheld rather than fabricated — so it will be scored on the rating only.</li>
      <li><strong>No guidance track records.</strong> Our standards require an eight-to-twelve quarter
        guided-versus-delivered series per name. It is not built, so no rating leans on one.</li>
    </ul>
  </div>
</section>
"""
    return write("track-record.html", page(
        "Track Record — ND Capital", "Every call logged with its date, target and review status. Losses published alongside wins.",
        0, body, active="Track Record"))


# ============================================================ main

def main():
    cov = load_json("coverage.json")
    themes_j = load_json("themes.json")
    fund = load_json("fundamentals.json")["companies"]
    bets = load_json("bets.json")
    earn = load_json("earnings.json")
    pubs, by_ticker = load_publications()
    companies_r, themes_r = load_research()

    written = []
    written.append(build_home(cov, themes_j, pubs, fund, earn))
    written.append(build_coverage_index(cov, themes_j))
    for c in cov["companies"]:
        written.append(build_stock_page(c, companies_r, by_ticker, themes_j, fund))
    written += build_themes(themes_j, themes_r, cov, by_ticker)
    written += build_pubs(pubs, "brief", "briefs", "Morning Briefs", "Every morning, before the open",
                          "What moved overnight, what matters today, and how it changes the book.", "Briefs")
    written += build_pubs(pubs, "insight", "insights", "Insights", "Learn with us",
                          "Long-form research and methodology, written to teach the method rather than sell a view.",
                          "Insights")
    written.append(build_methodology(cov, themes_j))
    written.append(build_track_record(cov, bets, earn))

    # sitemap + robots
    write("sitemap.txt", "\n".join(sorted(w for w in written if w.endswith(".html"))))
    write("robots.txt", "User-agent: *\nAllow: /\n")

    fid = CFG.get("formspree_id", "").strip()
    print(f"Built {len(written)} pages.")
    print(f"  coverage : {len(cov['companies'])} stock pages")
    print(f"  themes   : {len(themes_j['themes'])} theme pages")
    print(f"  briefs   : {len([p for p in pubs if p['kind']=='brief'])}")
    print(f"  insights : {len([p for p in pubs if p['kind']=='insight'])}")
    if not fid:
        print("\n  ! Newsletter NOT live — add your Formspree form ID to website/config.json")
    else:
        print(f"\n  Newsletter live via Formspree ({fid}).")


if __name__ == "__main__":
    main()
