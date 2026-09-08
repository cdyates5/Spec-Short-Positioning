#!/usr/bin/env python3
"""
fetch_data.py — builds data.json for the Spec-Short Capitulation Index.

Methodology:
    % Short = inverse-ETF DOLLAR volume
              -------------------------------------------------
              (leveraged-long + inverse) ETF DOLLAR volume        (weekly)

Dollar volume (shares x price) is used deliberately: raw share volume is
dominated by ultra-low-priced inverse funds (e.g. TZA near $4, which trades
300M+ shares/week purely because it's cheap), which distorts the ratio.
Dollar-weighting reproduces 3Fourteen Research's published band.

Runs server-side (GitHub Actions runner), so it reaches Yahoo Finance
directly — no CORS, no proxies. Output is a same-origin data.json the
static page reads on load.
"""

import json
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

# Speculative ETF universe (liquid proxy for the full leveraged/inverse space).
SHORTS = ["SH", "SDS", "SPXU", "SPXS", "PSQ", "SQQQ", "SDOW", "TZA"]
LONGS  = ["SSO", "UPRO", "SPXL", "QLD", "TQQQ", "UDOW", "TNA", "SOXL"]
SPX    = "^GSPC"
ALL    = [SPX] + SHORTS + LONGS

PERIOD   = "10y"
INTERVAL = "1wk"
MIN_LEG  = 4          # require >=4 of each leg present for a valid week
MIN_ROWS = 100        # sanity floor on output length


def to_friday(ts) -> str:
    """yfinance weekly bars are stamped at week-start (Mon); normalise to Fri."""
    d = ts.to_pydatetime()
    fri = d + timedelta(days=(4 - d.weekday()))
    return fri.strftime("%Y-%m-%d")


def main() -> int:
    print(f"Downloading {len(ALL)} tickers, {PERIOD} {INTERVAL} ...")
    df = yf.download(
        ALL, period=PERIOD, interval=INTERVAL,
        auto_adjust=False, progress=False,
        group_by="ticker", threads=True,
    )

    vol, close = {}, {}
    for t in ALL:
        try:
            sub = df[t]
        except Exception:
            print(f"  warn: {t} missing from download")
            continue
        if "Volume" in sub:
            vol[t] = sub["Volume"]
        if "Close" in sub:
            close[t] = sub["Close"]

    if SPX not in close:
        print("FATAL: S&P 500 (^GSPC) data missing", file=sys.stderr)
        return 1

    spx_close = close[SPX].dropna()
    rows = []
    for ts, spx_val in spx_close.items():
        if pd.isna(spx_val):
            continue
        s_dv = l_dv = 0.0   # dollar volume, not share volume
        s_n = l_n = 0
        for t in SHORTS:
            v, c = vol.get(t), close.get(t)
            if v is not None and c is not None and ts in v.index and ts in c.index \
               and pd.notna(v.loc[ts]) and pd.notna(c.loc[ts]):
                s_dv += float(v.loc[ts]) * float(c.loc[ts]); s_n += 1
        for t in LONGS:
            v, c = vol.get(t), close.get(t)
            if v is not None and c is not None and ts in v.index and ts in c.index \
               and pd.notna(v.loc[ts]) and pd.notna(c.loc[ts]):
                l_dv += float(v.loc[ts]) * float(c.loc[ts]); l_n += 1
        if s_n < MIN_LEG or l_n < MIN_LEG or (s_dv + l_dv) <= 0:
            continue
        rows.append({
            "date": to_friday(ts),
            "spx":  round(float(spx_val), 2),
            "pct":  round(s_dv / (s_dv + l_dv) * 100, 2),
        })

    # De-dup by date (keep last) and sort ascending.
    by_date = {r["date"]: r for r in rows}
    rows = [by_date[d] for d in sorted(by_date)]

    if len(rows) < MIN_ROWS:
        print(f"FATAL: only {len(rows)} rows built (< {MIN_ROWS})", file=sys.stderr)
        return 1

    out = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Yahoo Finance — weekly dollar volume (shares x price)",
        "methodology": "inverse $ vol / (long + inverse) $ vol",
        "tickers": {"shorts": SHORTS, "longs": LONGS},
        "data": rows,
    }
    with open("data.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))

    print(f"Wrote data.json: {len(rows)} weeks, "
          f"{rows[0]['date']} -> {rows[-1]['date']}, "
          f"latest %short = {rows[-1]['pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
