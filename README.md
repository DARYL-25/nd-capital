# ND Capital — Website

A generated static site. No build tooling, no npm, no dependencies — just Python 3.8+.

```
python website/build.py
```

That regenerates all 46 pages into this folder. Open `index.html` in a browser to preview.

---

## Turn on the newsletter (2 minutes)

The subscribe form is on every page and wired, but it needs a place to send emails. Until you do
this, it shows a polite "not connected yet" message rather than silently losing addresses.

1. Go to **https://formspree.io** and sign up (free tier is fine).
2. Create a new form. Call it something like "ND Capital newsletter".
3. Formspree gives you an endpoint like `https://formspree.io/f/xayzbwqd`.
   **Copy only the last part** — `xayzbwqd`.
4. Open `website/config.json` and paste it in:

   ```json
   "formspree_id": "xayzbwqd",
   ```

5. Re-run `python website/build.py`.

Subscribers now land in your Formspree inbox and export to CSV. The form includes a hidden
honeypot field so most bot signups are dropped automatically.

**When the list gets big enough to actually send from**, move to Buttondown or MailerLite — they
handle sending, unsubscribe links and the legal requirements that come with a real mailing list.
Only `formspree_id` and the form `action` need to change.

---

## How the site gets its content

Nothing on the site is hand-written HTML. Three generators run in order:

```
python _System/write_research.py    # 24 company thesis files + coverage.json
python _System/write_themes.py      # 12 theme files + themes.json
python website/build.py             # the whole site
```

**The split that matters:** market data and judgement never live in the same file.

| File | Holds | Who edits it |
|---|---|---|
| `website/data/fundamentals.json` | vendor market data, timestamped | data pull only |
| `_System/research_data.py` + `_b.py` | the analysis — thesis, scenarios, catalysts | the analyst |
| `Research/Companies/<T>/00_THESIS.md` | the rendered research document | generated |
| `website/data/coverage.json` | structured ratings the site reads | generated |

So refreshing prices can never silently change an argument, and rewriting an argument can never
leave a stale number behind. Re-run `write_research.py` after any data pull and every snapshot,
multiples table and momentum read across all 24 names updates at once.

---

## Publishing a note

Drop a markdown file in `website/content/briefs/` or `website/content/insights/` with front matter:

```markdown
---
title: Micron — raising target after Q4
date: 2026-09-28
category: Rating Change
tickers: [MU, LRCX, SK-Hynix-000660]
tags: [Memory, Earnings]
summary: One sentence for the card on the insights page.
---

Body in normal markdown. Tables, bold, links, blockquotes and lists all work.
```

Then rebuild. **The `tickers:` line is the important one** — build.py inverts it into a per-stock
feed, so this note automatically appears in the "Research & updates" section of the MU, LRCX and
SK hynix pages. You never link anything by hand.

---

## Changing a rating

1. Edit the name in `_System/research_data.py` (or `_research_data_b.py`) — `rating`, `target`,
   `conviction`, plus the reasoning.
2. Add a row to that name's change log. **Never delete the prior view** — the record of being
   wrong is the most valuable data in the system.
3. Re-run all three generators.
4. Publish a note explaining the change, tagged with the ticker so it lands on the stock page.

---

## Folder map

```
website/
  build.py            the generator
  md.py               dependency-free markdown -> HTML
  config.json         site settings + Formspree ID + disclaimer
  assets/site.css     the entire design system — edit here to restyle
  assets/*.svg|png    logos
  content/briefs/     morning briefs (markdown)
  content/insights/   long-form articles (markdown)
  data/               fundamentals, coverage, themes (JSON)
  index.html          }
  coverage/           }
  themes/             }  all generated — do not edit by hand,
  briefs/             }  your changes will be overwritten
  insights/           }
  methodology.html    }
  track-record.html   }
```

---

## Publishing to the web (GitHub Pages, free)

One-time setup, no command line needed:

1. **Create the repo.** github.com → New repository → name it `nd-capital` → keep it **Public**
   (required for free Pages) → Create. Leave it empty.
2. **Install GitHub Desktop** (free): https://desktop.github.com — sign in.
3. **Add this folder.** File → Add local repository → point at this `website` folder → accept the
   offer to initialise git.
4. **Publish.** Commit message "Initial site" → Commit to main → Publish repository (make sure
   "Keep this code private" is **unchecked**).
5. **Turn on Pages.** On github.com: repo → Settings → Pages → Source "Deploy from a branch" →
   Branch `main`, folder `/ (root)` → Save. Live in a minute or two at
   `https://<your-username>.github.io/nd-capital/`.

**After that**, publishing a change is: run the generators → open GitHub Desktop → commit → push.
Live in under a minute.

---

## Known gaps

Stated here rather than hidden, and reflected on the Methodology page:

- **No guidance track records.** The research standards require an 8–12 quarter guided-vs-delivered
  series and a quantified sandbag factor per name. Not built — no note assigns one.
- **No alternative data.** Sentiment commentary is inferred from public reporting, not measured.
  Labelled as such everywhere and carries no weight in any rating.
- **SK hynix has no price target.** The data vendor doesn't cover KRX 000660 on the free plan.
  Thesis published, valuation withheld.
- **Market data is on a free Alpha Vantage key** — 25 requests/day, no bulk quotes, no real-time.
  A paid tier would allow a daily refresh of all 24 names plus the earnings calendar.
- **No track record yet.** Coverage was initiated 2 August 2026.
