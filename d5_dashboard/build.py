"""D5 -- dashboard: a self-contained HTML snapshot of the price/OI regime board.

    python -m d5_dashboard --asof 2026-08-31

Reads only data/, writes only data/09_dashboard/.  No network, no service.
"Current" means the last bar of the dataset, not live data.
"""
from __future__ import annotations

import argparse
import base64
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LAB = DATA / "05_regime" / "regime_labels" / "freq=1h"
FEAT = DATA / "02_features" / "features_1h"
OID = DATA / "01_layer2" / "oi_1h"
FUND = DATA / "01_layer2" / "funding"
MEM = DATA / "03_reference" / "universe_membership.parquet"
BASE1 = DATA / "07_funding" / "base" / "p4_base_h=1.parquet"
OUT = DATA / "09_dashboard"

WINDOW_H = 24
VOL_LOOKBACK_D = 90
REGIMES = ("R1", "R2", "R3", "R4")
RNAME = {"R1": "long buildup", "R2": "short covering",
         "R3": "short buildup", "R4": "deleveraging"}
FNAME = {-1: "-", 0: "negative", 1: "neutral", 2: "high", 3: "extreme"}


def log(msg):
    print(msg, flush=True)


def _files(root, first, last):
    out = []
    for p in sorted(root.glob("year=*/chunk=*.parquet")):
        m = p.stem.replace("chunk=", "")
        if first <= m <= last:
            out.append(p)
    return out


def _month_of(bar):
    """The month chunk that a bar belongs to (bar start = ts_end - 1h)."""
    return (bar - pd.Timedelta(hours=1)).normalize().replace(day=1)


def _span(bar):
    first = (bar - pd.Timedelta(days=VOL_LOOKBACK_D + 10)).strftime("%Y-%m")
    last = _month_of(bar).strftime("%Y-%m")
    return first, last


def load_labels(first, last, as_of):
    cols = ["symbol", "ts_end", "regime", "price_change", "oi_change",
            "funding_negative", "funding_neutral", "funding_high", "funding_extreme",
            "funding_p25", "funding_p75", "funding_p90", "mkt_vol_state"]
    parts = []
    for p in _files(LAB, first, last):
        d = pd.read_parquet(p, columns=cols)
        parts.append(d[d.ts_end <= as_of])
    return pd.concat(parts, ignore_index=True)


def _series(root, cols, first, last, as_of):
    parts = []
    for p in _files(root, first, last):
        parts.append(pd.read_parquet(p, columns=cols))
    d = pd.concat(parts, ignore_index=True)
    return d[d.ts_end <= as_of]


def load_close(first, last, as_of):
    return _series(FEAT, ["symbol", "ts_end", "close"], first, last, as_of)


def load_oi(first, last, as_of):
    return _series(OID, ["symbol", "ts_end", "oi"], first, last, as_of)


def load_funding(first, last, as_of):
    parts = []
    for p in _files(FUND, first, last):
        parts.append(pd.read_parquet(p, columns=["symbol", "ts_funding", "funding_rate"]))
    d = pd.concat(parts, ignore_index=True)
    return d[d.ts_funding <= as_of]


# funding state -> the slice of the 0-1 axis that state owns
BAND = {0: (0.00, 0.25), 1: (0.25, 0.75), 2: (0.75, 0.90), 3: (0.90, 1.00)}


def funding_position(rate, p25, p75, p90, state):
    """Map the current rate onto 0-1, inside the band owned by its funding state.

    Funding rates are heavily discretised on Binance and p75 == p90 for ~70% of
    contracts at any hour, so a pure percentile map is undefined; the state
    (which already handles ties) picks the band and the percentiles only refine
    the position inside it.  Degenerate bands collapse to their midpoint.
    """
    if state not in BAND:
        return float("nan")
    lo_b, hi_b = BAND[state]
    if not all(np.isfinite(x) for x in (rate, p25, p75, p90)):
        return 0.5 * (lo_b + hi_b)
    if state == 0:
        a = 2.0 * p25 if p25 < 0 else 0.0
        b = p25
    elif state == 1:
        a, b = p25, p75
    elif state == 2:
        a, b = p75, p90
    else:
        a = p90
        b = p90 + max(abs(p90), 1e-9)
    if b - a <= 1e-12:
        return 0.5 * (lo_b + hi_b)
    t = float(np.clip((rate - a) / (b - a), 0.0, 1.0))
    return lo_b + (hi_b - lo_b) * t


