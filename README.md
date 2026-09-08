# Spec-Short Capitulation Index — auto-updating hosted dashboard

A recreation of the 3Fourteen Research / Warren Pies speculative-short ETF
volume indicator. The page is fully static; its data is refreshed
**server-side on a daily schedule** by a GitHub Action and read from
`data.json`. No browser-side market fetch, so there's no CORS or proxy
fragility — it just works wherever it's hosted, and it's genuinely current
every time you (or anyone) opens it, no open tab or manual step required.

## How it works

```
GitHub Action (daily cron, runs on GitHub's servers)
   └─ runs fetch_data.py
        └─ pulls 10y weekly data for SPX + 16 leveraged/inverse ETFs from Yahoo
        └─ computes  % Short = inverse $ volume / (long + inverse) $ volume
        └─ writes data.json, commits it to the repo
GitHub Pages serves index.html + data.json
   └─ browser loads ./data.json (same-origin → always works, no proxy needed)
```

`index.html` also embeds a snapshot as a fallback, so it renders instantly
and never shows a blank screen even before `data.json` loads.

## One-time setup (~10 minutes)

### 1. Create a GitHub account and repo
If you don't have a GitHub account, sign up free at github.com. Then click
the **+** icon (top-right) → **New repository**. Name it something like
`spec-short-index`, set it to **Public** (required for free GitHub Pages),
and click **Create repository**.

### 2. Upload the files
On the empty repo page, click **uploading an existing file** and drag in:
- `index.html`
- `data.json`
- `fetch_data.py`
- `requirements.txt`

The `.github/workflows/update.yml` file needs its folder structure
preserved. If GitHub's drag-and-drop flattens folders, instead click
**Add file → Create new file**, type the filename exactly as
`.github/workflows/update.yml` (GitHub will auto-create the folders),
and paste in its contents. Commit when done.

### 3. Allow the Action to commit data back to the repo
Go to **Settings → Actions → General**, scroll to **Workflow permissions**,
select **Read and write permissions**, and **Save**.
*(This is the single most common thing people miss — the workflow requests
write access, but this repo-level toggle must also be turned on, or every
run will fail silently to push.)*

### 4. Enable GitHub Pages
Go to **Settings → Pages**. Under *Build and deployment*, set:
- Source: **Deploy from a branch**
- Branch: **main** / **/(root)**
- Save

After a minute or two, your live URL appears at the top of that page:
`https://<your-username>.github.io/<repo-name>/`

### 5. Run the fetch once now (don't wait for the overnight schedule)
Go to the **Actions** tab → click **Update spec-short data** in the left
sidebar → **Run workflow** → **Run workflow** (green button).
It takes 1-2 minutes. A green checkmark means it fetched live data and
committed a fresh `data.json`.

That's it. Open your Pages URL — the status pill should read green **Live**
with the current date. From here on, it refreshes every day on its own.

## Verifying it worked

- **Green "Live" pill** + a recent date next to it = working correctly.
- **Slate "Baked data" pill** = `data.json` didn't load. Check, in order:
  1. Is GitHub Pages actually enabled (step 4)?
  2. Did the Action run succeed (green check under the **Actions** tab)?
  3. Does `data.json` exist at the repo root and look like real JSON
     (not an error page)?
- Opening `index.html` directly from your computer's file system
  (double-clicking it, `file://...`) will **always** show the baked
  snapshot — browsers block a local file from fetching another local file.
  You must view it via the `github.io` URL for the live version.

## Schedule & cost

- Runs daily at **22:00 UTC** (~6pm ET, after the US close). To change it,
  edit the `cron:` line in `.github/workflows/update.yml` — e.g.
  `0 13 * * *` runs at 9am ET instead.
- Each run takes about 1-2 minutes. GitHub's free tier includes 2,000
  Action-minutes/month; this uses roughly 3% of that.

### Two things worth knowing
- **GitHub pauses scheduled workflows after 60 days with no repo activity.**
  Any commit, or just clicking "Run workflow" once, re-arms it. If you're
  checking in on this dashboard at least every couple of months, you'll
  never notice this.
- **GitHub's cron scheduler is best-effort**, occasionally delayed by up to
  an hour under heavy load. Irrelevant for weekly data.

## Customizing

- **Basket / universe:** edit `SHORTS` / `LONGS` in `fetch_data.py`.
- **Signal thresholds:** edit `THRESHOLDS` near the top of the `<script>`
  block in `index.html`.
- **Run daily instead of weekly:** change `INTERVAL = "1wk"` to `"1d"` in
  `fetch_data.py` — the page's chart code handles daily bars too.
- **Different/more reliable data source:** `fetch_data.py` is the only file
  that touches market data. To swap `yfinance` for a keyed provider (Tiingo,
  Polygon, Financial Modeling Prep), rewrite its download section to emit
  the same `{date, spx, pct}` row shape — nothing else needs to change.

---

*Recreation for research/education. Not affiliated with or endorsed by
3Fourteen Research. Methodology inferred from Warren Pies' public
description (Excess Returns podcast, 2024) and calibrated against the
published chart. Past performance is not indicative of future results;
this is not investment advice.*
