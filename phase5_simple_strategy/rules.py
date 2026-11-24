"""Phase 5 -- arm definitions (GUIDANCE.md sec.3 and sec.4).

Two arms come out of the gate (sec.3).  Nothing here is chosen by hand:

A1  cell 4 & state 0 (negative funding)  -> long,  hold 8h   primary
B1  cell 4 & market-vol high, any funding -> long,  hold 1h  reference

Both are R4 = price down AND open interest down, and both are long.  The gate is
two-sided: a cell's direction is the sign of its mean, so a cell below zero would
be an arm on the short side.  None does.  Three cells clear G1 with a negative
mean and all three fail G3 (the median is not negative), so the short side of the
gate is empty in this data and every surviving arm is long.

Sizing is flat: every signal takes SIZE_PER_SIGNAL, capped at MAX_UNITS of gross
exposure.  There is no fitted parameter in this module.
"""
from __future__ import annotations

import pandas as pd

ARMS: tuple[dict, ...] = (
    dict(name="A1", cell=4, state=0, mv=None, hold=8, role="primary",
         direction=1, note="note hypothesis: negative funding"),
    dict(name="B1", cell=4, state=None, mv="high", hold=1, role="reference",
         direction=1, note="no funding condition; market-vol high"),
)
ARM_BY_NAME = {a["name"]: a for a in ARMS}



def select(base: pd.DataFrame, arm: dict) -> pd.DataFrame:
    """Rows of p4_base_h={hold} belonging to this arm.

    Universe and event definition are inherited from the Phase 4 base: it only
    holds in_universe & excl_reason=='ok' rows.  state -1 (no funding label) is
    dropped, matching the gate's G0 filter.
    """
    b = base[base["state"].between(0, 3)]
    m = b["cell"] == arm["cell"]
    if arm["state"] is not None:
        m &= b["state"] == arm["state"]
    if arm["mv"] is not None:
        m &= b["mkt_vol_lab"] == arm["mv"]
    out = b.loc[m].copy()
    out["code"] = out["symbol"].astype("int64")
    out["arm"] = arm["name"]
    return out.sort_values(["hour", "code"]).reset_index(drop=True)
