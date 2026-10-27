"""Phase 3 · confirmatory —— 实验 1–4 + 描述层的**四格**版本（实现者 B；推断口径
2026-10-27 由实现者 D 从"双向聚类"改为"只按合约聚类"）

一句话
    在冻结口径（D13 / D14 / D15）下，用 `stats_core` 的基元把四个确认性检验各跑
    一遍，并把描述层四格的底数落成表。**点估计与描述层数字照旧与独立复算
    `_rebuild/_oracle_four_cell_results.md` 逐项对齐；SE 类只钉一个锚点
    （DiD 的按合约 SE = 0.0004656142），实验 3/4 的 χ² 不再对拍旧的双向值，
    只断言"仍然显著 / 仍然不显著"并记录新值**（闸门逐项 PASS/FAIL 写进
    `data/06_event_study/docs/step7_checks_confirmatory.txt`）。

样本（`EVENT.horizons` 的最大值 H = 24）
    headline = `in_universe`，再过滤 `ok_24h`
    → **n = 255,807**（headline 256,079，丢 272 行 y 缺失）；
    格 n：R1 74,875 / R2 50,519 / R3 44,585 / R4 85,828；
    簇：**合约 249**（唯一的聚类维度）；每个 (hour, symbol) 唯一，无重复。
    方向（实测核对）：R1=(P+1,q+1) R2=(P+1,q−1) R3=(P−1,q+1) R4=(P−1,q−1)。

四个实验（设计一律四格 const / P / q / P·q，q ∈ {−1,+1}，D14.4）
    1 收益·均值   y = winsor_fwd_24h，四格 + **按合约聚类**（symbol），
                  DiD = 4·b_Pq，χ²(3) = H0: P = q = P·q = 0（⟺ 四格均值全相等）。
    2 收益·中位数 同一批行，`cell_medians_boot`（按小时有放回、整小时带走，
                  (reps, seed) 取自 `EventConfig` → 1000 次），四格中位数与
                  DiD 的中位数差，区间取重抽分布的 2.5/97.5 百分位。
    3 波动        y = log(rv_24h)，四格，**不加任何固定效应**（D15.1；加 FE 会让
                  交互项变号，且那是另一个问题）。报 c = R3−R4 = 2(b_q − b_Pq)、
                  g = (R1−R2)−(R3−R4) = 4·b_Pq 与 χ²(3)。
    4 反转斜率    y = winsor_fwd_24h，按 SPEC §3.1 的嵌套参数化
                  X = [mu_R1..mu_R4, ls, D2·ls, D3·ls, D4·ls]（ls = log(shock)），
                  四条斜率 theta_Rk，H0: 四条相等 → `wald_test(b, V, [5,6,7])`，df = 3。
                  （用 8 参模型直接挑 4 个下标问的是"斜率全为 0"，不是这个数。）

口径三条（不许在表里改）
    * 推断只用 CGM **单向聚类（按合约 symbol）**：V = bread·(Σ_g s_g s_g')·bread，
      无小样本校正。**双向聚类整个删掉**（用户拍板）：时刻维度的相关不再进入
      协方差 —— 中性化之后小时维度 lag24 自相关只剩 0.001；按合约的 SE 已经是
      双向的 96.7%（iid 3.4368bp / 按合约 4.6561bp / 双向 4.8137bp；时刻维度
      只占 iid→双向 那 1.38bp 修正的 11%）。
      均值与 OLS 一次都不重抽；只有中位数重抽（它没有解析标准误，按小时有放回）。
    * 单位内部一律**小数**（D14.2），表里给 unit 列标注；×100 即百分数。
      波动表是 log(rv) 尺度，系数换算成百分比要 exp(b) − 1。
    * 联合检验一律 W = b'V⁻¹b（V 来自同一组聚类协方差），**不把两个 t² 相加**。

输出
    data/06_event_study/tables/freq=1h/confirmatory_return.parquet    （实验 1、2）+ .csv
    data/06_event_study/tables/freq=1h/confirmatory_vol.parquet       （实验 3）  + .csv
    data/06_event_study/tables/freq=1h/confirmatory_slope.parquet     （实验 4）  + .csv
    data/06_event_study/tables/freq=1h/descriptive_four_cell.parquet  （描述层）  + .csv
    data/06_event_study/docs/step7_checks_confirmatory.txt            （闸门全文）

用法
    python phase3_event/confirmatory.py          # 全部 PASS 退出码 0，任一 FAIL 退出码 1
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))          # stats_core 在同一个目录
sys.path.insert(0, str(HERE.parent))   # config 在仓库根目录
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows 控制台是 GBK
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402
import stats_core as sc  # noqa: E402

EVENT = cfg_mod.EVENT
FREQ = "1h"
H = max(EVENT.horizons)          # 主前向期 = 24（EventConfig.horizons 的最大值）
"""列名全部由 H 生成，避免"手写 24h 与参数不一致"。"""

Y_WIN = f"winsor_fwd_{H}h"
Y_RAW = f"fwd_{H}h"
Y_EXC = f"excess_fwd_{H}h"
Y_RV = f"rv_{H}h"
OK = f"ok_{H}h"
HIT = f"hit_{H}h"

CELLS = ("R1", "R2", "R3", "R4")
PQ = {"R1": (+1, +1), "R2": (+1, -1), "R3": (-1, +1), "R4": (-1, -1)}
Z95 = NormalDist().inv_cdf(0.975)   # 1.959963984540054，与 oracle 同一个数

ROOT = HERE.parent
OUT_ROOT = ROOT / "data" / "06_event_study"
EV_PATH = OUT_ROOT / "events" / f"events_{FREQ}.parquet"
TBL_DIR = OUT_ROOT / "tables" / f"freq={FREQ}"
DOC_DIR = OUT_ROOT / "docs"
CHECKS_PATH = DOC_DIR / "step7_checks_confirmatory.txt"

UNIT_RET = "decimal_return"
UNIT_LOG = "log_rv"
UNIT_SLOPE = "decimal_return_per_log_shock"
UNIT_CHI2 = "chi2_statistic"

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


# ============================================================ 0. 样本与编码
COLS = ["symbol", "regime", "in_universe", "hour", "price_change", "oi_change",
        "price_thr", "oi_thr", "shock", "d", OK, HIT, Y_RV, Y_RAW, Y_EXC, Y_WIN]


def load_sample() -> tuple[pd.DataFrame, int]:
    """headline（in_universe）∩ ok_24h，按 (hour, symbol) 稳定排序。"""
    ev = pd.read_parquet(EV_PATH, columns=COLS)
    n_all = len(ev)
    s = ev.loc[ev["in_universe"].to_numpy(dtype=bool)].copy()
    n_headline = len(s)
    s = s.loc[s[OK].to_numpy(dtype=bool)]
    s = s.sort_values(["hour", "symbol"], kind="stable").reset_index(drop=True)
    log(f"事件表 {n_all:,} 行 → headline {n_headline:,} 行 → {OK} 后 n = {len(s):,}"
        f"（丢 {n_headline - len(s)} 行 y 缺失）")
    return s, n_headline


def symbol_codes(s: pd.DataFrame) -> np.ndarray:
    """唯一聚类维度 = 合约 symbol。只要求"同一簇同号"，factorize 的顺序无关。

    返回值直接喂给 `stats_core.cluster_se`；真实数据里 symbol 是字符串
    （object dtype），cluster_se 用 np.unique 处理，不需要在这里转成整数。
    """
    return pd.factorize(s["symbol"].to_numpy(), sort=False)[0].astype("int64")


# ============================================================ 1. 估计量小工具
def _lin(b: np.ndarray, V: np.ndarray, w) -> tuple[float, float]:
    """线性组合 w'b 的点估计与 SE（协方差取自同一组 cluster_se，D14.5）。

    SE 只做 sqrt(w'Vw)，不做任何聚类或 Wald 的重算——那两件事归 stats_core。
    """
    w = np.asarray(w, dtype="float64").ravel()
    var = float(w @ V @ w)
    return float(w @ b), math.sqrt(max(var, 0.0))


def _stat(est: float, se: float) -> dict:
    """点估计 + SE → t / p / 95% 区间（单自由度）。

    p 用 chi2_sf(1, t²)，与双侧正态 p 恒等（stats_core.chi2_sf 自检第 1 条）。
    """
    t = est / se
    return {"estimate": est, "se": se, "t": t, "p": sc.chi2_sf(1, t * t),
            "ci_lo": est - Z95 * se, "ci_hi": est + Z95 * se}


def _w(k: int, *pairs) -> np.ndarray:
    """按列下标构造线性组合权重：_w(4, (k["q"], 2.0), (k["Pq"], -2.0))。"""
    w = np.zeros(k)
    for i, v in pairs:
        w[int(i)] = float(v)
    return w


# ============================================================ 2. 实验 1
def experiment1(s: pd.DataFrame, y: np.ndarray, cS, X4, names4) -> dict:
    """收益 · 均值：四格 + 按合约聚类（y = winsor_fwd_24h）。"""
    b, V = sc.cluster_se(X4, y, cS)
    k = {nm: i for i, nm in enumerate(names4)}
    coef = {}
    for nm in names4:
        w = np.zeros(len(names4))
        w[k[nm]] = 1.0
        coef[nm] = _stat(*_lin(b, V, w))
    did = _stat(*_lin(b, V, _w(len(names4), (k["Pq"], 4.0))))
    # R1−R2 = 2(q + Pq)，R3−R4 = 2(q − Pq)（四格饱和的代数恒等）
    r12 = _stat(*_lin(b, V, _w(len(names4), (k["q"], 2.0), (k["Pq"], 2.0))))
    r34 = _stat(*_lin(b, V, _w(len(names4), (k["q"], 2.0), (k["Pq"], -2.0))))
    W, p = sc.wald_test(b, V, [k["P"], k["q"], k["Pq"]])
    reg = s["regime"].to_numpy()
    cell_mean = {c: float(y[reg == c].mean()) for c in CELLS}
    cell_n = {c: int((reg == c).sum()) for c in CELLS}
    return {"b": b, "V": V, "coef": coef, "did": did, "r12": r12, "r34": r34,
            "wald": (W, p), "cell_mean": cell_mean, "cell_n": cell_n,
            "n": len(s), "X": X4, "names": names4}


# ============================================================ 3. 实验 2
def experiment2(s: pd.DataFrame, y: np.ndarray) -> dict:
    """收益 · 中位数：四格中位数 + 按小时重抽（不切块，D14.1 的中位数例外）。"""
    t0 = time.time()
    M = sc.cell_medians_boot(s, Y_WIN, "regime", "hour",
                             reps=EVENT.random_draws, seed=EVENT.random_seed)
    elapsed = time.time() - t0
    labels = [str(x) for x in np.unique(s["regime"].to_numpy())]
    reg = s["regime"].to_numpy()
    point = {c: float(np.median(y[reg == c])) for c in labels}
    cells = {}
    for j, c in enumerate(labels):
        cells[c] = {"estimate": point[c],
                    "se": float(M[:, j].std(ddof=1)),
                    "ci_lo": float(np.percentile(M[:, j], 2.5)),
                    "ci_hi": float(np.percentile(M[:, j], 97.5))}
    # 配对：同一次重抽里先算四格中位数、再作差（不是两次独立重抽的差）
    dist = (M[:, 0] - M[:, 1]) - (M[:, 2] - M[:, 3])
    did = {"estimate": (point["R1"] - point["R2"]) - (point["R3"] - point["R4"]),
           "se": float(dist.std(ddof=1)),
           "ci_lo": float(np.percentile(dist, 2.5)),
           "ci_hi": float(np.percentile(dist, 97.5))}
    cell_n = {c: int((reg == c).sum()) for c in CELLS}
    return {"M": M, "labels": labels, "cells": cells, "did": did,
            "share_neg": float((dist < 0).mean()), "boot_median": float(np.median(dist)),
            "boot_mean": float(dist.mean()), "elapsed": elapsed,
            "cell_n": cell_n, "n": len(s)}


# ============================================================ 4. 实验 3
def experiment3(s: pd.DataFrame, y_logrv: np.ndarray, cS, X4, names4) -> dict:
    """波动：四格 + 按合约聚类（y = log(rv_24h)），**不加任何固定效应**（D15.1）。"""
    b, V = sc.cluster_se(X4, y_logrv, cS)
    k = {nm: i for i, nm in enumerate(names4)}
    coef = {}
    for nm in names4:
        w = np.zeros(len(names4))
        w[k[nm]] = 1.0
        coef[nm] = _stat(*_lin(b, V, w))
    c_oi = _stat(*_lin(b, V, _w(len(names4), (k["q"], 2.0), (k["Pq"], -2.0))))  # R3−R4
    g_int = _stat(*_lin(b, V, _w(len(names4), (k["Pq"], 4.0))))                  # 4·b_Pq
    W, p = sc.wald_test(b, V, [k["P"], k["q"], k["Pq"]])
    reg = s["regime"].to_numpy()
    cell_mean = {c: float(y_logrv[reg == c].mean()) for c in CELLS}
    return {"b": b, "V": V, "coef": coef, "c": c_oi, "g": g_int, "wald": (W, p),
            "cell_mean": cell_mean, "n": len(s)}


# ============================================================ 5. 实验 4
LS = 4          # 嵌套参数化里公共斜率 ls 的列下标（前 4 列是四格的 mu）


def experiment4(s: pd.DataFrame, y: np.ndarray, cS) -> dict:
    """反转斜率：SPEC §3.1 的嵌套参数化，H0 = 四条斜率相等 → χ²(3)。"""
    reg = s["regime"].to_numpy()
    ls = np.log(s["shock"].to_numpy(dtype="float64"))
    D = {c: (reg == c).astype("float64") for c in CELLS}
    X = np.column_stack([D["R1"], D["R2"], D["R3"], D["R4"],
                         ls, D["R2"] * ls, D["R3"] * ls, D["R4"] * ls])
    b, V = sc.cluster_se(X, y, cS)
    mu, theta = {}, {}
    for i, c in enumerate(CELLS):
        w = np.zeros(8)
        w[i] = 1.0
        mu[c] = _stat(*_lin(b, V, w))
        w = np.zeros(8)
        w[LS] = 1.0
        if i:                       # theta_Rk = b_ls + b_{Dk·ls}；theta_R1 = b_ls
            w[LS + i] = 1.0
        theta[c] = _stat(*_lin(b, V, w))
    diffs = {}
    for i, c in enumerate(CELLS):
        if i:                       # theta_R1 − theta_Rk = −b_{Dk·ls}
            w = np.zeros(8)
            w[LS + i] = -1.0
            diffs[c] = _stat(*_lin(b, V, w))
    W, p = sc.wald_test(b, V, [LS + 1, LS + 2, LS + 3])
    return {"X": X, "b": b, "V": V, "mu": mu, "theta": theta, "diffs": diffs,
            "wald": (W, p), "n": len(s)}


# ============================================================ 6. 描述层
def descriptive(s: pd.DataFrame, y, y_raw, y_exc, y_rv) -> pd.DataFrame:
    """每格的 n / 均值 / 中位数 / 命中率 / 平均 rv（三种收益口径并列）。"""
    reg = s["regime"].to_numpy()
    dvec = s["d"].to_numpy(dtype="float64")
    hit = s[HIT].to_numpy(dtype="float64")
    rows = []
    for c in CELLS:
        m = reg == c
        rows.append({
            "cell": c,
            "price_sign": PQ[c][0],
            "oi_sign": PQ[c][1],
            "n": int(m.sum()),
            "share_of_sample": float(m.mean()),
            "mean_winsor": float(y[m].mean()),
            "median_winsor": float(np.median(y[m])),
            "mean_raw": float(y_raw[m].mean()),
            "median_raw": float(np.median(y_raw[m])),
            "mean_excess": float(y_exc[m].mean()),
            "median_excess": float(np.median(y_exc[m])),
            "hit_raw": float(hit[m].mean()),
            "hit_neutral": float(np.mean(dvec[m] * y[m] > 0)),
            "mean_rv": float(y_rv[m].mean()),
            "median_rv": float(np.median(y_rv[m])),
            "share_winsorized": float(np.mean(y[m] != y_exc[m])),
        })
    df = pd.DataFrame(rows)
    df.insert(0, "sample", "headline")
    df.insert(1, "h", H)
    return df


# ============================================================ 7. 表
def _rec(experiment: str, statistic: str, r: dict, cell: str = "", n: int = 0,
         method: str = "symbol_cluster", unit: str = UNIT_RET, note: str = "") -> dict:
    row = {"experiment": experiment, "statistic": statistic, "cell": cell}
    for key in ("estimate", "se", "t", "p", "ci_lo", "ci_hi"):
        row[key] = r.get(key, np.nan)
    row.update({"n": n, "method": method, "unit": unit, "note": note})
    return row


def _table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.insert(0, "sample", "headline")
    df.insert(1, "h", H)
    return df


def build_return_table(res1: dict, res2: dict) -> pd.DataFrame:
    """实验 1（均值）+ 实验 2（中位数）。"""
    n1, n2 = res1["n"], res2["n"]
    rows = [_rec("exp1_mean", f"b_{nm}", res1["coef"][nm], n=n1) for nm in sc.FOUR_CELL_NAMES]
    rows.append(_rec("exp1_mean", "did", res1["did"], n=n1,
                     note="DiD = (R1−R2)−(R3−R4) = 4·b_Pq"))
    rows.append(_rec("exp1_mean", "R1_minus_R2", res1["r12"], n=n1, note="= 2(b_q + b_Pq)"))
    rows.append(_rec("exp1_mean", "R3_minus_R4", res1["r34"], n=n1, note="= 2(b_q − b_Pq)"))
    W, p = res1["wald"]
    rows.append(_rec("exp1_mean", "chi2_3_joint", {"estimate": W, "p": p}, n=n1,
                     method="symbol_cluster_wald", unit=UNIT_CHI2,
                     note="H0: P = q = P·q = 0（⟺ 四格均值全相等）；df = 3"))
    rows += [_rec("exp1_mean", "cell_mean", {"estimate": res1["cell_mean"][c]}, cell=c,
                  n=res1["cell_n"][c], method="descriptive",
                  note="四格饱和：等于 X@b 的拟合值") for c in CELLS]
    rows += [_rec("exp2_median", "cell_median", res2["cells"][c], cell=c, n=res2["cell_n"][c],
                  method="hour_bootstrap_1000",
                  note=f"按小时有放回重抽 {EVENT.random_draws} 次、整小时带走；"
                       "se = 重抽 sd，区间 = 2.5/97.5 百分位") for c in CELLS]
    rows.append(_rec("exp2_median", "median_did", res2["did"], n=n2, method="hour_bootstrap_1000",
                     note="(R1−R2)−(R3−R4) 的配对中位数差：同一次重抽内先算四格中位数再作差"))
    return _table(rows)


def build_vol_table(res3: dict) -> pd.DataFrame:
    """实验 3（log(rv_24h)，无固定效应）。"""
    n = res3["n"]
    rows = [_rec("exp3_vol", f"b_{nm}", res3["coef"][nm], n=n, unit=UNIT_LOG)
            for nm in sc.FOUR_CELL_NAMES]
    rows.append(_rec("exp3_vol", "c_R3_minus_R4", res3["c"], n=n, unit=UNIT_LOG,
                     note="c = R3−R4 = 2(b_q − b_P·q)；exp(c)−1 为百分比效应"))
    rows.append(_rec("exp3_vol", "g_interaction", res3["g"], n=n, unit=UNIT_LOG,
                     note="g = (R1−R2)−(R3−R4) = 4·b_P·q；exp(g)−1 为百分比效应"))
    W, p = res3["wald"]
    rows.append(_rec("exp3_vol", "chi2_3_joint", {"estimate": W, "p": p}, n=n,
                     method="symbol_cluster_wald", unit=UNIT_CHI2,
                     note="H0: P = q = P·q = 0；df = 3；描述性结果（无固定效应，未控同刻市场波动）"))
    rows += [_rec("exp3_vol", "cell_mean_logrv", {"estimate": res3["cell_mean"][c]}, cell=c,
                  n=n, method="descriptive", unit=UNIT_LOG,
                  note="四格饱和：等于 X@b 的拟合值") for c in CELLS]
    return _table(rows)


def build_slope_table(res4: dict) -> pd.DataFrame:
    """实验 4（四条 log(shock) 斜率 + 斜率相等的 χ²(3)）。"""
    n = res4["n"]
    rows = [_rec("exp4_slope", "mu", res4["mu"][c], cell=c, n=n, unit=UNIT_SLOPE,
                 note="格内截距（ls = log(shock) = 0 处）") for c in CELLS]
    rows += [_rec("exp4_slope", "theta", res4["theta"][c], cell=c, n=n, unit=UNIT_SLOPE,
                  note="该格的冲击 → 收益斜率") for c in CELLS]
    rows += [_rec("exp4_slope", f"theta_R1_minus_{c}", res4["diffs"][c], cell=c, n=n,
                  unit=UNIT_SLOPE, note="斜率差（= −b_{Dk·ls}，嵌套参数化）") for c in CELLS[1:]]
    W, p = res4["wald"]
    rows.append(_rec("exp4_slope", "chi2_3_equal_slopes", {"estimate": W, "p": p}, n=n,
                     method="symbol_cluster_wald", unit=UNIT_CHI2,
                     note="H0: theta_R1 = theta_R2 = theta_R3 = theta_R4（4 条斜率 → 3 个约束）；"
                          "wald_test(b, V, [5,6,7])，df = 3"))
    return _table(rows)


def write_table(df: pd.DataFrame, name: str) -> None:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TBL_DIR / f"{name}.parquet", index=False)
    df.to_csv(TBL_DIR / f"{name}.csv", index=False, encoding="utf-8")
    log(f"写盘 {name}.parquet / .csv  （{len(df)} 行 × {df.shape[1]} 列）")


# ============================================================ 8. 闸门
class Gate:
    """逐项记录 PASS/FAIL；near/rel 同时跟踪与 oracle 的绝对/相对偏差。"""

    def __init__(self, header: str) -> None:
        self.lines = [header]
        self.n_pass = 0
        self.n_fail = 0
        self.n_cmp = 0
        self.max_abs = 0.0
        self.max_abs_label = ""
        self.max_exact = 0.0        # 只统计 oracle 印 10 位小数的锚点
        self.max_exact_label = ""
        self.buckets = {}           # tol → (max |Δ|, label)
        self.rel_bucket = (0.0, "")

    def _emit(self, ok: bool, body: str) -> None:
        self.n_pass += int(ok)
        self.n_fail += int(not ok)
        self.lines.append(f"  [{'PASS' if ok else 'FAIL'}] {body}")

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(title)

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self._emit(bool(ok), label + (f"  [{detail}]" if detail else ""))

    def near(self, label: str, got: float, exp: float, tol: float = 1e-6,
             fmt: str = "%+.10f", anchor: bool = True) -> None:
        """绝对容差比对（默认 1e-6，与验收口径一致）。

        anchor=True 且 fmt 为 10 位小数、容差 ≤ 1e-6 时，这一项同时计入
        "oracle 印 10 位小数"的锚点组（oracle 只印 8 位小数的量设 anchor=False）。
        """
        dev = abs(float(got) - float(exp))
        self.n_cmp += 1
        if dev > self.max_abs:
            self.max_abs, self.max_abs_label = dev, label
        if tol > 0.0:
            prev = self.buckets.get(tol)
            if prev is None or dev > prev[0]:
                self.buckets[tol] = (dev, label)
        if anchor and tol == 1e-6 and fmt == "%+.10f" and dev > self.max_exact:
            self.max_exact, self.max_exact_label = dev, label
        self._emit(dev <= tol,
                   f"{label} = {fmt % float(got)}   oracle {fmt % float(exp)}   |Δ| {dev:.1e}")

    def rel(self, label: str, got: float, exp: float, rtol: float = 1e-4) -> None:
        """相对容差比对（只给 4–5 位有效数字的量：p 值、比值、小斜率差）。"""
        rel = abs(float(got) - float(exp)) / abs(float(exp))
        self.n_cmp += 1
        if rel > self.rel_bucket[0]:
            self.rel_bucket = (rel, label)
        self._emit(rel <= rtol,
                   f"{label} = {float(got):.6e}   oracle {float(exp):.6e}   rel {rel:.1e}")

    def text(self, footer: str) -> str:
        total = self.n_pass + self.n_fail
        out = ["\n".join(self.lines), "",
               f"闸门汇总：PASS {self.n_pass} / FAIL {self.n_fail}"
               f"（共 {total} 项，其中与 oracle 的数值比对 {self.n_cmp} 项）",
               "与 oracle 的最大偏差，按 oracle 自己给出的位数分档"
               "（放宽容差只为吸收它的四舍五入）："]
        for tol in sorted(self.buckets):
            dev, label = self.buckets[tol]
            tag = "整数计数" if tol == 0.0 else f"容差 {tol:.0e}"
            out.append(f"  {tag}：max |Δ| {dev:.2e}（{label}）")
        dev, label = self.rel_bucket
        out.append(f"  相对容差（4–5 位有效数字的量）：max rel {dev:.2e}（{label}）")
        out.append(f"  其中 oracle 印 10 位小数的锚点（系数 / SE / 区间 / 格均值 /"
                   f" 中位数 / 斜率 / mu）：max |Δ| {self.max_exact:.2e}"
                   f"（{self.max_exact_label}）")
        out.append(f"  全部比对的最大 |Δ|（含 t 值 3 位、p 值 4 位等粗印位数的量）："
                   f"{self.max_abs:.2e}（{self.max_abs_label}）")
        return "\n".join(out) + "\n" + footer + "\n"


def gate_sample(g: Gate, s: pd.DataFrame, n_headline: int, cS, X4) -> None:
    g.section("0. 样本与聚类基（SPEC §零 / §四）")
    reg = s["regime"].to_numpy()
    n = len(s)
    g.near("headline 行数", n_headline, 256079, tol=0, fmt="%.0f")
    g.near(f"{OK} 过滤后 n", n, 255807, tol=0, fmt="%.0f")
    g.near("被 ok_24h 丢掉的行数", n_headline - n, 272, tol=0, fmt="%.0f")
    exp_cell = {"R1": 74875, "R2": 50519, "R3": 44585, "R4": 85828}
    for c in CELLS:
        g.near(f"格 {c} n", int((reg == c).sum()), exp_cell[c], tol=0, fmt="%.0f")
    g.check("每行恰好落在一格（四格 n 之和 = n）",
            sum(int((reg == c).sum()) for c in CELLS) == n,
            f"{sum(int((reg == c).sum()) for c in CELLS):,} / {n:,}")
    g.near("合约簇数（唯一聚类维度）", int(np.unique(cS).size), 249, tol=0, fmt="%.0f")
    dup = int(s.duplicated(subset=["hour", "symbol"]).sum())
    g.check("(hour, symbol) 无重复（每个事件一行）", dup == 0, f"重复 {dup} 行，行数 {n:,}")
    rank4 = int(np.linalg.matrix_rank(X4))
    g.check("四格设计矩阵满秩（rank(X) == 4，D14.4）", rank4 == 4,
            f"rank {rank4} / 列 {X4.shape[1]}")
    sign_p = np.sign(s["price_change"].to_numpy(dtype="float64"))
    sign_q = np.sign(s["oi_change"].to_numpy(dtype="float64"))
    ok_map = all(set(zip(sign_p[reg == c], sign_q[reg == c])) == {PQ[c]} for c in CELLS)
    g.check("regime ↔ (P, q) 一一对应（R1=(+,+)、R2=(+,−)、R3=(−,+)、R4=(−,−)）", ok_map)
    mean_y = float(s[Y_WIN].to_numpy(dtype="float64").mean())
    g.check("单位闸门：|mean(winsor_fwd_24h)| < 0.05（小数口径，D14.2）",
            abs(mean_y) < 0.05, f"mean = {mean_y:+.6f}；若误写成百分数会 > 0.05")


def gate_exp1(g: Gate, res1: dict) -> None:
    g.section("1. 实验 1 · 收益·均值（y = winsor_fwd_24h，四格 + 按合约聚类）")
    coef = res1["coef"]
    # 系数（点估计）与聚类无关，照旧对拍 oracle
    exp_b = {"const": -0.0011203151, "P": -0.0000708906,
             "q": -0.0000640939, "Pq": 0.0001558478}
    for nm in sc.FOUR_CELL_NAMES:
        g.near(f"b_{nm}", coef[nm]["estimate"], exp_b[nm])
    did = res1["did"]
    g.near("DiD = 4·b_Pq", did["estimate"], 0.0006233910)
    # 全闸门**唯一**的 SE 锚点：oracle 报告的 DiD SE 分解里的 symbol-only 那一项
    g.near("SE(DiD) 按合约聚类（唯一 SE 锚点）", did["se"], 0.0004656142)
    g.near("R1−R2 = 2(b_q + b_Pq)", res1["r12"]["estimate"], 0.0001835078)
    g.near("R3−R4 = 2(b_q − b_Pq)", res1["r34"]["estimate"], -0.0004398833)
    # 四格饱和：X@b 必须逐格等于格均值（不存 25 万个拟合值，按格还原）
    c0, cP = coef["const"]["estimate"], coef["P"]["estimate"]
    cq, cPq = coef["q"]["estimate"], coef["Pq"]["estimate"]
    fitted = {"R1": c0 + cP + cq + cPq, "R2": c0 + cP - cq - cPq,
              "R3": c0 - cP + cq - cPq, "R4": c0 - cP - cq + cPq}
    dev_fit = max(abs(fitted[c] - res1["cell_mean"][c]) for c in CELLS)
    g.check("四格饱和：系数还原的格均值 = 样本格均值（差 < 1e-12）", dev_fit < 1e-12,
            f"max|Δ| {dev_fit:.1e}")
    dev_did = abs(did["estimate"] - ((res1["cell_mean"]["R1"] - res1["cell_mean"]["R2"])
                                     - (res1["cell_mean"]["R3"] - res1["cell_mean"]["R4"])))
    g.check("DiD = 由格均值算出的 (R1−R2)−(R3−R4)（差 < 1e-12）", dev_did < 1e-12,
            f"|Δ| {dev_did:.1e}")
    # t / p / 区间都由同一个 V 推出，是管线产物（oracle 没给 symbol-only 的这三个
    # 数，所以只记录、不设判据 —— 恒真的闸门等于没闸门）
    g.lines.append(
        f"        └ 记录（不作判据）：t = {did['t']:+.4f}，p = {did['p']:.4f}，"
        f"95% [{1e4 * did['ci_lo']:+.4f}, {1e4 * did['ci_hi']:+.4f}]bp")
    W, p = res1["wald"]
    g.check("χ²(3) 联合检验可算（W ≥ 0，p ∈ (0,1)）", W >= 0.0 and 0.0 < p < 1.0,
            f"W = {W:.6f}, p = {p:.6f}（oracle 未给这个数；判定见 §6）")


def gate_exp2(g: Gate, res2: dict) -> None:
    g.section("2. 实验 2 · 收益·中位数（按小时重抽，整小时带走）")
    g.check("重抽的格序 = R1..R4（下面的列序假设成立）", res2["labels"] == list(CELLS),
            str(res2["labels"]))
    exp_med = {"R1": -0.0060570034, "R2": -0.0044026979,
               "R3": -0.0037700105, "R4": -0.0044589456}
    for c in CELLS:
        r = res2["cells"][c]
        g.near(f"中位数 {c}", r["estimate"], exp_med[c])
        g.check(f"重抽区间含点估计 {c}", r["ci_lo"] <= r["estimate"] <= r["ci_hi"],
                f"[{r['ci_lo']:+.6f}, {r['ci_hi']:+.6f}]，se = {r['se']:.6f}")
    g.near("中位数 DiD = (R1−R2)−(R3−R4)", res2["did"]["estimate"], -0.0023432407)
    g.check(f"重抽 {EVENT.random_draws} 次耗时 ≤ 10s（SPEC §六）", res2["elapsed"] <= 10.0,
            f"{res2['elapsed']:.2f}s")
    n_neg = int(round(res2["share_neg"] * EVENT.random_draws))
    g.check(f"重抽分布 {EVENT.random_draws} 次全为负", n_neg == EVENT.random_draws,
            f"{n_neg}/{EVENT.random_draws} 次为负，boot 中位数 {res2['boot_median']:+.6f}")
    g.check("中位数 DiD 的重抽区间不含 0（上界 < 0）", res2["did"]["ci_hi"] < 0.0,
            f"[{res2['did']['ci_lo']:+.10f}, {res2['did']['ci_hi']:+.10f}]")


def gate_exp3(g: Gate, res3: dict) -> None:
    g.section("3. 实验 3 · 波动（y = log(rv_24h)，四格，不加固定效应，按合约聚类）")
    coef = res3["coef"]
    # 点估计（系数 / 对比 / 格均值）与聚类无关，照旧对拍 oracle
    exp_b = {"const": -2.9819109528, "P": 0.0045137267,
             "q": 0.0252995685, "Pq": -0.0167437593}
    for nm in sc.FOUR_CELL_NAMES:
        g.near(f"b_{nm}", coef[nm]["estimate"], exp_b[nm])
    c_oi, g_int = res3["c"], res3["g"]
    g.near("c = R3−R4 = 2(b_q − b_Pq)", c_oi["estimate"], 0.0840866557)
    g.near("g = (R1−R2)−(R3−R4) = 4·b_Pq", g_int["estimate"], -0.0669750374)
    g.near("exp(c)−1（%）", 100.0 * math.expm1(c_oi["estimate"]), 8.7723, tol=1e-4,
           fmt="%+.4f")
    g.near("exp(g)−1（%）", 100.0 * math.expm1(g_int["estimate"]), -6.4781, tol=1e-4,
           fmt="%+.4f")
    # χ²(3) 的 V 变了 → 数值必然变，不再对拍 137.321246，只断言"仍然显著"并记录新值
    W, p = res3["wald"]
    g.check("χ²(3) 仍然强烈拒绝（H0: P = q = P·q = 0；df = 3）", p < 1e-20,
            f"新值 W = {W:.6f}, p = {p:.4e}"
            "（双向口径的旧值 137.321246 / p = 1.4289e-29 不再是锚点）")
    exp_lrv = {"R1": -2.9688414170, "R2": -2.9859530353,
               "R3": -2.9443813516, "R4": -3.0284680074}
    exp_exp = {"R1": 0.0513628, "R2": 0.0504914, "R3": 0.0526346, "R4": 0.0483897}
    for c in CELLS:
        g.near(f"格均值 log(rv) {c}", res3["cell_mean"][c], exp_lrv[c])
        g.near(f"exp(格均值 log rv) {c}", math.exp(res3["cell_mean"][c]), exp_exp[c],
               tol=1e-7)
    g.near("R3/R4（exp 格均值之比）",
           math.exp(res3["cell_mean"]["R3"] - res3["cell_mean"]["R4"]), 1.0877, tol=5e-5)
    g.near("R1/R2（exp 格均值之比）",
           math.exp(res3["cell_mean"]["R1"] - res3["cell_mean"]["R2"]), 1.0173, tol=5e-5)
    g.lines.append(
        f"        └ 记录（不作判据）：SE(c) = {c_oi['se']:.6f}，t(c) = {c_oi['t']:+.3f}，"
        f"SE(g) = {g_int['se']:.6f}，t(g) = {g_int['t']:+.3f}"
        "（oracle 的 0.011306 / 0.019671 是双向口径，已不适用）")


def gate_exp4(g: Gate, res4: dict, s: pd.DataFrame) -> None:
    g.section("4. 实验 4 · 反转斜率（X = [mu_R1..mu_R4, ls, D2·ls, D3·ls, D4·ls]）")
    rank8 = int(np.linalg.matrix_rank(res4["X"]))
    exp_mu = {"R1": -0.0005591394, "R2": -0.0007733510,
              "R3": -0.0013508360, "R4": -0.0007114631}
    exp_th = {"R1": -0.0007726218, "R2": -0.0007722913,
              "R3": 0.0001286116, "R4": -0.0001726876}
    for c in CELLS:
        g.near(f"mu_{c}", res4["mu"][c]["estimate"], exp_mu[c])
        g.near(f"theta_{c}", res4["theta"][c]["estimate"], exp_th[c])
    g.rel("斜率差 R1−R2", res4["diffs"]["R2"]["estimate"], -3.305e-7, rtol=1e-3)
    g.near("斜率差 R1−R3", res4["diffs"]["R3"]["estimate"], -0.0009012335)
    g.near("斜率差 R1−R4", res4["diffs"]["R4"]["estimate"], -0.0005999342)
    # χ²(3) 的 V 变了 → 数值必然变，不再对拍 2.475038 / p = 0.479819，
    # 只断言"仍然不显著"并记录新值
    W, p = res4["wald"]
    g.check("χ²(3) 仍然不显著（H0: 四条斜率相等，df = 3）", p > 0.05,
            f"新值 W = {W:.6f}, p = {p:.6f}"
            "（双向口径的旧值 2.475038 / p = 0.479819 不再是锚点）")
    th, _ = sc.overreaction_slope(s, Y_WIN, "shock", "regime")
    dev = float(np.abs(th - np.array([res4["theta"][c]["estimate"] for c in CELLS])).max())
    g.check("嵌套参数化的 theta 与逐格 OLS 斜率一致（stats_core.overreaction_slope）",
            dev < 1e-12, f"max|Δ| {dev:.1e}")
    g.lines.append(
        "        └ 记录（不作判据）：SE(theta) = "
        + ", ".join(f"{res4['theta'][c]['se']:.6f}" for c in CELLS)
        + "；z(R1−R3) = %+.3f，z(R1−R4) = %+.3f"
        % (res4["diffs"]["R3"]["t"], res4["diffs"]["R4"]["t"])
        + "（oracle 的 SE / z 是双向口径，已不适用）")


def gate_descriptive(g: Gate, desc: pd.DataFrame) -> None:
    g.section("5. 描述层 · 四格底数（headline, h=24, ok_24h）")
    d = desc.set_index("cell")
    exp_n = {"R1": 74875, "R2": 50519, "R3": 44585, "R4": 85828}
    exp_mean = {"R1": -0.0010994518, "R2": -0.0012829596,
                "R3": -0.0012693662, "R4": -0.0008294829}
    exp_med = {"R1": -0.0060570034, "R2": -0.0044026979,
               "R3": -0.0037700105, "R4": -0.0044589456}
    exp_hit = {"R1": 0.46012688, "R2": 0.48470872, "R3": 0.48758551, "R4": 0.49817076}
    exp_hitn = {"R1": 0.41856427, "R2": 0.42946218, "R3": 0.56191544, "R4": 0.57311134}
    exp_rv = {"R1": 0.060804, "R2": 0.061640, "R3": 0.065527, "R4": 0.057308}
    for c in CELLS:
        g.near(f"n {c}", float(d.loc[c, "n"]), exp_n[c], tol=0, fmt="%.0f")
        g.near(f"mean(winsor) {c}", d.loc[c, "mean_winsor"], exp_mean[c])
        g.near(f"median(winsor) {c}", d.loc[c, "median_winsor"], exp_med[c])
        g.near(f"命中率(raw, hit_24h) {c}", d.loc[c, "hit_raw"], exp_hit[c], tol=1e-7,
               anchor=False)
        g.near(f"命中率(中性, d·winsor>0) {c}", d.loc[c, "hit_neutral"], exp_hitn[c],
               tol=1e-7, anchor=False)
        g.near(f"mean rv_24h {c}", d.loc[c, "mean_rv"], exp_rv[c], tol=1e-5, fmt="%.6f")

    def did_of(col: str) -> float:
        return (float(d.loc["R1", col]) - float(d.loc["R2", col])) \
            - (float(d.loc["R3", col]) - float(d.loc["R4", col]))

    g.near("均值 DiD（winsor）", did_of("mean_winsor"), 0.0006233910)
    g.near("均值 DiD（raw）", did_of("mean_raw"), 0.0014941402)
    g.near("均值 DiD（excess）", did_of("mean_excess"), 0.0026190077)
    g.near("中位数 DiD（winsor）", did_of("median_winsor"), -0.0023432407)
    g.near("中位数 DiD（raw）", did_of("median_raw"), -0.0039756894)
    g.near("中位数 DiD（excess）", did_of("median_excess"), -0.0023432407)


def gate_verdict(g: Gate, res1: dict, res2: dict, res3: dict, res4: dict) -> None:
    g.section("6. 判定（普通显著性；等价性检验已取消，D15.2）")
    did = res1["did"]
    g.check("实验 1 均值：DiD 区间跨 0 → 测不出增量",
            did["ci_lo"] < 0.0 < did["ci_hi"] and did["p"] > 0.05,
            f"DiD = {1e4 * did['estimate']:+.4f}bp，SE = {1e4 * did['se']:.4f}bp，"
            f"t = {did['t']:+.3f}，p = {did['p']:.4f}，"
            f"95% [{1e4 * did['ci_lo']:+.4f}, {1e4 * did['ci_hi']:+.4f}]bp")
    W1, p1 = res1["wald"]
    g.check("实验 1 均值：χ²(3) 联合检验不显著（p > 0.05）", p1 > 0.05,
            f"W = {W1:.6f}, p = {p1:.6f}（P = q = Pq = 0 ⟺ 四格均值全相等）")
    m = res2["did"]
    g.check("实验 2 中位数：区间不含 0 → 有增量，且符号与均值相反（负）",
            m["ci_hi"] < 0.0 < did["estimate"],
            f"DiD = {1e4 * m['estimate']:+.4f}bp，"
            f"95% [{1e4 * m['ci_lo']:+.4f}, {1e4 * m['ci_hi']:+.4f}]bp，"
            f"{int(round(res2['share_neg'] * EVENT.random_draws))}/{EVENT.random_draws} 次为负")
    W3, p3 = res3["wald"]
    g.check("实验 3 波动：χ²(3) 强烈拒绝（描述性，未控同刻市场波动）", p3 < 1e-20,
            f"W = {W3:.6f}, p = {p3:.4e}；c = {res3['c']['estimate']:+.6f} → "
            f"{100.0 * math.expm1(res3['c']['estimate']):+.4f}%")
    W4, p4 = res4["wald"]
    g.check("实验 4 斜率：χ²(3) 不显著 → 四个斜率没有差别（D15.3）", p4 > 0.05,
            f"W = {W4:.6f}, p = {p4:.6f}")


# ============================================================ 9. main
def main() -> int:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    s, n_headline = load_sample()
    cS = symbol_codes(s)
    log(f"聚类维度：合约 symbol，{int(np.unique(cS).size)} 簇")
    y = s[Y_WIN].to_numpy(dtype="float64")
    y_raw = s[Y_RAW].to_numpy(dtype="float64")
    y_exc = s[Y_EXC].to_numpy(dtype="float64")
    y_rv = s[Y_RV].to_numpy(dtype="float64")
    y_logrv = np.log(y_rv)
    X4, names4 = sc.four_cell_design(s)
    log(f"四格设计 {X4.shape}，列 {names4}")

    res1 = experiment1(s, y, cS, X4, names4)
    log(f"实验 1（收益·均值）：DiD = {res1['did']['estimate']:+.10f}，"
        f"SE = {res1['did']['se']:.10f}，t = {res1['did']['t']:+.3f}")
    res3 = experiment3(s, y_logrv, cS, X4, names4)
    log(f"实验 3（波动）：chi2(3) = {res3['wald'][0]:.6f}，c = {res3['c']['estimate']:+.10f}")
    res4 = experiment4(s, y, cS)
    log(f"实验 4（斜率）：chi2(3) = {res4['wald'][0]:.6f}，p = {res4['wald'][1]:.6f}")
    res2 = experiment2(s, y)
    log(f"实验 2（中位数）：DiD = {res2['did']['estimate']:+.10f}，"
        f"{EVENT.random_draws} 次重抽 {res2['elapsed']:.2f}s")
    desc = descriptive(s, y, y_raw, y_exc, y_rv)

    for df, name in ((build_return_table(res1, res2), "confirmatory_return"),
                     (build_vol_table(res3), "confirmatory_vol"),
                     (build_slope_table(res4), "confirmatory_slope"),
                     (desc, "descriptive_four_cell")):
        write_table(df, name)

    gate = Gate(f"event_study · confirmatory · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    gate.lines.append(f"样本：headline(in_universe) & {OK}，freq={FREQ}，h={H}；"
                      "内部单位一律小数（D14.2），×100 即百分数（波动表为 log(rv) 尺度）")
    gate.lines.append("推断：CGM 单向聚类，**只按合约 symbol**（"
                      "V = bread·(Σ_g s_g s_g')·bread，无小样本校正）；双向聚类已删除，"
                      "时刻维度不进入协方差；"
                      f"中位数按小时有放回重抽（{EVENT.random_draws} 次，"
                      f"seed={EVENT.random_seed}）")
    gate.lines.append("容差：按 oracle 自己印的位数设（10 位小数 → 1e-6；8 位 → 1e-7；"
                      "7 位 → 1e-7；6 位 → 1e-5；4 位 → 1e-4；3 位 t → 5e-4），"
                      "每行注明 |Δ| / rel")
    gate_sample(gate, s, n_headline, cS, X4)
    gate_exp1(gate, res1)
    gate_exp2(gate, res2)
    gate_exp3(gate, res3)
    gate_exp4(gate, res4, s)
    gate_descriptive(gate, desc)
    gate_verdict(gate, res1, res2, res3, res4)
    footer = ("oracle 出处：phase3_event/_rebuild/_oracle_four_cell_results.md（独立实现，"
              "不 import stats_core；其中双向 SE 与双向 χ² 自 2026-10-27 起只作历史）；"
              "样本与口径见 DECISIONS 的 D13–D15 与 SPEC v2。"
              "按合约口径的独立复算见 _rebuild/_oracle_oneway_results.md："
              "交接时 143 项逐位一致（max |Δ| 1.8e-15），但不进闸门 —— 只钉 DiD 那一个 SE 锚点")
    txt = gate.text(footer)
    CHECKS_PATH.write_text(txt, encoding="utf-8")
    print(txt)
    log(f"闸门写盘 {CHECKS_PATH}")
    return 0 if gate.n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
