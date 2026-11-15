"""Phase 5 -- arm definitions (HANDOFF.md sec.4) and the V1 volatility layer.

Two arms come out of the gate (sec.3).  Nothing here is chosen by hand:

A1  cell 4 & state 0 (negative funding)  -> long, hold 8h   primary
B1  cell 4 & market-vol high, any funding -> long, hold 1h  reference

Both are R4 = price down AND open interest down.  The gate found no arm outside
R4: 86 of 96 cells fail G1 (the level is not statistically above zero).

V1 (sec.4) is a volatility layer reported next to each arm, never a rule:
    target_vol = median(sigma) over that arm's TRAINING events, fitted once
    size       = clip(sigma_at_entry / target_vol, 0.5, 1.5)
vol = rv = exp(lrv), so the frozen ratio target_vol / vol is exp(target - lrv).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ARMS: tuple[dict, ...] = (
    dict(name="A1", cell=4, state=0, mv=None, hold=8, role="primary",
         note="note hypothesis: negative funding"),
    dict(name="B1", cell=4, state=None, mv="high", hold=1, role="reference",
         note="no funding condition; market-vol high"),
)
ARM_BY_NAME = {a["name"]: a for a in ARMS}

SIZE_FLOOR, SIZE_CAP = 0.5, 1.5
TARGET_QUANTILE = 0.5


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



def target_vol(sigma_train: np.ndarray) -> float:
    """Median causal volatility of the arm's TRAINING events, fitted once."""
    x = np.asarray(sigma_train, dtype="float64")
    x = x[np.isfinite(x) & (x > 0)]
    if x.size == 0:
        raise ValueError("target_vol: no finite sigma in the training window")
    return float(np.median(x))


def overlay_size(sigma: np.ndarray, target: float) -> np.ndarray:
    """Inverse-target-vol sizing: MORE size when volatility is HIGH.

    size multiplier = clip(sigma / target, 0.5, 1.5), multiplied by the base
    size of 0.2 units.  sigma is causal (backtest.trailing_vol); the ratio is
    against the arm's own training median, so it is scale-free.

    Note this is the opposite of textbook vol targeting.  That is deliberate:
    in this sample the gross edge RISES with volatility, so sizing down in
    high vol removes the best trades.
    """
    x = np.asarray(sigma, dtype="float64")
    x = np.where(np.isfinite(x) & (x > 0), x, target)
    return np.clip(x / target, SIZE_FLOOR, SIZE_CAP)