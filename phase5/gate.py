"""Phase 5 -- the Phase 4 -> Phase 5 gate (GUIDANCE.md sec.2, G0-G5).

    python -m phase5.gate            # write the table, print the pass set
    python -m phase5.gate --all      # print all 96 cells, not just those past G1

The gate answers one question only: does this cell contain something.  Cost and
executability are Phase 5's job (sec.6), not the gate's.

G0  load p4_base_h={1,4,8,24}, events cell 1..4, state 0..3 (2/3 merged to high)
G1  level significantly above 0: one-sided, CGM two-way clustered (symbol, month),
    BH within the 12-cell family of each (source, h)
G2  not pure beta: mean(y_raw) >= 0
G3  not tail-driven: median(fwd) > 0 and 1% trimmed mean > 0
G4  stable: >=4 of the 5 calendar years positive AND the last 12 months >= 0
G5  map surviving cells to strategy arms
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import backtest as bt

OUT = bt.DATA / "08_strategy" / "tables"
HORIZONS = (1, 4, 8, 24)
MIN_N = 400
BH_Q = 0.05

# G4 blocks: plain calendar years.  2022 is partial (the panel starts in March)
# and 2026 is partial (the sample ends in August), which is why the recency test
# is a rolling 12 months instead of "the 2026 block".
YEARS = (("Y22", "2022-03", "2022-12"), ("Y23", "2023-01", "2023-12"),
         ("Y24", "2024-01", "2024-12"), ("Y25", "2025-01", "2025-12"),
         ("Y26", "2026-01", "2026-08"))
RECENT_START = "2025-09"
MIN_POS_YEARS = 4

ARM_BY_CELL = {("P4", "R4", "neg", 8): ("A1", "primary (note hypothesis)"),
               ("P3", "R4", "high", 1): ("B1", "reference (no funding condition)")}


def _sf(t: float) -> float:
    return 0.5 * math.erfc(t / math.sqrt(2.0))


def cgm_se(y: np.ndarray, sym: np.ndarray, month: np.ndarray) -> float:
    """CGM two-way clustered SE of the mean: V_c + V_m - V_(c x m)."""
    e = y - y.mean()
    n = len(y)

    def cl(*keys):
        s = pd.Series(e).groupby(list(keys)).sum()
        return float((s ** 2).sum()) / n ** 2

    return float(np.sqrt(max(cl(sym) + cl(month) - cl(sym, month), 1e-30)))


def bh(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for i in range(n - 1, -1, -1):
        prev = min(prev, p[o[i]] * n / (i + 1))
        q[o[i]] = prev
    return q


def _row(src, dim, cell, cut, h, g: pd.DataFrame) -> dict:
    y = g["fwd"].to_numpy("float64") * 1e4
    se = cgm_se(y, g["sym"].to_numpy(), g["month"].to_numpy())
    tr = float(y[(y >= np.percentile(y, 1)) & (y <= np.percentile(y, 99))].mean())
    per = [float(g[(g["month"] >= lo) & (g["month"] <= hi)]["fwd"].mean() * 1e4)
           for _, lo, hi in YEARS]
    last12 = float(g[g["month"] >= RECENT_START]["fwd"].mean() * 1e4)
    return dict(src=src, dim=dim, cell=cell, cut=cut, h=h, n=len(y),
                level=float(y.mean()), se=se, t=float(y.mean()) / se,
                p=_sf(float(y.mean()) / se), yraw=float(g["y_raw"].mean() * 1e4),
                med=float(np.median(y)), trim=tr,
                Y22=per[0], Y23=per[1], Y24=per[2], Y25=per[3], Y26=per[4],
                n_pos=sum(1 for x in per if x > 0), last12=last12)


def cell_rows(b: pd.DataFrame, h: int) -> list[dict]:
    b = b[b["state"].between(0, 3)]
    out = []
    for cell in (1, 2, 3, 4):
        for cut in ("neg", "neu", "high"):
            mask = b["state"] == {"neg": 0, "neu": 1}.get(cut, -1)
            if cut == "high":
                mask = b["state"].isin([2, 3])
            g = b[(b["cell"] == cell) & mask]
            if len(g) >= MIN_N:
                out.append(_row("P4", "funding", f"R{cell}", cut, h, g))
        for cut in ("high", "mid", "low"):
            g = b[(b["cell"] == cell) & (b["mkt_vol_lab"] == cut)]
            if len(g) >= MIN_N:
                out.append(_row("P3", "mkt_vol", f"R{cell}", cut, h, g))
    return out


def build() -> pd.DataFrame:
    rows = []
    for h in HORIZONS:
        b = pd.read_parquet(bt.BASE / f"p4_base_h={h}.parquet",
                            columns=["cell", "state", "mkt_vol_lab", "fwd", "y_raw",
                                     "sym", "month"])
        rows.extend(cell_rows(b, h))
    df = pd.DataFrame(rows)
    df["q"] = np.nan
    for _, idx in df.groupby(["src", "h"]).groups.items():
        df.loc[idx, "q"] = bh(df.loc[idx, "p"].to_numpy())
    df["G1"] = df["q"] < BH_Q
    df["G2"] = df["yraw"] >= 0
    df["G3"] = (df["med"] > 0) & (df["trim"] > 0)
    df["G4"] = (df["n_pos"] >= MIN_POS_YEARS) & (df["last12"] >= 0)
    df["gate_pass"] = df[["G1", "G2", "G3", "G4"]].all(axis=1)
    arm = [ARM_BY_CELL.get((r.src, r.cell, r.cut, int(r.h)), ("", ""))
           for r in df.itertuples()]
    df["arm"] = [a for a, _ in arm]
    df["role"] = [b for _, b in arm]
    return df


COLS = ["src", "dim", "cell", "cut", "h", "n", "level", "se", "t", "p", "q",
        "yraw", "med", "trim", "Y22", "Y23", "Y24", "Y25", "Y26", "n_pos",
        "last12", "G1", "G2", "G3", "G4", "gate_pass", "arm", "role"]


def main(argv=None) -> int:
    import sys
    show_all = "--all" in (argv if argv is not None else sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    df[COLS].to_csv(OUT / "p5_gate.csv", index=False)
    fin = df[df.gate_pass][COLS]
    fin.to_csv(OUT / "p5_gate_arms.csv", index=False)

    pd.set_option("display.width", 250)
    print("G0  cells tested: %d   (P4 = %d, P3 = %d)"
          % (len(df), (df.src == "P4").sum(), (df.src == "P3").sum()))
    print("G1  level significant (BH q<0.05): %d" % df.G1.sum())
    print("G2  survived (not pure beta):      %d" % (df.G1 & df.G2).sum())
    print("G3  survived (not tail-driven):    %d" % (df.G1 & df.G2 & df.G3).sum())
    print("G4  survived (>=%d/5 years +, last 12m >= 0): %d  <- arms"
          % (MIN_POS_YEARS, df.gate_pass.sum()))
    print("")
    show = df if show_all else df[df.G1]
    print("cells that passed G1, with every condition and every year:")
    print(show[["src", "cell", "cut", "h", "n", "level", "q", "yraw", "med",
                "Y22", "Y23", "Y24", "Y25", "Y26", "n_pos", "last12",
                "G1", "G2", "G3", "G4", "gate_pass", "arm"]].round(2).to_string(index=False))
    print("")
    print("arms that passed every condition:")
    print(fin[["arm", "src", "cell", "cut", "h", "n", "level", "q", "yraw",
               "n_pos", "last12", "role"]].round(2).to_string(index=False))
    print("")
    print("written: %s" % (OUT / "p5_gate.csv"))
    print("written: %s" % (OUT / "p5_gate_arms.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