def build_board(as_of, labels, close, oi, funding, mem):
    mkey = _month_of(as_of).strftime("%Y-%m")
    uni = mem[mem.month == mkey].sort_values("rank")
    syms = list(uni.symbol)
    rank_of = dict(zip(uni.symbol, uni["rank"]))

    sub = labels[labels.symbol.isin(syms)]
    start = as_of - pd.Timedelta(hours=WINDOW_H)
    win = sub[(sub.ts_end >= start) & sub.regime.isin(REGIMES)]
    latest = win.sort_values("ts_end").groupby(["symbol", "regime"]).tail(1)
    latest = latest.set_index(["symbol", "regime"])

    snap = sub[sub.ts_end == as_of].set_index("symbol")

    o = oi[oi.symbol.isin(syms)].sort_values(["symbol", "ts_end"])
    o["oi24"] = o.groupby("symbol")["oi"].pct_change(24, fill_method=None)
    oi_now = o[o.ts_end == as_of].set_index("symbol")["oi24"]

    f = funding[funding.symbol.isin(syms)].sort_values(["symbol", "ts_funding"])
    frate = f.groupby("symbol")["funding_rate"].last()

    c = close[close.symbol.isin(syms)].sort_values(["symbol", "ts_end"])
    c["r"] = np.log(c.groupby("symbol")["close"].pct_change().add(1.0))
    c["v24"] = c.groupby("symbol")["r"].transform(
        lambda s: s.rolling(24, min_periods=18).std())
    vpct = {}
    for sym, g in c.groupby("symbol"):
        v = g["v24"].dropna()
        if len(v) >= 100:
            vpct[sym] = float((v < v.iloc[-1]).mean())

    rows = []
    for sym in syms:
        rec = {"rank": int(rank_of[sym]), "symbol": sym}
        fresh = {}
        for rg in REGIMES:
            try:
                row = latest.loc[(sym, rg)]
            except KeyError:
                rec["age_" + rg] = np.nan
                rec["pc_" + rg] = np.nan
                rec["oc_" + rg] = np.nan
                continue
            age = float((as_of - row["ts_end"]).total_seconds() / 3600.0)
            rec["age_" + rg] = age
            rec["pc_" + rg] = float(row["price_change"])
            rec["oc_" + rg] = float(row["oi_change"])
            fresh[rg] = age
        if fresh:
            rg = min(fresh, key=fresh.get)
            rec["last"] = rg
            rec["age"] = fresh[rg]
            rec["price_chg"] = rec["pc_" + rg]
            rec["oi_chg"] = rec["oc_" + rg]
        else:
            rec["last"] = "-"
            rec["age"] = np.nan
            rec["price_chg"] = np.nan
            rec["oi_chg"] = np.nan

        if sym in snap.index:
            s = snap.loc[sym]
            code = -1
            for key, val in (("funding_negative", 0), ("funding_neutral", 1),
                             ("funding_high", 2), ("funding_extreme", 3)):
                if bool(s[key]):
                    code = val
            rec["funding"] = code
            rec["funding_pct"] = funding_position(
                float(frate.get(sym, np.nan)), float(s["funding_p25"]),
                float(s["funding_p75"]), float(s["funding_p90"]), code)
            rec["mkt_vol"] = str(s["mkt_vol_state"])
        else:
            rec["funding"] = -1
            rec["funding_pct"] = np.nan
            rec["mkt_vol"] = "unknown"

        rec["oi_24h"] = float(oi_now.get(sym, np.nan))
        rec["vol_pct"] = float(vpct.get(sym, np.nan))
        rows.append(rec)

    df = pd.DataFrame(rows)
    df["vol_rank"] = df["vol_pct"].rank(ascending=False, method="min")
    df["fund_rank"] = df["funding_pct"].rank(ascending=False, method="min")
    return df.sort_values("rank").reset_index(drop=True)


CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:28px auto;max-width:1180px;color:#1a202c}
h1{font-size:21px;margin:0 0 2px}
h2{font-size:15px;margin:26px 0 8px;border-bottom:1px solid #e2e8f0;padding-bottom:4px}
.sub{color:#4a5568;font-size:12.5px;margin-bottom:14px;line-height:1.7}
table{border-collapse:collapse;font-size:12px;width:100%}
th,td{padding:4px 9px;border-bottom:1px solid #edf2f7;text-align:right}
th{background:#f7fafc;font-weight:600}
td.l,th.l{text-align:left}
.tag{font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:1px 5px;border-radius:3px}
.r1{background:#c6f6d5;color:#22543d}
.r3{background:#fed7d7;color:#742a2a}
.r4{background:#e2e8f0;color:#2d3748}
.r2{background:#fefcbf;color:#744210}
.none{color:#a0aec0}
footer{margin-top:34px;font-size:11px;color:#718096;line-height:1.7;border-top:1px solid #e2e8f0;padding-top:12px}
img{max-width:100%;border:1px solid #e2e8f0;margin-top:6px}
"""

COLS = ["rank", "symbol", "last", "age", "price_chg", "oi_chg", "funding", "vol_pct"]
HEAD = ["#", "contract", "last state", "age", "price chg", "OI chg", "funding", "vol pctile"]


def cell(col, v):
    if col.startswith("age_"):
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%.0fh</td>" % v
    if col.startswith("pc_"):
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%+.0f bp</td>" % (v * 1e4)
    if col.startswith("oc_"):
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%+.1f%%</td>" % (v * 100)
    if col == "rank":
        return "<td>%d</td>" % int(v)
    if col == "symbol":
        return "<td class='l'><b>%s</b></td>" % v
    if col == "last":
        if v == "-":
            return "<td class='l none'>-</td>"
        return "<td class='l'><span class='tag %s'>%s</span></td>" % (str(v).lower(), v)
    if col == "age":
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%.0fh</td>" % v
    if col == "price_chg":
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%+.0f bp</td>" % (v * 1e4)
    if col == "oi_chg":
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%+.1f%%</td>" % (v * 100)
    if col == "funding":
        return "<td>%s</td>" % FNAME.get(int(v) if np.isfinite(v) else -1, "-")
    if col == "vol_pct":
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%.0f%%</td>" % (v * 100)
    if col == "oi_24h":
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%+.1f%%</td>" % (v * 100)
    if col == "funding_pct":
        return "<td class='none'>-</td>" if not np.isfinite(v) else "<td>%.2f</td>" % v
    return "<td>%s</td>" % v


def table(df, cols=None, head=None):
    cols = cols or COLS
    head = head or HEAD
    out = ["<table><tr>" + "".join(
        "<th class='l'>%s</th>" % h if c in ("symbol", "last") else "<th>%s</th>" % h
        for c, h in zip(cols, head)) + "</tr>"]
    for _, r in df.iterrows():
        out.append("<tr>" + "".join(cell(c, r[c]) for c in cols) + "</tr>")
    out.append("</table>")
    return "".join(out)


def fig_crowding(df):
    d = df.dropna(subset=["funding_pct", "oi_24h"])
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    ax.scatter(d["funding_pct"], d["oi_24h"] * 100, c=d["fund_rank"],
               cmap="viridis_r", s=30, edgecolor="white", linewidth=0.6)
    ax.axhline(0, color="k", lw=0.8)
    ax.axvline(0.75, color="k", ls="--", lw=0.9, alpha=0.55)
    ax.set_xlabel("funding percentile (contract's own 90d history)")
    ax.set_ylabel("24h OI change (%)")
    ax.set_title("Crowding: funding vs open-interest change")
    lab = pd.concat([d.nlargest(3, "oi_24h"), d.nlargest(3, "funding_pct")]).drop_duplicates("symbol")
    for _, r in lab.iterrows():
        ax.annotate(r["symbol"], (r["funding_pct"], r["oi_24h"] * 100),
                    fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def render(df, as_of, n_ev, mkt_vol):
    a1 = df[df["age_R1"].notna()]
    a3 = df[df["age_R3"].notna()]
    a4 = df[df["age_R4"].notna()]
    crowd = df.dropna(subset=["funding_pct", "oi_24h"])
    ext = crowd[crowd["funding"].isin([2, 3]) & (crowd["oi_24h"] > 0)]
    ext = ext.sort_values("funding_pct", ascending=False).head(10)
    vol = df.dropna(subset=["vol_pct"]).sort_values("vol_pct", ascending=False)

    h = []
    h.append("<!doctype html><html><head><meta charset='utf-8'>")
    h.append("<title>Price/OI Regime Board - %s</title>" % as_of.strftime("%Y-%m-%d"))
    h.append("<style>%s</style></head><body>" % CSS)
    h.append("<h1>Price / Open-Interest Regime Board</h1>")
    h.append("<div class='sub'><b>Data as of %s UTC</b> (dataset end - not live). "
             "Universe: top %d contracts by liquidity, ranked 1..%d. "
             "Market volatility regime: <b>%s</b>. "
             "Contracts with at least one regime in the last %dh: <b>%d / %d</b>.</div>"
             % (as_of.strftime("%Y-%m-%d %H:%M"), len(df), len(df), mkt_vol, WINDOW_H, n_ev, len(df)))

    h.append("<h2>1. Master table (all %d, by liquidity rank)</h2>" % len(df))
    h.append("<div class='sub'>Each row is one contract; <b>last state</b> is the most recent "
             "regime within the window and <b>age</b> is how long ago it happened. "
             "Contracts with nothing in the last %dh show <span class='none'>-</span>.</div>" % WINDOW_H)
    h.append(table(df))

    for title, sub, d, rg in (
            ("2. Long buildup (R1: price up + OI up)",
             "Price and open interest both above their rolling 90d thresholds.", a1, "R1"),
            ("3. Short buildup (R3: price down + OI up)",
             "Price below its threshold with open interest above its own.", a3, "R3"),
            ("4. Deleveraging (R4: price down + OI down)",
             "Open interest contracting while price falls - the note's stress case.", a4, "R4")):
        h.append("<h2>%s - %d contracts</h2>" % (title, len(d)))
        h.append("<div class='sub'>%s Age and size below are the %s event itself, "
                 "which may not be the contract's most recent state.</div>" % (sub, rg))
        cols = ["rank", "symbol", "age_" + rg, "pc_" + rg, "oc_" + rg, "funding", "vol_pct"]
        head = ["#", "contract", "age at " + rg, "price chg", "OI chg", "funding", "vol pctile"]
        h.append(table(d, cols, head) if len(d) else "<div class='sub none'>none in the window</div>")

    h.append("<h2>5. Funding-adjusted crowding view</h2>")
    h.append("<div class='sub'>x = funding percentile against the contract's own 90d history; "
             "y = 24h open-interest change. Upper-right = high funding with positions still being "
             "added (crowded longs). Dashed line marks the 75th percentile.</div>")
    h.append("<img src='data:image/png;base64,%s' alt='crowding'/>" % fig_crowding(df))
    h.append("<div class='sub'>Extreme quadrant: funding state high or extreme "
             "<b>and</b> 24h OI still rising - crowded longs that are still being added to.</div>")
    h.append(table(ext, ["symbol", "funding_pct", "oi_24h", "funding"],
                   ["contract", "funding pctile", "24h OI chg", "funding state"])
             if len(ext) else "<div class='sub none'>none</div>")

    h.append("<h2>6. Volatility percentile (own 90d history)</h2>")
    h.append("<div class='sub'>24h realised volatility of hourly returns, ranked against the same "
             "contract's own trailing %d days. This is the one dimension of the price/OI framework "
             "that is statistically robust: forward volatility rises after these events "
             "(16/16 cells, Phase 3). Direction is not.</div>" % VOL_LOOKBACK_D)
    h.append(table(vol, ["rank", "symbol", "vol_pct", "vol_rank"],
                   ["#", "contract", "vol pctile (own)", "cross-sectional rank"]))

    h.append("<footer>")
    h.append("<b>Not a trading signal.</b> This board is a state monitor. The strategy test in "
             "Phase 5 found no first-moment edge after a 20bp taker round trip: net Sharpe "
             "-1.48 (A1) and -0.98 (B1) on the main test window, and the verdict is not passed. "
             "The robust finding is the <i>second</i> moment - see section 6 and "
             "<code>phase3_event/GUIDANCE.md</code>. No historical return, Sharpe or cost figure "
             "appears anywhere on this page by design.")
    h.append("<br><br>Regimes are hourly event flags, not persistent states: at any hour only "
             "~4-8%% of contracts sit in one. 'Current' means the last bar of the frozen dataset "
             "(%s), not live data." % as_of.strftime("%Y-%m-%d %H:%M"))
    h.append("</footer></body></html>")
    return "".join(h)


def check(name, ok, detail=""):
    print("  [%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)



def last_bar() -> pd.Timestamp:
    p = sorted(LAB.glob("year=*/chunk=*.parquet"))[-1]
    return pd.read_parquet(p, columns=["ts_end"]).ts_end.max()


def main() -> int:
    ap = argparse.ArgumentParser(description="D5 - price/OI regime board")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD (default: last bar in the dataset)")
    args = ap.parse_args()

    end = last_bar()
    if args.asof:
        cut = pd.Timestamp(args.asof, tz="UTC") + pd.Timedelta(days=1)
        end = min(end, cut)
        # snap to the last available bar at or before the cut
        first, last = _span(cut)
        probe = pd.concat([pd.read_parquet(f, columns=["ts_end"])
                           for f in _files(LAB, first, last)], ignore_index=True)
        end = probe[probe.ts_end <= cut].ts_end.max()
    as_of = pd.Timestamp(end)
    first, last = _span(as_of)
    log("D5 board   as_of=%s   window=%dh   lookback=%dd" % (as_of, WINDOW_H, VOL_LOOKBACK_D))

    mem = pd.read_parquet(MEM)
    labels = load_labels(first, last, as_of)
    close = load_close(first, last, as_of)
    oi = load_oi(first, last, as_of)
    funding = load_funding(first, last, as_of)
    log("  loaded labels %d / close %d / oi %d / funding %d"
        % (len(labels), len(close), len(oi), len(funding)))

    df = build_board(as_of, labels, close, oi, funding, mem)
    n_ev = int((df["last"] != "-").sum())
    mkt = df.mkt_vol.mode().iloc[0] if len(df) else "unknown"
    log("  board rows %d   with an event in %dh: %d   market vol: %s"
        % (len(df), WINDOW_H, n_ev, mkt))

    ok = True
    a1 = df[df.age_R1.notna()]
    a3 = df[df.age_R3.notna()]
    a4 = df[df.age_R4.notna()]
    ok &= check("panel row counts match the master table",
                len(a1) == int(df.age_R1.notna().sum())
                and len(a3) == int(df.age_R3.notna().sum())
                and len(a4) == int(df.age_R4.notna().sum()),
                "R1 %d / R3 %d / R4 %d" % (len(a1), len(a3), len(a4)))

    sample = a1.sample(min(3, len(a1)), random_state=7) if len(a1) else a1
    hit = True
    for _, r in sample.iterrows():
        t = as_of - pd.Timedelta(hours=float(r.age_R1))
        m = labels[(labels.symbol == r.symbol) & (labels.ts_end == t) & (labels.regime == "R1")]
        hit &= len(m) == 1
    ok &= check("sampled R1 rows reproduce from the raw label table", hit,
                "%d sampled" % len(sample))

    t0 = pd.Timestamp("2021-12-01", tz="UTC")
    hh = int((as_of - t0).total_seconds() // 3600)
    if BASE1.exists():
        b = pd.read_parquet(BASE1, columns=["sym", "hour", "state"])
        # p4_base is an event table and trails the label panel by one bar; fall back to hh-1
        for probe in (hh, hh - 1):
            bb = b[(b.hour == probe) & (b.state >= 0)]
            if len(bb):
                b = bb
                break
        else:
            b = b.iloc[0:0]
        if len(b):
            j = df.merge(b, left_on="symbol", right_on="sym", how="inner")
            same = bool((j.funding == j.state).all()) if len(j) else True
            ok &= check("funding state agrees with p4_base_h=1", same,
                        "%d overlapping rows" % len(j))
        else:
            check("funding state vs p4_base_h=1", True, "no p4 rows at this hour (skipped)")
    else:
        check("funding state vs p4_base_h=1", True, "p4 base not present (skipped)")

    band_ok = True
    for _, r in df.dropna(subset=["funding_pct"]).iterrows():
        lo, hi = BAND[int(r["funding"])]
        band_ok &= (lo - 1e-9) <= r["funding_pct"] <= (hi + 1e-9)
    ok &= check("funding percentile sits inside its state's band", band_ok,
                "%d rows" % int(df["funding_pct"].notna().sum()))

    html = render(df, as_of, n_ev, mkt)
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / ("dashboard_%s.html" % as_of.strftime("%Y-%m-%d"))
    dst.write_text(html, encoding="utf-8", newline=chr(10))
    log("  written %s (%.1f KB)" % (dst, dst.stat().st_size / 1024))
    log("  checks %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
