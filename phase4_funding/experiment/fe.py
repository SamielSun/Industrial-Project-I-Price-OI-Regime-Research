"""Phase 4 · fast contract+month FE with 15 cell dummies (Gram/Schur).

The 16 disjoint cells (regime x {neg, neu, high-only, extreme}) are a partition.
One collinearity with the FE constant remains (the 16 dummies sum to 1), so the
last cell (index 15 = R4 x extreme) is the reference and 15 coefficients are
estimated. All reported quantities are contrasts, so the additive constant
cancels.

`fit` returns the 15 coefficients, their CGM two-way clustered covariance, and
the row-level influence function `psi = Xd * u` used by `t_drop5`.
"""
from __future__ import annotations

import numpy as np


def _cl(gs: np.ndarray, ns: int, psi: np.ndarray) -> np.ndarray:
    sc = np.zeros((ns, psi.shape[1]))
    for j in range(psi.shape[1]):
        sc[:, j] = np.bincount(gs, weights=psi[:, j], minlength=ns)
    return sc.T @ sc


def fit(y: np.ndarray, cell: np.ndarray, sym: np.ndarray, mon: np.ndarray):
    """y, cell (0..15), sym/mon as contiguous integer codes."""
    n = len(y)
    n_c = int(sym.max()) + 1
    n_m = int(mon.max()) + 1
    cnt_c = np.bincount(sym, minlength=n_c).astype("float64")
    cnt_m = np.bincount(mon, minlength=n_m).astype("float64")
    C_cm = np.bincount(sym * n_m + mon, minlength=n_c * n_m
                       ).reshape(n_c, n_m).astype("float64")

    m15 = cell < 15
    DD = np.diag(np.bincount(cell[m15], minlength=15).astype("float64"))
    Dc = np.zeros((15, n_c))
    Dm = np.zeros((15, n_m))
    np.add.at(Dc, (cell[m15], sym[m15]), 1.0)
    np.add.at(Dm, (cell[m15], mon[m15]), 1.0)
    Dy = np.bincount(cell, weights=y, minlength=16)[:15]
    Fy_c = np.bincount(sym, weights=y, minlength=n_c)
    Fy_m = np.bincount(mon, weights=y, minlength=n_m)

    FF = np.zeros((n_c - 1 + n_m, n_c - 1 + n_m))
    FF[:n_c - 1, :n_c - 1] = np.diag(cnt_c[:-1])
    FF[:n_c - 1, n_c - 1:] = C_cm[:-1, :]
    FF[n_c - 1:, :n_c - 1] = C_cm[:-1, :].T
    FF[n_c - 1:, n_c - 1:] = np.diag(cnt_m)
    DF = np.zeros((15, n_c - 1 + n_m))
    DF[:, :n_c - 1] = Dc[:, :-1]
    DF[:, n_c - 1:] = Dm
    FD = DF.T

    Fy = np.concatenate([Fy_c[:-1], Fy_m])
    H = np.linalg.solve(FF, FD)
    S = DD - DF @ H
    bread = np.linalg.inv(S)
    beta = bread @ (Dy - DF @ np.linalg.solve(FF, Fy))
    alpha = np.linalg.solve(FF, Fy - FD @ beta)

    fe_c = np.where(sym < n_c - 1, alpha[sym.clip(max=max(n_c - 2, 0))], 0.0)
    fe_m = alpha[n_c - 1 + mon]
    u = y - np.where(cell < 15, beta[cell.clip(max=14)], 0.0) - fe_c - fe_m

    Xd = np.zeros((n, 15))
    rows = np.arange(n)
    Xd[rows[m15], cell[m15]] = 1.0
    Xd -= np.where((sym < n_c - 1)[:, None],
                   H[sym.clip(max=max(n_c - 2, 0))], 0.0)
    Xd -= H[n_c - 1 + mon]
    psi = Xd * u[:, None]

    inter = sym * n_m + mon
    V = bread @ (_cl(sym, n_c, psi) + _cl(mon, n_m, psi)
                 - _cl(inter, n_c * n_m, psi)) @ bread
    return beta, V, u, psi


def contrast(beta: np.ndarray, V: np.ndarray, c: np.ndarray):
    est = float(c @ beta)
    var = float(c @ V @ c)
    se = float(np.sqrt(max(var, 0.0)))
    return est, se, (est / se if se > 0 else np.nan)


def t_drop5(y, cell, sym, mon, psi, c, n_c):
    """Drop the 5 contracts with the largest |sum psi_c| and re-estimate t."""
    s = psi @ c
    score = np.bincount(sym, weights=s, minlength=n_c)
    drop = np.argsort(-np.abs(score))[:5]
    keep = ~np.isin(sym, drop)
    if keep.sum() < 100:
        return np.nan
    us, s2 = np.unique(sym[keep], return_inverse=True)
    um, m2 = np.unique(mon[keep], return_inverse=True)
    if len(us) < 20 or len(um) < 10:
        return np.nan
    try:
        b2, V2, _, _ = fit(y[keep], cell[keep], s2, m2)
        return contrast(b2, V2, c)[2]
    except np.linalg.LinAlgError:
        return np.nan
