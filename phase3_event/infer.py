"""Phase 3 · infer —— 推断基元（不带数据加载）

fe_ols()        合约 + 月份双向固定效应下的 OLS（实验 1/3/1b、16）
demean2()       单列双向去均值（不平衡面板要迭代）
demean2_cols()  多列一起双向去均值
cgm_cov()       双向聚类协方差 V = V_合约 + V_月份 − V_合约×月份
cgm_se()        同上，只返回标准误
bh()            Benjamini-Hochberg 校正后的 p
p_two()         双侧 p（|t| 的正态尾概率）
"""
from __future__ import annotations

import math

import numpy as np


def p_two(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2.0))


def _group_mean(a: np.ndarray, g: np.ndarray, n: int) -> np.ndarray:
    cnt = np.bincount(g, weights=np.isfinite(a).astype("float64"), minlength=n)
    tot = np.bincount(g, weights=np.where(np.isfinite(a), a, 0.0), minlength=n)
    return np.where(cnt > 0, tot / np.where(cnt > 0, cnt, 1.0), 0.0)


def demean2(a: np.ndarray, g1: np.ndarray, n1: int, g2: np.ndarray, n2: int,
            iters: int = 25, tol: float = 1e-7) -> np.ndarray:
    """双向去均值：反复减 g1 组均值、g2 组均值，直到两边都归零。

    单一维度时一次就够；两维互相影响，所以要迭代（不平衡面板尤其需要）。
    """
    z = np.array(a, dtype="float64", copy=True)
    for _ in range(iters):
        z = z - _group_mean(z, g1, n1)[g1]
        z = z - _group_mean(z, g2, n2)[g2]
        if max(np.abs(_group_mean(z, g1, n1)).max(initial=0.0),
               np.abs(_group_mean(z, g2, n2)).max(initial=0.0)) < tol:
            break
    return z


def demean2_cols(Z: np.ndarray, g1: np.ndarray, n1: int, g2: np.ndarray, n2: int,
                 iters: int = 25, tol: float = 1e-7) -> np.ndarray:
    """多列一起双向去均值：同样的分组，一次循环处理所有列。"""
    out = np.array(Z, dtype="float64", copy=True)
    if out.ndim == 1:
        return demean2(out, g1, n1, g2, n2, iters, tol)
    for _ in range(iters):
        for j in range(out.shape[1]):
            out[:, j] = out[:, j] - _group_mean(out[:, j], g1, n1)[g1]
        for j in range(out.shape[1]):
            out[:, j] = out[:, j] - _group_mean(out[:, j], g2, n2)[g2]
        r1 = max(np.abs(_group_mean(out[:, j], g1, n1)).max(initial=0.0)
                 for j in range(out.shape[1]))
        r2 = max(np.abs(_group_mean(out[:, j], g2, n2)).max(initial=0.0)
                 for j in range(out.shape[1]))
        if max(r1, r2) < tol:
            break
    return out


def _cluster_var(psi: np.ndarray, g: np.ndarray, n: int) -> np.ndarray:
    k = psi.shape[1]
    sc = np.zeros((n, k))
    for j in range(k):
        sc[:, j] = np.bincount(g, weights=psi[:, j], minlength=n)
    return sc.T @ sc


def cgm_cov(psi: np.ndarray, bread: np.ndarray, g1: np.ndarray, n1: int,
            g2: np.ndarray, n2: int) -> np.ndarray:
    """Cameron-Gelbach-Miller 双向聚类的协方差矩阵： V = V1 + V2 − V12。"""
    V = _cluster_var(psi, g1, n1) + _cluster_var(psi, g2, n2)
    inter = g1 * n2 + g2
    V = V - _cluster_var(psi, inter, int(inter.max()) + 1)
    return bread @ V @ bread


def cgm_se(psi: np.ndarray, bread: np.ndarray, g1: np.ndarray, n1: int,
           g2: np.ndarray, n2: int) -> np.ndarray:
    """同上，只返回各系数的标准误。"""
    return np.sqrt(np.maximum(np.diag(cgm_cov(psi, bread, g1, n1, g2, n2)), 0.0))


def fe_ols(y: np.ndarray, X: np.ndarray, g1: np.ndarray, n1: int,
           g2: np.ndarray, n2: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """双向固定效应 OLS。返回 (beta, 逐行影响函数 psi, 双向聚类 SE)。"""
    Z = demean2_cols(np.column_stack([y, X]), g1, n1, g2, n2)
    yd, Xd = Z[:, 0], Z[:, 1:]
    XtX = Xd.T @ Xd
    beta = np.linalg.solve(XtX, Xd.T @ yd)
    bread = np.linalg.inv(XtX)
    u = yd - Xd @ beta
    psi = Xd * u[:, None]
    se = cgm_se(psi, bread, g1, n1, g2, n2)
    return beta, psi, se


def bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg 校正后的 p。"""
    p = np.asarray(p, dtype="float64")
    out = np.full(p.size, np.nan)
    ok = np.isfinite(p)
    if ok.sum() == 0:
        return out
    idx = np.where(ok)[0]
    order = idx[np.argsort(p[idx])]
    m = order.size
    adj = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[order] = np.minimum(adj, 1.0)
    return out


def nw_se(x: np.ndarray, lag: int) -> float:
    """均值的 Newey-West（Bartlett 核）标准误。

    γ0 + 2·Σ_{l=1..lag} (1 − l/(lag+1))·γ_l，再除以 n 开根；
    γ_l 用 1/n 归一（与 statsmodels 的 cov_type="HAC" 默认一致）。
    """
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = x.size
    if n < 2:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for l in range(1, min(lag, n - 1) + 1):
        g = float(e[l:] @ e[:-l]) / n
        s += 2.0 * (1.0 - l / (lag + 1.0)) * g
    if s <= 0:
        return float("nan")
    return float(np.sqrt(s / n))
