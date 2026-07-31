# ND Capital — Website

Static site, no build step. Open `index.html` in a browser to preview locally.

## Folder structure

- `index.html` — the site (single file: HTML + CSS + JS)
- `assets/` — logos (PNG + SVG), from Brand Identity/Final v2
- `data/` — JSON files the research agents will publish into:
  - `brief.json` — the daily morning brief
  - `bets.json` — the transparent bets tracker
  - `earnings.json` — the weekly earnings calendar
  - `coverage.json` — equity research coverage cards
  - These aren't wired into the page yet — `index.html` currently shows
    static placeholder content in these sections. Next step once the
    research agents are running: have the page `fetch()` these JSON files
    instead, so publishing new research is just an agent writing a file here.
- `insights/` — long-form research articles/deep-dives will live here.

## Publishing to the web (GitHub Pages, free)

Claude's sandbox has no general internet access, so publishing has to happen
from your own computer. Easiest path — no command line needed:

1. **Create the repo.** Go to github.com → New repository → name it
   `nd-capital` (or anything) → keep it **Public** (required for free GitHub
   Pages) → Create repository. Don't add a README/gitignore — leave it empty.
2. **Install GitHub Desktop** (free): https://desktop.github.com — sign in
   with your GitHub account.
3. **Add this folder as the local repo.** In GitHub Desktop: File → Add local
   repository → point it at this `website` folder. It'll offer to initialize
   git here — accept.
4. **Publish.** Enter a commit message like "Initial site" → Commit to main
   → Publish repository (make sure "Keep this code private" is unchecked) →
   push to the GitHub repo you created in step 1 (set it as the remote if
   asked).
5. **Turn on Pages.** On github.com, open the repo → Settings → Pages →
   under "Build and deployment", Source: "Deploy from a branch" → Branch:
   `main`, folder `/ (root)` → Save. GitHub gives you a live URL within a
   minute or two, typically `https://<your-username>.github.io/nd-capital/`.

## Updating after today

Claude edits the files in this folder directly (same as always). To publish
a change: open GitHub Desktop, it'll show the changed files, write a commit
message, hit "Commit to main", then "Push origin". The live site updates in
under a minute. No need to repeat the setup steps above.

Once the research agents are wired up to write into `data/`, the same flow
applies — Claude writes the JSON, you push in GitHub Desktop (or we automate
that push later with a scheduled task, once we decide how).
