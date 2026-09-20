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

--------------------------------------------------------------------------
FIX (this version): Yahoo Finance began blocking requests from datacenter/
cloud IP ranges — including GitHub Actions runners — by fingerprinting the
TLS handshake of Python's default `requests`/urllib3 stack, independent of
any per-IP rate limit. Symptom: scheduled runs that worked for months start
failing outright (429/403) with no code change on our side. This is a
widely-reported yfinance + CI issue as of 2024-2026.

Fix: route requests through `curl_cffi`, which impersonates a real Chrome
TLS fingerprint, so Yahoo's edge treats it like an ordinary browser request
even though it's still running on a GitHub-hosted runner. This is the fix
the yfinance maintainers currently recommend for this exact failure mode.
If curl_cffi isn't installed, falls back to a plain requests session (the
old behavior) so this still runs somewhere that isn't blocked.
--------------------------------------------------------------------------

Runs server-side (GitHub Actions runner). Output is a same-origin data.json
the static page reads on load.
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

SHORTS = ["SH", "SDS", "SPXU", "SPXS", "PSQ", "SQQQ", "SDOW", "TZA"]
LONGS  = ["SSO", "UPRO", "SPXL", "QLD", "TQQQ", "UDOW", "TNA", "SOXL"]
SPX    = "^GSPC"
ALL    = [SPX] + SHORTS + LONGS

PERIOD   = "10y"
INTERVAL = "1wk"
MIN_LEG  = 4
MIN_ROWS = 100
MAX_RETRIES = 3


def make_session():
    """Prefer a curl_cffi session impersonating Chrome (bypasses Yahoo's
    TLS-fingerprint block on datacenter IPs). Falls back to plain requests
    if curl_cffi isn't available."""
    try:
        from curl_cffi import requests as cffi_requests
        print("Using curl_cffi session (Chrome impersonation).")
        return cffi_requests.Session(impersonate="chrome")
    except ImportError:
        print("WARNING: curl_cffi not installed — falling back to plain "
              "requests session. If Yahoo is blocking this runner's TLS "
              "fingerprint, this fallback will likely fail. "
              "Add 'curl_cffi' to requirements.txt to fix.", file=sys.stderr)
        return None


def download_with_retry(session):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = dict(
                tickers=ALL, period=PERIOD, interval=INTERVAL,
                auto_adjust=False, progress=False,
                group_by="ticker", threads=True,
            )
            if session is not None:
                kwargs["session"] = session
            df = yf.download(**kwargs)
            if df is not None and not df.empty:
                return df
            last_err = "empty DataFrame returned"
        except Exception as e:
            last_err = str(e)
        print(f"  attempt {attempt}/{MAX_RETRIES} failed: {last_err}", file=sys.stderr)
        if attempt < MAX_RETRIES:
            time.sleep(5 * attempt)
    raise RuntimeError(f"yf.download failed after {MAX_RETRIES} attempts: {last_err}")


def to_friday(ts) -> str:
    d = ts.to_pydatetime()
    fri = d + timedelta(days=(4 - d.weekday()))
    return fri.strftime("%Y-%m-%d")


def main() -> int:
    print(f"Downloading {len(ALL)} tickers, {PERIOD} {INTERVAL} ...")
    session = make_session()

    try:
        df = download_with_retry(session)
    except RuntimeError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        print("This almost always means Yahoo is blocking this runner "
              "(TLS fingerprint or IP-range block). See the comment at "
              "the top of this file for the curl_cffi fix.", file=sys.stderr)
        return 1

    vol, close = {}, {}
    missing = []
    for t in ALL:
        try:
            sub = df[t]
        except Exception:
            missing.append(t)
            continue
        if "Volume" in sub:
            vol[t] = sub["Volume"]
        if "Close" in sub:
            close[t] = sub["Close"]

    if missing:
        print(f"  warn: missing from download: {', '.join(missing)}")

    if SPX not in close:
        print("FATAL: S&P 500 (^GSPC) data missing", file=sys.stderr)
        return 1

    spx_close = close[SPX].dropna()
    rows = []
    for ts, spx_val in spx_close.items():
        if pd.isna(spx_val):
            continue
        s_dv = l_dv = 0.0
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

    by_date = {r["date"]: r for r in rows}
    rows = [by_date[d] for d in sorted(by_date)]

    if len(rows) < MIN_ROWS:
        print(f"FATAL: only {len(rows)} rows built (< {MIN_ROWS}) — "
              f"data looks incomplete, refusing to write data.json", file=sys.stderr)
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
