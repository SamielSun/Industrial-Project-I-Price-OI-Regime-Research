"""Phase 3 · event_study —— 表与图

⚠️ 本文件是 **v1 实现**，正在按 PHASE3_GUIDANCE.md（v2）重建。逐函数的状态：

| 函数 | v2 里的去向 | 状态 |
|---|---|---|
| `experiment_outcomes` / `gate_outcomes` | D1 + D2（描述层） | 保留，**要删 p_sig / p_bh / t 三列** |
| `experiment_path_risk` | D3 | 保留 |
| `experiment_event_path` | D4 | 保留（已加 se_cum） |
| `experiment_by_symbol` / `experiment_by_state` | D6 | 保留，**by_state 要去掉 64 个未入家族的 did** |
| `experiment_ic` | D7 | 保留，**要加"纯价格动量"一列并排** |
| `experiment_baselines` / `experiment_random_timing` | D5 + C5 | **重写**：随机对照改成"同刻同波动状态的随机合约"，funding 补 extreme 档与 SE |
| `experiment_regressions` | C1 / C2 | **重写**：换成六格模型（价格符号 × OI 三态）+ 市场中性 + 截尾 + block bootstrap |
| `experiment_threshold_scan` | R1 | **重写**：一维扫描改为 6×6 二维网格 |

v2 待新增（尚不存在）：市场中性化、1%/99% 截尾、48h moving-block bootstrap、六个确认性检验、C4 过反应斜率、R2 价格十分位匹配、R4 安慰剂 `fwd(-h)`。

用法（v1）：
    python phase3_event/event_study.py --only outcomes
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from statistics import NormalDist

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402

EVENT = cfg_mod.EVENT
HORIZONS = tuple(EVENT.horizons)
REGIMES = ("R1", "R2", "R3", "R4")
SAMPLES = ("headline", "full")
SIGN = {"R1": 1.0, "R2": 1.0, "R3": -1.0, "R4": -1.0}
ND = NormalDist()
CUR_FREQ = "1h"
T_START = time.time()


def table_dir(out_root: Path) -> Path:
    d = out_root / "tables" / f"freq={CUR_FREQ}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.0f}s] {msg}", flush=True)


# ---------------------------------------------------------------- 估计量
def mean_se_2way(y: np.ndarray, g1: np.ndarray, g2: np.ndarray) -> tuple[float, float]:
    """均值的双向聚类标准误（CGM）。g1 = 决策时刻，g2 = 合约。"""
    y = np.asarray(y, dtype="float64")
    n = y.size
    if n == 0:
        return float("nan"), float("nan")
    m = float(y.mean())
    e = y - m
    c1 = g1 if g1.dtype.kind in "iu" else pd.factorize(g1, sort=False)[0].astype("int64")
    c2 = g2 if g2.dtype.kind in "iu" else pd.factorize(g2, sort=False)[0].astype("int64")
    if c1.max() < 1 or c2.max() < 1:
        raise SystemExit("双向聚类要求两个维度都至少 2 簇（CGM 在单簇时会抵消成 0）")
    both = c1 * (c2.max() + 1) + c2

    def meat(codes: np.ndarray) -> float:
        s = np.bincount(codes, weights=e)
        return float((s ** 2).sum())

    var = (meat(c1) + meat(c2) - meat(both)) / n ** 2
    return m, float(np.sqrt(max(var, 0.0)))


def p_two_sided(t: float) -> float:
    if not np.isfinite(t):
        return float("nan")
    return float(2.0 * (1.0 - ND.cdf(abs(t))))


def bh(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype="float64")
    m = p.size
    o = np.argsort(p)
    q = np.empty(m)
    q[o] = np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]
    return np.minimum(q, 1.0)


# ---------------------------------------------------------------- 数据
def load_events(out_root: Path, freq: str) -> pd.DataFrame:
    p = out_root / "events" / f"events_{freq}.parquet"
    if not p.exists():
        raise SystemExit(f"找不到事件表：{p}（先跑 build_event_table.py）")
    d = pd.read_parquet(p)
    log(f"事件表 {len(d):,} 行 × {d.shape[1]} 列")
    return d


# ---------------------------------------------------------------- 实验 1–4
def experiment_outcomes(ev: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    rows = []
    for sample in SAMPLES:
        s = ev if sample == "full" else ev[ev["in_universe"].to_numpy(dtype=bool)]
        if not len(s):
            continue
        for regime in REGIMES:
            cell = s[s["regime"] == regime]
            if not len(cell):
                continue
            for h in HORIZONS:
                ok = cell[f"ok_{h}h"].to_numpy(dtype=bool)
                fwd = cell[f"fwd_{h}h"].to_numpy(dtype="float64")[ok]
                n = int(ok.sum())
                row = {
                    "sample": sample, "regime": regime, "h": h,
                    "n": n, "n_invalid": int(len(cell) - n),
                    "mean_fwd": float(fwd.mean()) if n else np.nan,
                    "median_fwd": float(np.median(fwd)) if n else np.nan,
                    "sd_fwd": float(fwd.std(ddof=1)) if n > 1 else np.nan,
                }
                y = cell[f"y_sig_{h}h"].to_numpy(dtype="float64")[ok]
                g1 = cell["hour"].to_numpy()[ok]
                g2 = cell["symbol"].to_numpy()[ok]
                m_fwd, se_fwd = mean_se_2way(fwd, g1, g2)
                m_sig, se_sig = mean_se_2way(y, g1, g2)
                t_sig = m_sig / se_sig if se_sig > 0 else np.nan
                row.update({
                    "se_tw": se_fwd,
                    "t": m_fwd / se_fwd if se_fwd > 0 else np.nan,
                    "ci_lo": m_fwd - 1.96 * se_fwd,
                    "ci_hi": m_fwd + 1.96 * se_fwd,
                    "mean_sig": m_sig, "se_sig": se_sig, "t_sig": t_sig,
                    "p_sig": p_two_sided(t_sig),
                })
                hit = cell[f"hit_{h}h"].to_numpy(dtype="float64")[ok]
                cont = cell[f"cont_{h}h"].to_numpy(dtype="float64")[ok]
                rev = cell[f"rev_{h}h"].to_numpy(dtype="float64")[ok]
                flat = cell[f"flat_{h}h"].to_numpy(dtype="float64")[ok]
                m_hit, se_hit = mean_se_2way(hit, g1, g2)
                m_dif, se_dif = mean_se_2way(cont - rev, g1, g2)
                rv = cell[f"rv_{h}h"].to_numpy(dtype="float64")[ok]
                row.update({
                    "hit_rate": m_hit, "se_hit": se_hit,
                    "p_cont": float(cont.mean()), "p_rev": float(rev.mean()), "p_flat": float(flat.mean()),
                    "p_cont_minus_rev": m_dif,
                    "t_cont_rev": m_dif / se_dif if se_dif > 0 else np.nan,
                    "mean_rv": float(rv.mean()), "median_rv": float(np.median(rv)),
                })
                rows.append(row)

    df = pd.DataFrame(rows)
    p = df["p_sig"].to_numpy(dtype="float64")
    finite = np.isfinite(p)
    df["p_bh"] = np.nan
    df.loc[finite, "p_bh"] = bh(p[finite])
    df["regime"] = pd.Categorical(df["regime"], REGIMES, ordered=True)
    df = df.sort_values(["sample", "regime", "h"]).reset_index(drop=True)
    df["regime"] = df["regime"].astype(str)

    out = table_dir(out_root)
    df.to_parquet(out / "outcomes.parquet", index=False)
    df.to_csv(out / "outcomes.csv", index=False, encoding="utf-8")
    log(f"写出 {out / 'outcomes.parquet'}（{len(df)} 行）")
    return df


# ---------------------------------------------------------------- 闸门
def gate_outcomes(df: pd.DataFrame) -> int:
    lines = [f"event_study · outcomes · {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    bad = 0

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数", len(df) == 32, f"{len(df)} / 期望 32 = 2x4x4")
    if CUR_FREQ != "1h":
        body = "\n".join(lines) + "\n"
        print(body); print(f"[gate] outcomes: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
        return bad
    want_n = {"R1": (74_959, 267_080), "R2": (50_564, 184_686),
              "R3": (44_623, 164_126), "R4": (85_933, 307_343)}
    for regime, (nh, nf) in want_n.items():
        sel = df[(df.regime == regime) & (df.h == 1)]
        gh = int(sel[sel["sample"] == "headline"][["n", "n_invalid"]].to_numpy().sum())
        gf = int(sel[sel["sample"] == "full"][["n", "n_invalid"]].to_numpy().sum())
        check(f"{regime} 样本量 headline/full", (gh, gf) == (nh, nf), f"{gh:,}/{gf:,} 期望 {nh:,}/{nf:,}")
    check("每格 n > 0", bool((df.n > 0).all()), f"最小 n = {int(df.n.min()):,}")
    check("每格 se_sig > 0", bool((df.se_sig > 0).all()), f"最小 se = {df.se_sig.min():.3e}")

    sign = df.regime.map(SIGN).to_numpy()
    dev = float(np.nanmax(np.abs(df.mean_sig.to_numpy() - sign * df.mean_fwd.to_numpy())))
    check("mean_sig = ±mean_fwd", dev < 1e-12, f"最大偏差 {dev:.2e}")

    dev = float(np.nanmax(np.abs(df.hit_rate.to_numpy() - df.p_cont.to_numpy())))
    check("hit_rate = p_cont", dev < 1e-12, f"最大偏差 {dev:.2e}")

    tot = (df.p_cont + df.p_rev + df.p_flat).to_numpy()
    check("p_cont+p_rev+p_flat = 1", float(np.abs(tot - 1).max()) < 1e-9, f"最大偏差 {np.abs(tot - 1).max():.2e}")

    finite = df.p_sig.notna().to_numpy()
    order = np.argsort(df.p_sig.to_numpy()[finite])
    p_sorted = df.p_sig.to_numpy()[finite][order]
    q_sorted = df.p_bh.to_numpy()[finite][order]
    check("p_bh 单调且 >= p", bool(np.all(np.diff(q_sorted) >= -1e-12) and np.all(q_sorted >= p_sorted - 1e-12)),
          f"q 最小 {q_sorted.min():.3e} · 最大 {q_sorted.max():.3f}")
    n_sig = int((df.p_bh < 0.05).sum())
    lines.append(f"  [note] BH 后 p_bh < 0.05 的格子: {n_sig} / {int(finite.sum())}")

    body = "\n".join(lines) + "\n"
    docs = Path("data/06_event_study/docs")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / f"step5_checks_outcomes_{CUR_FREQ}.txt").write_text(body, encoding="utf-8")
    print(body)
    print(f"[gate] event_study outcomes: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 全量面板（基准用）
PASS_COLS = [
    "symbol", "ts_end", "regime", "excl_reason", "price_change", "oi_change",
    "price_thr", "oi_thr", "in_universe", "mkt_vol_state",
    "funding_negative", "funding_neutral", "funding_high",
]


def load_panel_and_labels(in_root: Path, out_root: Path, freq: str) -> pd.DataFrame:
    """标签表全量 + 前向面板（只取基准要用的列）。约 725 万行。"""
    lab_files = sorted((in_root / "05_regime" / "regime_labels" / f"freq={freq}").rglob("*.parquet"))
    labels = pd.concat([pd.read_parquet(p, columns=PASS_COLS) for p in lab_files], ignore_index=True)
    fwd_cols = ["symbol", "ts_end"] + [f"{m}_{h}h" for h in HORIZONS for m in ("fwd", "rv", "ok")]
    fwd_files = sorted((out_root / "forward" / f"freq={freq}").rglob("*.parquet"))
    code = (labels.ts_end.dt.year * 100 + labels.ts_end.dt.month).astype("int64")
    by_month = {int(k): v for k, v in labels.groupby(code, sort=False)}
    log(f"标签 {len(labels):,} 行、{len(by_month)} 个月，开始 join {len(fwd_files)} 个前向分区")
    parts = []
    for p in fwd_files:
        ym = int(p.stem.split("=")[1].replace("-", ""))
        lab_m = by_month.get(ym)
        if lab_m is None:
            continue
        f = pd.read_parquet(p, columns=fwd_cols)
        keep = lab_m.merge(f, on=["symbol", "ts_end"], how="inner", validate="1:1")
        parts.append(keep)
    out = pd.concat(parts, ignore_index=True)
    del parts
    if len(out) != len(labels):
        raise SystemExit(f"面板 join 行数错：{len(out):,} != 标签 {len(labels):,}")
    out["sym_code"] = pd.factorize(out.symbol, sort=False)[0].astype("int64")
    t0 = pd.Timestamp("2021-12-01", tz="UTC")
    out["hour"] = ((out.ts_end - t0).dt.total_seconds() // 3600).astype("int64")
    log(f"全量面板 {len(out):,} 行")
    return out


def cell_stats(sub: pd.DataFrame, h: int, d_src: str) -> dict:
    """一个格子的全部统计量。d_src in price / oi / none。"""
    ok = sub[f"ok_{h}h"].to_numpy(dtype=bool)
    fwd = sub[f"fwd_{h}h"].to_numpy(dtype="float64")[ok]
    n = int(ok.sum())
    row = {
        "n_pop": int(len(sub)), "n": n, "n_invalid": int(len(sub) - n),
        "mean_fwd": float(fwd.mean()) if n else np.nan,
        "median_fwd": float(np.median(fwd)) if n else np.nan,
        "mean_rv": float(sub[f"rv_{h}h"].to_numpy(dtype="float64")[ok].mean()) if n else np.nan,
    }
    g1 = sub["hour"].to_numpy()[ok]
    g2 = sub["sym_code"].to_numpy()[ok]
    m, se = mean_se_2way(fwd, g1, g2)
    row.update({"se_tw": se, "t": m / se if se > 0 else np.nan,
                "ci_lo": m - 1.96 * se, "ci_hi": m + 1.96 * se})
    pc = sub["price_change"].to_numpy(dtype="float64")[ok]
    sig = np.sign(fwd)
    if d_src == "none":
        row.update({"mean_sig": np.nan, "se_sig": np.nan, "t_sig": np.nan, "p_sig": np.nan,
                    "hit_rate": np.nan, "se_hit": np.nan, "p_cont": np.nan, "p_rev": np.nan,
                    "p_flat": np.nan, "p_cont_minus_rev": np.nan, "t_cont_rev": np.nan})
        return row
    d = np.sign(pc) if d_src == "price" else np.sign(sub["oi_change"].to_numpy(dtype="float64")[ok])
    y = d * fwd
    m_sig, se_sig = mean_se_2way(y, g1, g2)
    t_sig = m_sig / se_sig if se_sig > 0 else np.nan
    hit = ((sig == d) & (fwd != 0)).astype("float64")
    cont = (sig == np.sign(pc)).astype("float64")
    rev = (sig == -np.sign(pc)).astype("float64")
    flat = (fwd == 0).astype("float64")
    m_hit, se_hit = mean_se_2way(hit, g1, g2)
    m_dif, se_dif = mean_se_2way(cont - rev, g1, g2)
    row.update({
        "mean_sig": m_sig, "se_sig": se_sig, "t_sig": t_sig, "p_sig": p_two_sided(t_sig),
        "hit_rate": m_hit, "se_hit": se_hit,
        "p_cont": float(cont.mean()), "p_rev": float(rev.mean()), "p_flat": float(flat.mean()),
        "p_cont_minus_rev": m_dif, "t_cont_rev": m_dif / se_dif if se_dif > 0 else np.nan,
    })
    return row



def experiment_random_timing(full: pd.DataFrame, reps: int) -> pd.DataFrame:
    """随机时点基准：按状态分 4 组，每组 1000 轮层内无放回抽时刻。"""
    ok = full[full.excl_reason == "ok"]
    rng = np.random.default_rng(EVENT.random_seed)
    rows = []
    for sample in SAMPLES:
        base = ok if sample == "full" else ok[ok.in_universe.to_numpy(dtype=bool)]
        base = base.reset_index(drop=True)
        state_code = pd.factorize(base.mkt_vol_state, sort=False)[0]
        st_all = pd.factorize(base.sym_code.to_numpy() * 100 + state_code, sort=False)[0]
        pos_by = base.groupby(st_all, sort=True).indices
        fwd = {h: base[f"fwd_{h}h"].to_numpy(dtype="float64") for h in HORIZONS}
        for regime in REGIMES:
            ev_pos = np.flatnonzero((base.regime == regime).to_numpy())
            if not ev_pos.size:
                continue
            d = np.sign(base.price_change.to_numpy(dtype="float64")[ev_pos])
            st_ev = st_all[ev_pos]
            order = np.argsort(st_ev, kind="stable")
            d_sorted = d[order]
            uniq, counts = np.unique(st_ev[order], return_counts=True)
            sums = {h: np.empty(reps) for h in HORIZONS}
            cnts = {h: np.empty(reps) for h in HORIZONS}
            buf = {h: np.empty(ev_pos.size) for h in HORIZONS}
            for b in range(reps):
                off = 0
                for s, n in zip(uniq, counts):
                    sel = rng.choice(pos_by[s], size=int(n), replace=False)
                    for h in HORIZONS:
                        buf[h][off:off + n] = fwd[h][sel]
                    off += int(n)
                for h in HORIZONS:
                    y = d_sorted * buf[h]
                    v = np.isfinite(y)
                    sums[h][b] = y[v].sum()
                    cnts[h][b] = v.sum()
            for h in HORIZONS:
                stat = sums[h] / cnts[h]
                rows.append({
                    "sample": sample, "group": f"random_{regime}", "d_src": "price", "h": h,
                    "n_pop": int(ev_pos.size), "n": int(ev_pos.size), "n_invalid": 0,
                    "mean_sig": float(np.median(stat)),
                    "mean_sig_p5": float(np.percentile(stat, 5)),
                    "mean_sig_p95": float(np.percentile(stat, 95)),
                    "mean_fwd": np.nan, "median_fwd": np.nan, "mean_rv": np.nan,
                    "se_tw": np.nan, "t": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                    "se_sig": np.nan, "t_sig": np.nan, "p_sig": np.nan,
                    "hit_rate": np.nan, "se_hit": np.nan,
                    "p_cont": np.nan, "p_rev": np.nan, "p_flat": np.nan,
                    "p_cont_minus_rev": np.nan, "t_cont_rev": np.nan,
                })
            log(f"  随机时点 {sample}/{regime}: {reps} 轮完成")
    return pd.DataFrame(rows)

def experiment_baselines(full: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    ok = full[full.excl_reason == "ok"]
    groups = [
        ("R1", "price", lambda d: d[d.regime == "R1"]),
        ("R2", "price", lambda d: d[d.regime == "R2"]),
        ("R3", "price", lambda d: d[d.regime == "R3"]),
        ("R4", "price", lambda d: d[d.regime == "R4"]),
        ("price_only", "price", lambda d: d[np.abs(d.price_change) > d.price_thr]),
        ("oi_only", "oi", lambda d: d[np.abs(d.oi_change) > d.oi_thr]),
        ("funding_low", "none", lambda d: d[d.funding_negative]),
        ("funding_mid", "none", lambda d: d[d.funding_neutral]),
        ("funding_high", "none", lambda d: d[d.funding_high]),
    ]
    rows = []
    for sample in SAMPLES:
        base = ok if sample == "full" else ok[ok["in_universe"].to_numpy(dtype=bool)]
        for name, d_src, sel in groups:
            sub = sel(base)
            for h in HORIZONS:
                r = {"sample": sample, "group": name, "d_src": d_src, "h": h}
                r.update(cell_stats(sub, h, d_src))
                rows.append(r)
    df = pd.DataFrame(rows)
    df["mean_sig_p5"] = np.nan
    df["mean_sig_p95"] = np.nan
    rand = experiment_random_timing(full, int(EVENT.random_draws))
    df = pd.concat([df, rand], ignore_index=True)
    df = df.sort_values(["sample", "h", "group"]).reset_index(drop=True)
    out = table_dir(out_root)
    df.to_parquet(out / "baselines.parquet", index=False)
    df.to_csv(out / "baselines.csv", index=False, encoding="utf-8")
    log(f"写出 baselines.parquet（{len(df)} 行）")
    return df


def gate_baselines(df: pd.DataFrame) -> int:
    lines = [f"event_study · baselines · {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    bad = 0

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数", len(df) == 104, f"{len(df)} / 期望 104 = 13 组 x 4 前向期 x 2 样本")
    rnd = df[df.group.str.startswith("random_")]
    check("随机行 32", len(rnd) == 32, str(len(rnd)))
    check("随机行 p5 <= 中位数 <= p95",
          bool((rnd.mean_sig_p5 <= rnd.mean_sig).all() and (rnd.mean_sig <= rnd.mean_sig_p95).all()),
          f"例：{rnd.iloc[0].mean_sig_p5:.5f} <= {rnd.iloc[0].mean_sig:.5f} <= {rnd.iloc[0].mean_sig_p95:.5f}")
    if CUR_FREQ != "1h":
        body = "\n".join(lines) + "\n"
        print(body); print(f"[gate] baselines: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
        return bad
    for sample, want_p, want_o in (("full", 2_041_947, 2_001_052), ("headline", 555_012, 546_440)):
        s = df[(df["sample"] == sample) & (df.h == 1)]
        got_p = int(s[s.group == "price_only"].n_pop.iloc[0])
        got_o = int(s[s.group == "oi_only"].n_pop.iloc[0])
        check(f"{sample} 纯价格 n_pop", got_p == want_p, f"{got_p:,} / 期望 {want_p:,}")
        check(f"{sample} 纯 OI n_pop", got_o == want_o, f"{got_o:,} / 期望 {want_o:,}")
    tot = int(df[(df["sample"] == "full") & (df.h == 1) & df.group.str.startswith("funding")].n_pop.sum())
    check("funding 三档覆盖", tot == 7_000_165, f"{tot:,} / 期望 7,000,165（余 10,624 行无状态）")
    body = "\n".join(lines) + "\n"
    docs = Path("data/06_event_study/docs")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / f"step6_checks_baselines_{CUR_FREQ}.txt").write_text(body, encoding="utf-8")
    print(body)
    print(f"[gate] event_study baselines: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad



# ---------------------------------------------------------------- 工具：带聚类的 OLS
def ols_cgm(X: np.ndarray, y: np.ndarray, g1: np.ndarray, g2: np.ndarray):
    XtXi = np.linalg.pinv(X.T @ X)
    b = XtXi @ (X.T @ y)
    u = y - X @ b
    Xu = X * u[:, None]
    c1 = g1 if g1.dtype.kind in "iu" else pd.factorize(g1, sort=False)[0]
    c2 = g2 if g2.dtype.kind in "iu" else pd.factorize(g2, sort=False)[0]
    both = c1 * (int(c2.max()) + 1) + c2

    def meat(codes):
        M = np.zeros((int(codes.max()) + 1, X.shape[1]))
        np.add.at(M, codes, Xu)
        return M.T @ M

    V = XtXi @ (meat(c1) + meat(c2) - meat(both)) @ XtXi
    return b, np.sqrt(np.maximum(np.diag(V), 0.0))


def m3_did(sub: pd.DataFrame, h: int) -> tuple[float, float]:
    """在子样本上拟合 M3，返回 g 与其聚类标准误。"""
    ok = sub[f"ok_{h}h"].to_numpy(dtype=bool)
    fwd = sub[f"fwd_{h}h"].to_numpy(dtype="float64")[ok]
    P = (sub["price_change"].to_numpy(dtype="float64")[ok] > 0).astype("float64")
    O = (sub["oi_change"].to_numpy(dtype="float64")[ok] > 0).astype("float64")
    X = np.column_stack([np.ones_like(P), P, O, P * O])
    g1 = sub["hour"].to_numpy()[ok]
    g2 = sub["sym_code"].to_numpy()[ok] if "sym_code" in sub else sub["symbol"].to_numpy()[ok]
    b, se = ols_cgm(X, fwd, g1, g2)
    return float(b[3]), float(se[3])


# ---------------------------------------------------------------- 实验 5：路径风险
def experiment_path_risk(ev: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    rows = []
    for sample in SAMPLES:
        s = ev if sample == "full" else ev[ev["in_universe"].to_numpy(dtype=bool)]
        for regime in REGIMES:
            cell = s[s["regime"] == regime]
            for h in HORIZONS:
                ok = cell[f"ok_{h}h"].to_numpy(dtype=bool)
                n = int(ok.sum())
                mfe = cell[f"mfe_{h}h"].to_numpy(dtype="float64")[ok]
                mae = cell[f"mae_{h}h"].to_numpy(dtype="float64")[ok]
                mdd = cell[f"mdd_{h}h"].to_numpy(dtype="float64")[ok]
                q = lambda a: [float(np.percentile(a, p)) for p in (10, 50, 90)]
                mfe_q, mae_q, mdd_q = q(mfe), q(mae), q(mdd)
                rows.append({
                    "sample": sample, "regime": regime, "h": h, "n": n,
                    "n_invalid": int(len(cell) - n),
                    "mfe_mean": float(mfe.mean()), "mfe_p10": mfe_q[0], "mfe_p50": mfe_q[1], "mfe_p90": mfe_q[2],
                    "mae_mean": float(mae.mean()), "mae_p10": mae_q[0], "mae_p50": mae_q[1], "mae_p90": mae_q[2],
                    "mdd_mean": float(mdd.mean()), "mdd_p10": mdd_q[0], "mdd_p50": mdd_q[1], "mdd_p90": mdd_q[2],
                    "p_mfe_ge_absmae": float((mfe >= np.abs(mae)).mean()),
                    "mfe_over_absmae": float(mfe.mean() / abs(mae.mean())) if mae.mean() < 0 else np.nan,
                })
    df = pd.DataFrame(rows)
    out = table_dir(out_root)
    df.to_parquet(out / "path_risk.parquet", index=False)
    df.to_csv(out / "path_risk.csv", index=False, encoding="utf-8")
    log(f"写出 path_risk.parquet（{len(df)} 行）")
    return df


def gate_path_risk(df: pd.DataFrame) -> int:
    bad = 0
    lines = ["path_risk", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数 32", len(df) == 32, str(len(df)))
    check("mdd <= 0", bool((df.mdd_mean <= 0).all()), f"最大 {df.mdd_mean.max():.2e}")
    check("mfe >= 0", bool((df.mfe_mean >= 0).all()), f"最小 {df.mfe_mean.min():.2e}")
    check("mae <= 0", bool((df.mae_mean <= 0).all()), f"最大 {df.mae_mean.max():.2e}")
    print("\n".join(lines))
    print(f"[gate] path_risk: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 实验 9：按合约
def experiment_by_symbol(ev: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    rows = []
    for sample in SAMPLES:
        s = ev if sample == "full" else ev[ev["in_universe"].to_numpy(dtype=bool)]
        for (sym, regime), cell in s.groupby(["symbol", "regime"], sort=True):
            for h in HORIZONS:
                ok = cell[f"ok_{h}h"].to_numpy(dtype=bool)
                n = int(ok.sum())
                if n == 0:
                    continue
                fwd = cell[f"fwd_{h}h"].to_numpy(dtype="float64")[ok]
                y = cell[f"y_sig_{h}h"].to_numpy(dtype="float64")[ok]
                rows.append({
                    "sample": sample, "symbol": sym, "regime": regime, "h": h,
                    "n": n, "n_invalid": int(len(cell) - n),
                    "mean_fwd": float(fwd.mean()), "mean_sig": float(y.mean()),
                    "hit_rate": float(cell[f"hit_{h}h"].to_numpy(dtype="float64")[ok].mean()),
                })
    df = pd.DataFrame(rows)
    out = table_dir(out_root)
    df.to_parquet(out / "by_symbol.parquet", index=False)
    log(f"写出 by_symbol.parquet（{len(df)} 行）")
    return df


def gate_by_symbol(df: pd.DataFrame, ev: pd.DataFrame) -> int:
    bad = 0
    lines = ["by_symbol", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数 <= 8,544", len(df) <= 8544, str(len(df)))
    tot = df[(df.h == 1)].groupby("sample")["n"].sum()
    want = {"full": 923235, "headline": 256079}
    for k, v in want.items():
        check(f"{k} 事件数", int(tot.get(k, 0)) <= v, f"{int(tot.get(k,0)):,} <= {v:,}（n 已剔除无效）")
    print("\n".join(lines))
    print(f"[gate] by_symbol: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 实验 10：按市场状态
def experiment_by_state(ev: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    rows = []
    for sample in SAMPLES:
        s = ev if sample == "full" else ev[ev["in_universe"].to_numpy(dtype=bool)]
        for state, block in s.groupby("mkt_vol_state", sort=True):
            for regime in REGIMES:
                cell = block[block["regime"] == regime]
                for h in HORIZONS:
                    ok = cell[f"ok_{h}h"].to_numpy(dtype=bool)
                    n = int(ok.sum())
                    if n == 0:
                        continue
                    fwd = cell[f"fwd_{h}h"].to_numpy(dtype="float64")[ok]
                    y = cell[f"y_sig_{h}h"].to_numpy(dtype="float64")[ok]
                    rows.append({
                        "sample": sample, "mkt_vol_state": state, "regime": regime, "h": h,
                        "n": n, "n_invalid": int(len(cell) - n),
                        "mean_fwd": float(fwd.mean()), "mean_sig": float(y.mean()),
                        "hit_rate": float(cell[f"hit_{h}h"].to_numpy(dtype="float64")[ok].mean()),
                        "mean_rv": float(cell[f"rv_{h}h"].to_numpy(dtype="float64")[ok].mean()),
                    })
            for h in HORIZONS:
                g, se = m3_did(block, h)
                rows.append({
                    "sample": sample, "mkt_vol_state": state, "regime": "did", "h": h,
                    "n": int(block[f"ok_{h}h"].sum()), "n_invalid": 0,
                    "did": g, "se_did": se, "t_did": g / se if se > 0 else np.nan,
                })
    df = pd.DataFrame(rows)
    out = table_dir(out_root)
    df.to_parquet(out / "by_state.parquet", index=False)
    log(f"写出 by_state.parquet（{len(df)} 行）")
    return df


def gate_by_state(df: pd.DataFrame) -> int:
    bad = 0
    lines = ["by_state", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    n_did = int((df.regime == "did").sum())
    n_cell = int((df.regime != "did").sum())
    check("did 行 = 32", n_did == 32, str(n_did))
    check("状态×状态 行 <= 128", n_cell <= 128, str(n_cell))
    check("did 的 se > 0", bool((df[df.regime == "did"].se_did > 0).all()),
          f"最小 {df[df.regime == 'did'].se_did.min():.2e}")
    print("\n".join(lines))
    print(f"[gate] by_state: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 实验 11：事件研究图（前后各 24h）
def experiment_event_path(full: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    wide = pd.read_parquet(out_root / "wide" / "close.parquet")
    grid = pd.DatetimeIndex(wide["ts"])
    syms = [c for c in wide.columns if c != "ts"]
    col = {s: i for i, s in enumerate(syms)}
    close = wide[syms].to_numpy("float32")
    del wide

    ev = full[(full.regime.isin(REGIMES)) & (full["ok_24h"].to_numpy(dtype=bool))]
    hour = ((ev.ts_end - grid[0]).dt.total_seconds() // 3600).astype("int64").to_numpy()
    jj = ev.symbol.map(col).to_numpy()
    entry_i = hour - 1
    p0 = close[entry_i, jj]
    log(f"事件研究图：{len(ev):,} 个事件（ok_24h）")

    rows = []
    n_grid = len(grid)
    for k in range(-24, 25):
        idx = entry_i + k
        valid = (idx >= 0) & (idx < n_grid)
        cur = np.full(len(ev), np.nan, dtype="float32")
        cur[valid] = close[idx[valid], jj[valid]]
        cum = cur / p0 - 1.0
        ev2 = ev.assign(cum=cum).dropna(subset=["cum"])
        for sample in SAMPLES:
            s = ev2 if sample == "full" else ev2[ev2["in_universe"].to_numpy(dtype=bool)]
            for regime in REGIMES:
                cell = s[s["regime"] == regime]
                if not len(cell):
                    continue
                y = cell["cum"].to_numpy(dtype="float64")
                d = np.sign(cell["price_change"].to_numpy(dtype="float64"))
                g1 = cell["hour"].to_numpy()
                g2 = cell["sym_code"].to_numpy()
                m, se = mean_se_2way(y, g1, g2)
                rows.append({"sample": sample, "regime": regime, "k": k, "n": len(cell),
                             "mean_cum": m, "se_cum": se, "median_cum": float(np.median(y)),
                             "mean_sig_cum": float((d * y).mean())})
    df = pd.DataFrame(rows)
    out = table_dir(out_root)
    df.to_parquet(out / "event_path.parquet", index=False)
    log(f"写出 event_path.parquet（{len(df)} 行）")
    return df


def gate_event_path(df: pd.DataFrame) -> int:
    bad = 0
    lines = ["event_path", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数 392", len(df) == 392, str(len(df)))
    z = df[df.k == 0].mean_cum.abs().max()
    check("k=0 处累积收益 = 0", z < 1e-6, f"最大 |mean| {z:.2e}")
    # k=0 处 cum 恒为 0，方差必然为 0 —— 这是定义决定的，不是错误
    nz = df[df.k != 0]
    check("se_cum > 0 (k != 0)", bool((nz.se_cum > 0).all()), f"最小 {nz.se_cum.min():.2e}")
    print("\n".join(lines))
    print(f"[gate] event_path: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 实验 12：门槛扫描
QUANTILES = tuple(getattr(cfg_mod.REGIME, "quantiles", (0.55, 0.60, 0.65, 0.70, 0.75, 0.80)))
WIN = f"{cfg_mod.REGIME.window_days}D"
MIN_HOURS = int(cfg_mod.REGIME.min_history_days * 24)


def rolling_thr(df: pd.DataFrame, col: str, q: float) -> np.ndarray:
    """按合约重算 trailing 分位阈值（与 Phase 2 同口径）。

    注意：滚动窗口必须用【全部标签行】（含 warmup/halt）来计算，否则窗口里的观测数变少、
    分位会系统偏低 —— 实测只用 ok 行会让 p70 标注量从 923,235 掉到 906,871。
    """
    s = df.sort_values(["symbol", "ts_end"], kind="stable")
    out = np.full(len(s), np.nan)
    for _, idx in s.groupby("symbol", sort=False).indices.items():
        sub = s.iloc[idx]
        ts = pd.DatetimeIndex(sub.ts_end)
        vals = pd.Series(np.abs(sub[col].to_numpy(dtype="float64")), index=ts)
        r = vals.rolling(WIN).quantile(q).to_numpy()
        age = (ts.asi8 - ts.asi8[0]) >= MIN_HOURS * 3_600_000_000_000
        r[~age] = np.nan
        out[idx] = r
    res = np.full(len(df), np.nan)
    res[s.index.to_numpy()] = out
    return res


def experiment_threshold_scan(full: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    rows = []
    scan_counts = {}
    for q in QUANTILES:
        tp_all = rolling_thr(full, "price_change", q)
        to_all = rolling_thr(full, "oi_change", q)
        lab_all = (np.abs(full.price_change.to_numpy(dtype="float64")) > tp_all) & \
                  (np.abs(full.oi_change.to_numpy(dtype="float64")) > to_all)
        scan_counts[q] = int(lab_all.sum())
        keep = full.excl_reason.to_numpy() == "ok"
        ok_rows = full[keep].reset_index(drop=True)
        lab = lab_all[keep]
        pc = ok_rows.price_change.to_numpy(dtype="float64")
        oc = ok_rows.oi_change.to_numpy(dtype="float64")
        reg = np.where(lab & (pc > 0) & (oc > 0), "R1",
              np.where(lab & (pc > 0) & (oc < 0), "R2",
              np.where(lab & (pc < 0) & (oc > 0), "R3",
              np.where(lab & (pc < 0) & (oc < 0), "R4", ""))))
        sub = ok_rows.assign(reg_scan=reg)
        n_lab = int((sub.reg_scan != "").sum())
        log(f"  q={q:.2f}: 标注 {n_lab:,}")
        for sample in SAMPLES:
            base = sub if sample == "full" else sub[sub.in_universe.to_numpy(dtype=bool)]
            hits = base[base.reg_scan != ""]
            for h in HORIZONS:
                m = hits[f"ok_{h}h"].to_numpy(dtype=bool)
                d = np.sign(hits.price_change.to_numpy(dtype="float64")[m])
                fwd = hits[f"fwd_{h}h"].to_numpy(dtype="float64")[m]
                y = d * fwd
                g1 = hits["hour"].to_numpy()[m]
                g2 = pd.factorize(hits.symbol.to_numpy()[m], sort=False)[0]
                for regime in REGIMES:
                    sel = hits.reg_scan.to_numpy()[m] == regime
                    if sel.sum() == 0:
                        continue
                    mm, ss = mean_se_2way(y[sel], g1[sel], g2[sel])
                    rows.append({"q": q, "sample": sample, "h": h, "group": regime,
                                 "n": int(sel.sum()), "mean_sig": mm, "se": ss,
                                 "t": mm / ss if ss > 0 else np.nan})
                gg, gs = m3_did(hits.assign(sym_code=pd.factorize(hits.symbol, sort=False)[0],
                                            price_change=hits.price_change,
                                            oi_change=hits.oi_change), h)
                rows.append({"q": q, "sample": sample, "h": h, "group": "did",
                             "n": int(m.sum()), "mean_sig": gg, "se": gs,
                             "t": gg / gs if gs > 0 else np.nan})
    df = pd.DataFrame(rows).sort_values(["q", "sample", "h", "group"]).reset_index(drop=True)
    out = table_dir(out_root)
    df.to_parquet(out / "threshold_scan.parquet", index=False)
    df.to_csv(out / "threshold_scan.csv", index=False, encoding="utf-8")
    log(f"写出 threshold_scan.parquet（{len(df)} 行）")
    return df, scan_counts


def gate_threshold_scan(df: pd.DataFrame, counts: dict) -> int:
    bad = 0
    lines = ["threshold_scan", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数 240", len(df) == 240, str(len(df)))
    check("q 六档", sorted(df.q.unique()), str(sorted(df.q.unique())))
    want = {0.55: 1_660_259, 0.60: 1_390_282, 0.65: 1_144_793,
            0.70: 923_235, 0.75: 721_706, 0.80: 540_426}
    for q, w in want.items():
        g = counts.get(q, -1)
        check(f"q={q:.2f} 标注量", g == w, f"{g:,} / 期望 {w:,}")
    print("\n".join(lines))
    print(f"[gate] threshold_scan: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 实验 7：嵌套回归
def experiment_regressions(ev: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    rows = []
    for sample in SAMPLES:
        s = ev if sample == "full" else ev[ev["in_universe"].to_numpy(dtype=bool)]
        for h in HORIZONS:
            ok = s[f"ok_{h}h"].to_numpy(dtype=bool)
            sub = s[ok]
            y = sub[f"fwd_{h}h"].to_numpy(dtype="float64")
            P = (sub["price_change"].to_numpy(dtype="float64") > 0).astype("float64")
            O = (sub["oi_change"].to_numpy(dtype="float64") > 0).astype("float64")
            g1 = sub["hour"].to_numpy()
            g2 = sub["symbol"].to_numpy()
            models = {
                "M1": np.column_stack([np.ones_like(P), P]),
                "M2": np.column_stack([np.ones_like(P), P, O]),
                "M3": np.column_stack([np.ones_like(P), P, O, P * O]),
            }
            terms = {"M1": ["const", "P"], "M2": ["const", "P", "O"], "M3": ["const", "P", "O", "PxO"]}
            fitted = {}
            for name, X in models.items():
                b, se = ols_cgm(X, y, g1, g2)
                for i, t in enumerate(terms[name]):
                    rows.append({"sample": sample, "h": h, "model": name, "term": t,
                                 "coef": float(b[i]), "se": float(se[i]),
                                 "t": float(b[i] / se[i]) if se[i] > 0 else np.nan,
                                 "n": int(len(y))})
                fitted[name] = X @ b
            # H0 的两半：c=0（OI 平移）、g=0（交互）
            for label, idx in (("c", 2), ("g", 3)):
                X = models["M3"]
                b, se = ols_cgm(X, y, g1, g2)
                rows.append({"sample": sample, "h": h, "model": "M3", "term": f"test_{label}",
                             "coef": float(b[idx]), "se": float(se[idx]),
                             "t": float(b[idx] / se[idx]) if se[idx] > 0 else np.nan,
                             "n": int(len(y))})
    df = pd.DataFrame(rows)
    out = table_dir(out_root)
    df.to_parquet(out / "regressions.parquet", index=False)
    df.to_csv(out / "regressions.csv", index=False, encoding="utf-8")
    log(f"写出 regressions.parquet（{len(df)} 行）")
    return df


def gate_regressions(df: pd.DataFrame, ev: pd.DataFrame, out_root: Path) -> int:
    bad = 0
    lines = ["regressions", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数 88", len(df) == 88, f"{len(df)} / 期望 88 = 2x4x11")
    occ = table_dir(out_root) / "outcomes.parquet"
    if occ.exists():
        o = pd.read_parquet(occ)
        worst = 0.0
        for _, r in df[(df.model == "M3") & (df.term == "const")].iterrows():
            cell = o[(o["sample"] == r["sample"]) & (o.h == r.h) & (o.regime == "R4")]
            worst = max(worst, abs(float(cell.mean_fwd.iloc[0]) - r.coef))
        check("M3 的 a = R4 的 mean_fwd", worst < 1e-9, f"最大偏差 {worst:.2e}")
    print("\n".join(lines))
    print(f"[gate] regressions: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 实验 8：IC 衰减
def experiment_ic(full: pd.DataFrame, out_root: Path) -> pd.DataFrame:
    ok = full[full.excl_reason == "ok"]
    rows = []
    for sample in SAMPLES:
        base = ok if sample == "full" else ok[ok.in_universe.to_numpy(dtype=bool)]
        score = np.where(base.regime.to_numpy() == "R1", 1.0,
                np.where(base.regime.to_numpy() == "R4", -1.0, 0.0))
        base = base.assign(score=score)
        for h in HORIZONS:
            sub = base[base[f"ok_{h}h"].to_numpy(dtype=bool)]
            n_per = sub.groupby("hour")["score"].transform("size")
            sub = sub[n_per >= int(EVENT.ic_min_contracts)]
            if not len(sub):
                continue
            g = sub.groupby("hour")
            rs = g["score"].rank()
            rf = g[f"fwd_{h}h"].rank()
            gs = rs.groupby(sub["hour"]).transform("mean")
            gf = rf.groupby(sub["hour"]).transform("mean")
            ds, dff = rs - gs, rf - gf
            num = (ds * dff).groupby(sub["hour"]).sum()
            den = np.sqrt((ds ** 2).groupby(sub["hour"]).sum() * (dff ** 2).groupby(sub["hour"]).sum())
            ic = (num / den).dropna()
            n_h = len(ic)
            mean_ic = float(ic.mean())
            x = ic.to_numpy()
            L = h
            s = np.sum(x ** 2)
            for l in range(1, min(L, n_h - 1) + 1):
                s += 2 * (1 - l / (L + 1)) * float(np.sum(x[l:] * x[:-l]))
            se = float(np.sqrt(s)) / n_h
            rows.append({"sample": sample, "h": h, "n_hours": n_h,
                         "mean_ic": mean_ic, "se": se,
                         "t": mean_ic / se if se > 0 else np.nan})
    df = pd.DataFrame(rows)
    out = table_dir(out_root)
    df.to_parquet(out / "ic_decay.parquet", index=False)
    df.to_csv(out / "ic_decay.csv", index=False, encoding="utf-8")
    log(f"写出 ic_decay.parquet（{len(df)} 行）")
    return df


def gate_ic(df: pd.DataFrame) -> int:
    bad = 0
    lines = ["ic_decay", ""]

    def check(label, ok, detail):
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数 8", len(df) == 8, str(len(df)))
    check("IC 在 [-1,1]", bool(df.mean_ic.abs().max() <= 1), f"最大 |IC| {df.mean_ic.abs().max():.4f}")
    check("se > 0", bool((df.se > 0).all()), f"最小 {df.se.min():.2e}")
    print("\n".join(lines))
    print(f"[gate] ic_decay: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return bad


# ---------------------------------------------------------------- 图
def make_figures(out_root: Path) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = out_root / "tables" / f"freq={CUR_FREQ}"
    fig_dir = out_root / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    dpi = int(EVENT.figure_dpi)
    o = pd.read_parquet(t / "outcomes.parquet")
    b = pd.read_parquet(t / "baselines.parquet")
    p = pd.read_parquet(t / "path_risk.parquet")
    ep = pd.read_parquet(t / "event_path.parquet")
    ic = pd.read_parquet(t / "ic_decay.parquet")
    bs = pd.read_parquet(t / "by_state.parquet")
    colors = {"R1": "#1f77b4", "R2": "#2ca02c", "R3": "#d62728", "R4": "#ff7f0e"}
    made = []

    # f1 前向收益：2x2 = (原始水平 | 方向翻正) x (headline | full)
    xs = range(len(HORIZONS))
    order = ("headline", "full")
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2), sharex=True, sharey="row")
    for row, (metric, se, ylab) in enumerate((
        ("mean_fwd", "se_tw", "raw forward return (%)"),
        ("mean_sig", "se_sig", "direction-adjusted return (%)"),
    )):
        for col, sample in enumerate(order):
            ax = axes[row][col]
            for r in REGIMES:
                cell = o[(o.regime == r) & (o["sample"] == sample)].sort_values("h")
                y = cell[metric].to_numpy() * 100
                half = 1.96 * cell[se].to_numpy() * 100
                ax.fill_between(xs, y - half, y + half, color=colors[r], alpha=0.06, lw=0)
                ax.plot(xs, y, marker="o", ms=3.5, lw=1.4, color=colors[r], label=r)
            ax.axhline(0, color="k", lw=0.7)
            ax.grid(axis="y", color="0.92", lw=0.6)
            if row == 0:
                ax.set_title("headline (top 50)" if sample == "headline" else "full sample",
                             fontsize=9, pad=4)
            ax.set_ylabel(ylab, fontsize=8) if col == 0 else None
    axes[1][0].set_xticks(list(xs))
    axes[1][0].set_xticklabels([f"{h}h" for h in HORIZONS], fontsize=9)
    h_, l_ = axes[0][0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="upper center", ncol=4, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, 0.955))
    fig.suptitle("Forward return by regime and horizon", fontsize=11, y=0.99)
    fig.text(0.01, 0.012, "Bands: 95% two-way clustered CI.  Bottom row = top row x regime sign "
             "(+1 for R1/R2, -1 for R3/R4).  Raw returns include market drift.",
             fontsize=6.8, color="0.3")
    fig.tight_layout(rect=(0, 0.035, 1, 0.9))
    fig.savefig(fig_dir / "f1_forward_return.png", dpi=dpi); plt.close(fig)
    made.append("f1_forward_return.png")

    # f2 事件研究图：左右半轴拆成两个面板，各自独立纵轴
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for r in REGIMES:
        cell = ep[(ep.regime == r) & (ep["sample"] == "full")].sort_values("k")
        pre, post = cell[cell.k <= 0], cell[cell.k >= 0]
        for ax, part in ((axes[0], pre), (axes[1], post)):
            y = part.mean_cum.to_numpy() * 100
            half = 1.96 * part.se_cum.to_numpy() * 100
            ax.fill_between(part.k, y - half, y + half, color=colors[r], alpha=0.13, lw=0)
            ax.plot(part.k, y, color=colors[r], lw=1.6, label=r)
            ax.plot(part.k, part.median_cum * 100, color=colors[r], lw=1.0, ls="--", alpha=0.85)
    axes[0].axhline(0, color="k", lw=0.6); axes[0].axvline(0, color="k", lw=0.8)
    axes[1].axhline(0, color="k", lw=0.6); axes[1].axvline(0, color="k", lw=0.8)
    axes[0].set_xlim(-24, 0); axes[1].set_xlim(0, 24)
    axes[0].set_ylabel("cumulative raw return (%)")
    axes[0].set_title("before the event  (y spans ~9pp)", fontsize=9)
    axes[1].set_title("after the event  (y spans ~1pp)", fontsize=9)
    for ax in axes:
        ax.set_xlabel("hours relative to event")
        ax.grid(color="0.93", lw=0.6)
    h_, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h_, l_, fontsize=8, ncol=4, loc="upper center", frameon=False,
               bbox_to_anchor=(0.5, 0.985))
    fig.suptitle("Event study (full sample), panels have independent y-axes", fontsize=10, y=1.045)
    cnt = int(ep[(ep.regime == "R1") & (ep["sample"] == "full")].n.max())
    fig.text(0.01, 0.015, f"Shaded = 95% two-way clustered CI around the mean. Solid = mean, dashed = median, {cnt:,} R1 events (sample sizes differ slightly by regime). "
             "All paths are exactly 0 at the event by construction; the left half is the move that selected the event.",
             fontsize=6.5, color="0.3")
    fig.tight_layout(rect=(0, 0.05, 1, 0.99))
    fig.savefig(fig_dir / "f2_event_path.png", dpi=dpi); plt.close(fig)
    made.append("f2_event_path.png")

    # f3 基准并排
    fig, ax = plt.subplots(figsize=(8, 4.5))
    order = ["R1", "R2", "R3", "R4", "price_only", "oi_only", "funding_low", "funding_mid",
             "funding_high", "random_R1", "random_R2", "random_R3", "random_R4"]
    h24 = b[(b.h == 24) & (b["sample"] == "full")].set_index("group").reindex(order)
    ax.bar(range(len(order)), h24.mean_sig.to_numpy() * 100,
           yerr=1.96 * h24.se_sig.to_numpy() * 100, capsize=2,
           color=["#1f77b4"] * 4 + ["#7f7f7f"] * 5 + ["#c7c7c7"] * 4)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([x.replace("_", " ") for x in order], rotation=45, ha="right", fontsize=7)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("mean direction-adjusted 24h return (%)")
    ax.set_title("Four regimes vs baselines (full sample, 24h)")
    fig.tight_layout(); fig.savefig(fig_dir / "f3_baselines.png", dpi=dpi); plt.close(fig)
    made.append("f3_baselines.png")

    # f4 续势 vs 反转
    fig, ax = plt.subplots(figsize=(6, 4))
    for r in REGIMES:
        s = o[(o.regime == r) & (o["sample"] == "full")].sort_values("h")
        ax.plot(s.h, s.p_cont * 100, marker="o", color=colors[r], label=f"{r} continuation")
    ax.axhline(50, color="k", lw=0.6, ls=":")
    ax.set_xscale("log"); ax.set_xticks(list(HORIZONS)); ax.set_xticklabels([f"{h}h" for h in HORIZONS])
    ax.set_ylabel("P(future sign = event sign), %")
    ax.set_title("Continuation rate by horizon (full sample)")
    ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "f4_cont_rev.png", dpi=dpi); plt.close(fig)
    made.append("f4_cont_rev.png")

    # f5 路径风险
    fig, ax = plt.subplots(figsize=(6, 4))
    for r in REGIMES:
        s = p[(p.regime == r) & (p["sample"] == "full")].sort_values("h")
        ax.plot(s.mfe_mean * 100, s.mae_mean * 100, marker="o", color=colors[r], label=r)
        for _, row in s.iterrows():
            ax.annotate(f"{int(row.h)}h", (row.mfe_mean * 100, row.mae_mean * 100), fontsize=6)
    ax.axhline(0, color="k", lw=0.6); ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("mean MFE (%)"); ax.set_ylabel("mean MAE (%)")
    ax.set_title("Path risk: favourable vs adverse excursion")
    ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "f5_path_risk.png", dpi=dpi); plt.close(fig)
    made.append("f5_path_risk.png")

    # f6 IC 衰减
    fig, ax = plt.subplots(figsize=(6, 4))
    for sample, mk in (("full", "o"), ("headline", "s")):
        s = ic[ic["sample"] == sample].sort_values("h")
        ax.errorbar(s.h, s.mean_ic, yerr=1.96 * s.se, marker=mk, capsize=2, label=sample)
    ax.set_xscale("log"); ax.set_xticks(list(HORIZONS)); ax.set_xticklabels([f"{h}h" for h in HORIZONS])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("mean Spearman IC"); ax.set_title("IC decay by horizon")
    ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "f6_ic_decay.png", dpi=dpi); plt.close(fig)
    made.append("f6_ic_decay.png")

    # f7 分市场状态 DiD
    fig, ax = plt.subplots(figsize=(7, 4))
    did = bs[bs.regime == "did"]
    # unknown 不是一种市场状态：它只覆盖 2021-12…2022-03（波动率分位还没攒够一年），
    # 与样本最早期完全混淆。表里保留（列全、计数对得上），图里不画（避免被读成第四种状态）。
    states = [s for s in ("low", "mid", "high") if s in set(did.mkt_vol_state)]
    width = 0.2
    for i, st in enumerate(states):
        s = did[(did.mkt_vol_state == st) & (did["sample"] == "full")].sort_values("h")
        ax.bar(np.arange(len(s)) + (i - 1.5) * width, s.did.to_numpy() * 100,
               width=width, yerr=1.96 * s.se_did.to_numpy() * 100, capsize=2, label=st)
    ax.set_xticks(range(len(HORIZONS))); ax.set_xticklabels([f"{h}h" for h in HORIZONS])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("g = (R1-R2)-(R3-R4), %")
    ax.set_title("Interaction effect by market volatility state (full sample)")
    ax.legend(fontsize=7)
    ax.text(0.0, -0.22, "unknown state omitted: covers 2021-12 to 2022-03 only "
            "(trailing 1y quantiles not yet available), not a market state",
            transform=ax.transAxes, fontsize=6, color="0.35")
    fig.tight_layout(); fig.savefig(fig_dir / "f7_by_state.png", dpi=dpi); plt.close(fig)
    made.append("f7_by_state.png")

    log(f"图 {len(made)} 张：{', '.join(made)}")
    return len(made)

def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 · 表与图")
    ap.add_argument("--only", default="outcomes", help="要跑的表，逗号分隔")
    ap.add_argument("--freq", default="1h")
    ap.add_argument("--in-root", default="data")
    ap.add_argument("--out-root", default="data/06_event_study")
    args = ap.parse_args()
    out_root = Path(args.out_root).resolve()
    global CUR_FREQ
    CUR_FREQ = args.freq

    wanted = [w.strip() for w in args.only.split(",") if w.strip()]
    known = {"outcomes", "baselines", "path_risk", "by_symbol", "by_state",
             "event_path", "threshold_scan", "regressions", "ic", "figures"}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise SystemExit(f"尚未实现：{', '.join(unknown)}")

    in_root = Path(args.in_root).resolve()
    bad = 0
    ev_tables = {"outcomes", "path_risk", "by_symbol", "by_state", "regressions"}
    full_tables = {"baselines", "event_path", "threshold_scan", "ic"}

    if ev_tables & set(wanted):
        ev = load_events(out_root, args.freq)
        if "outcomes" in wanted:
            bad += gate_outcomes(experiment_outcomes(ev, out_root))
        if "path_risk" in wanted:
            bad += gate_path_risk(experiment_path_risk(ev, out_root))
        if "by_symbol" in wanted:
            bad += gate_by_symbol(experiment_by_symbol(ev, out_root), ev)
        if "by_state" in wanted:
            bad += gate_by_state(experiment_by_state(ev, out_root))
        if "regressions" in wanted:
            bad += gate_regressions(experiment_regressions(ev, out_root), ev, out_root)
        del ev

    if full_tables & set(wanted):
        full = load_panel_and_labels(in_root, out_root, args.freq)
        if "baselines" in wanted:
            bad += gate_baselines(experiment_baselines(full, out_root))
        if "event_path" in wanted:
            bad += gate_event_path(experiment_event_path(full, out_root))
        if "threshold_scan" in wanted:
            tbl, cnt = experiment_threshold_scan(full, out_root)
            bad += gate_threshold_scan(tbl, cnt)
        if "ic" in wanted:
            bad += gate_ic(experiment_ic(full, out_root))
    if "figures" in wanted:
        n = make_figures(out_root)
        bad += 0 if n == 7 else 1
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
