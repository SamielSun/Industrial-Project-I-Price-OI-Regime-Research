"""Phase 3 · figures_v2 —— 实验 12（事件研究路径，v2）+ 8 张图（实现者 I）

一句话
    本文件干两件事，**都不改任何已有脚本**：
      A. 重算实验 12 的事件路径表 `event_path_v2.parquet`（替换 v1 的 `event_path.parquet`
         —— 那张是旧口径产物，已随 v1 归档，不再使用）；
      B. 从**已有的 v2 表**画 8 张图（f1–f8），每张图里的每个数字都能回到某张表。

A · 事件路径（实验 12）
    cum_k = P(T+k) / P(T) − 1，k ∈ [−24, +24]，49 个点；P = 收盘价。
    **用原始收益：不市场中性、不截尾。** 理由：这是**路径图**，要看真实的价格轨迹；
    中性化会减掉每小时的市场均值（共同因子占 24h 收益方差 35%，D13），截尾会把
    "事件那一小时的大移动"（左半边的主体）压平 —— 两者都会让路径图不再像一条价格路径。
    （因此本表**不得**与 confirmatory/descriptive 的 winsor 口径混用；
      要比较水平请看 `descriptive_core.parquet` / `baselines_v2.parquet`。）

    价格从哪来（口径必须写死，写错会静默错位）
        `data/06_event_study/wide/close.parquet`：41,641 行 × 285 合约 + 一列 `ts`。
        实测两条对齐事实（闸门 §0 钉住，不是假设）：
          · 第 t 行的 `ts` = 2021-12-01 00:00 + t 小时 —— 即 **ts 是 bar 的开盘时刻**；
          · 该行存的收盘价对应 bar 的**收盘时刻 = ts + 1h**。
        所以事件（`ts_end` = bar 收盘时刻）的 P(T) 在**第 hour−1 行**，P(T+k) 在第 hour+k−1 行。
        证据：`mat[hour−1]/mat[hour−2] − 1` 与事件表的 `price_change` **逐行相等**
        （max|Δ| = 0），而 `mat[hour]/mat[hour−1] − 1` 差 4.5（错位一格）。
        `hour` 是事件表自带列（原点 2021-12-01，SPEC §零）。

    样本
        headline = `in_universe`（当月流动性前 50，249 合约）；
        full     = 全部 285 合约（**含** headline 行，与 `baselines_v2.py` 的 full 同定义）。
        只用 `ok_24h`，再要求 **49 个价格全齐**（`path_ok`）：实测 921,972 个 ok_24h 事件里
        有 241 个（0.026%）在 T−24…T−1 之间缺一个收盘价（该小时没有成交，bar 缺行），
        事件之前的那一段路径画不出来。**剔除它们**，于是 n 在 49 个 k 上**逐点恒定**
        （不是"差 5% 以内"，是逐位相同）——闸门 §1 就查这一条。
        ⚠️ 被剔除的只有**前置**窗口：`ok_24h` 保证 T+1…T+24 全有价格，实测 k ≥ 0 的缺失数是 0。

    每 (sample, regime, k) 报
        n、mean_cum、median_cum、se_cum、ci_lo、ci_hi、n_clusters、n_ok24h。
        se 用 `stats_core.cluster_se`（**按合约 symbol 聚类**，D17）：
        X = 常数列，于是 b = 格均值、V = 均值方差，se = sqrt(V[0,0])。
        n_ok24h = 该格的 ok_24h 事件数（= 剔除前的数），供"n 差额 = 224"这条对账。

B · 8 张图（英文标签，200 dpi，PNG，`data/06_event_study/figures/`）
    f1 前向收益（four states × four h，带 95% 区间）      descriptive_core + baselines_v2
    f2 事件路径（headline 与 full，四格，前后各 24h）      event_path_v2
    f3 五个价差（h=24，headline，带区间）                  baselines_spread
    f4 续势 / 反转比例（四格 × 四个 h）                    descriptive_core
    f5 路径风险：MFE vs MAE 散点（每点标 h）               descriptive_path
    f6 IC 衰减（四状态 vs 纯价格；原始收益 + 按 h 滞后的 NW）  ic_decay_v2
    f7 funding 四档水平随 h 变化（新图，替代 v1 的 by_state） baselines_v2
    f8 OI 增量的三个 Wald 块（W / df / p 用文字标注）       oi_increment

    三条硬规矩（闸门 §3 逐条查）
      1. **图里不写死任何数字**：每条曲线、每个点、每个误差棒都来自表列；图上出现的
         数字只有两类 —— 表里的量（n、W、df、p、均值）与**纯函数变换**（×100 转百分数、
         ×1e4 转 bp、1.96×se 转 95% 区间、用 `stats_core.chi2_sf` 反解 5% 临界值）。
      2. **图注必须写清三件事**：样本（headline / full）、口径（winsor / raw）、单位（% / bp）。
      3. **图里的 n 与表里的 n 一致**：每张图把用到的 n 渲染成文字（图注或刻度标注），
         闸门把那段文字解析回整数，再**重新从 parquet 读一遍表**算期望值比对。

单位（D14.2）
    表里一律**小数**（`mean_cum = 0.0123`，×100 = 1.23%）。图上：
      f1 / f2 / f4 / f5 用**百分数**（表值 ×100）；
      f3 / f7 用 **bp**（表值 ×1e4，1bp = 0.01%）—— 这几张的量级是 1–25bp，用 % 会全是 0.0x。

输出
    data/06_event_study/tables/freq=1h/event_path_v2.parquet  + .csv   （392 行 = 2×4×49）
    data/06_event_study/figures/f1..f8_*.png                            （200 dpi）
    data/06_event_study/docs/step12_checks_figures.txt                   （闸门 + 图清单 + n 核对）

用法
    python phase3_event/figures_v2.py              # 表 + 图 + 闸门（全部 PASS 退出码 0）
    python phase3_event/figures_v2.py --only path  # 只重算事件路径表
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from textwrap import wrap

import matplotlib

matplotlib.use("Agg")           # 无交互后端：必须在 import pyplot 之前设
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))          # stats_core 在同一个目录
sys.path.insert(0, str(HERE.parent))   # config 在仓库根目录
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows 控制台是 GBK
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402
import stats_core as sc  # noqa: E402

EVENT = cfg_mod.EVENT
FREQ = "1h"
HS = tuple(sorted(EVENT.horizons))        # (1, 4, 8, 24)
H_MAIN = max(HS)                          # 24
PATH_K = max(HS)                          # 路径窗口半宽 = 24（与主前向期同一个参数）
KS = tuple(range(-PATH_K, PATH_K + 1))    # −24 … +24，49 个点
CELLS = ("R1", "R2", "R3", "R4")
SAMPLES = ("headline", "full")
PQ = {"R1": (+1, +1), "R2": (+1, -1), "R3": (-1, +1), "R4": (-1, -1)}
CELL_LABEL = {"R1": "R1  price up / OI up", "R2": "R2  price up / OI down",
              "R3": "R3  price down / OI up", "R4": "R4  price down / OI down"}
COLORS = {"R1": "#1f77b4", "R2": "#2ca02c", "R3": "#d62728", "R4": "#ff7f0e"}
SAMPLE_COLORS = {"headline": "#1f77b4", "full": "#ff7f0e"}

ROOT = HERE.parent
OUT_ROOT = ROOT / "data" / "06_event_study"
EV_PATH = OUT_ROOT / "events" / f"events_{FREQ}.parquet"
CLOSE_PATH = OUT_ROOT / "wide" / "close.parquet"
TBL_DIR = OUT_ROOT / "tables" / f"freq={FREQ}"
FIG_DIR = OUT_ROOT / "figures"
DOC_DIR = OUT_ROOT / "docs"
CHECKS_PATH = DOC_DIR / "step12_checks_figures.txt"
IC_PATH = TBL_DIR / "ic_decay_v2.parquet"
V1_PATH = OUT_ROOT / "_archive_v1" / "tables" / f"freq={FREQ}" / "event_path.parquet"
PATH_TABLE = "event_path_v2"

T0 = pd.Timestamp("2021-12-01", tz="UTC")
"""小时原点（SPEC §零）。事件表的 hour 与 close.parquet 的行号共用这一个原点。"""

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


# ============================================================ 闸门记账
class Gate:
    """逐项记录 PASS/FAIL；任一 FAIL → 退出码 1。"""

    def __init__(self, header: str) -> None:
        self.lines = [header]
        self.n_pass = 0
        self.n_fail = 0

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(title)

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.n_pass += int(ok)
        self.n_fail += int(not ok)
        self.lines.append("  [" + ("PASS" if ok else "FAIL") + "] " + label
                          + (f"  [{detail}]" if detail else ""))

    def near(self, label: str, got: float, exp: float, tol: float = 1e-12,
             fmt: str = "%+.12f") -> None:
        dev = abs(float(got) - float(exp))
        self.check(label, dev <= tol,
                   f"{fmt % float(got)} vs 期望 {fmt % float(exp)}，|Δ| {dev:.1e} ≤ {tol:.0e}")

    def note(self, body: str) -> None:
        self.lines.append(f"        └ {body}")

    def table(self, header: list[str], rows: list[list[str]]) -> None:
        self.lines.append("")
        self.lines.append("        " + " | ".join(header))
        for r in rows:
            self.lines.append("        " + " | ".join(r))

    def text(self, footer: str) -> str:
        total = self.n_pass + self.n_fail
        return ("\n".join(self.lines) + "\n\n"
                + f"闸门汇总：PASS {self.n_pass} / FAIL {self.n_fail}（共 {total} 项）\n"
                + footer + "\n")


# ============================================================ A. 事件路径（实验 12）
BASE_COLS = ["symbol", "hour", "in_universe", "regime", "ok_24h",
             "price_change", "fwd_1h", "fwd_24h"]

NOTE_PATH = (
    "实验 12：事件研究路径 cum_k = P(T+k)/P(T) − 1，P = 收盘价（wide/close.parquet；"
    "该文件第 t 行的 ts 是 bar 开盘时刻、存的是 ts+1h 的收盘，所以 P(T+k) 在第 hour+k−1 行，"
    "与 price_change 逐行对拍 max|Δ|=0）。**原始收益**：不市场中性、不截尾——路径图要看真实价格轨迹，"
    "故本表不得与 winsor 口径（descriptive_core / baselines_v2）混用。"
    "样本：headline = in_universe、full = 全部 285 合约（含 headline 行）；"
    "只用 ok_24h 且 T−24…T+24 的 49 个收盘价全齐的事件（剔除 %d 行前置缺价，前向窗口无缺失），"
    "所以 n 在 49 个 k 上逐点恒定。k=0 恒为 0 是定义。se_cum = 按合约聚类的均值 SE，"
    "ci = mean ± 1.96·se，不截尾所以区间被极端事件拉宽是真实信息。小数单位，×100 即百分数。"
)


def load_close() -> tuple[np.ndarray, list[str], np.ndarray]:
    """读宽表收盘价矩阵（41,641 × 285）与它的小时轴。

    返回 (mat, cols, hour_axis)：mat[t, j] = 合约 cols[j] 在 **2021-12-01 + (t+1)h** 这个收盘时刻的价格
    （该文件的 ts 列是 bar 开盘时刻，见模块 docstring）。
    """
    cl = pd.read_parquet(CLOSE_PATH)
    cols = [c for c in cl.columns if c != "ts"]
    ts = pd.to_datetime(cl["ts"])
    hour_axis = ((ts - T0) // pd.Timedelta("1h")).to_numpy()
    mat = cl[cols].to_numpy(dtype="float64")
    log(f"收盘价矩阵 {mat.shape[0]:,} 行 × {len(cols)} 合约；"
        f"ts 从 {ts.iloc[0]} 到 {ts.iloc[-1]}")
    return mat, cols, hour_axis


def build_path(gate: Gate) -> tuple[pd.DataFrame, dict]:
    """实验 12 主表：2 样本 × 4 格 × 49 个 k。"""
    mat, cols, hour_axis = load_close()
    gate.section("0. 输入与对齐（价格矩阵 / 事件表）")
    gate.check("close.parquet 的 ts 逐行等于「2021-12-01 + 行号小时」（小时轴 = 行号）",
               bool(np.array_equal(hour_axis, np.arange(mat.shape[0], dtype="int64"))),
               f"{mat.shape[0]:,} 行，首 {hour_axis[0]}，末 {hour_axis[-1]}")
    gate.check("close.parquet 的合约数 = 285（事件表的合约集合）", len(cols) == 285,
               f"{len(cols)} 列（不含 ts）")

    ev = pd.read_parquet(EV_PATH, columns=BASE_COLS)
    ok = ev["ok_24h"].to_numpy(dtype=bool)
    # 只对 ok_24h 的行取价格：非 ok 的行 hour+24 可能越过矩阵末尾
    sub = ev.iloc[np.flatnonzero(ok)].reset_index(drop=True)
    del ev
    sym_idx = pd.Index(cols).get_indexer(sub["symbol"].to_numpy())
    gate.check("事件表的 symbol 全部能在 close.parquet 里找到（否则 get_indexer 给 −1）",
               bool((sym_idx >= 0).all()), f"{sub['symbol'].nunique()} 个合约")
    base = sub["hour"].to_numpy(dtype="int64") - 1          # P(T) 的行号
    gate.check("ok_24h 事件的前向窗口在矩阵内（hour+23 ≤ 末行）",
               int(base.max() + PATH_K) < mat.shape[0],
               f"max(base+24) = {int(base.max() + PATH_K)} ≤ {mat.shape[0] - 1}")

    p0 = mat[base, sym_idx]
    finite = np.isfinite(p0)
    for k in KS:
        if k:
            finite &= np.isfinite(mat[base + k, sym_idx])
    n_ok24 = int(base.size)
    n_drop = int((~finite).sum())
    log(f"ok_24h 事件 {n_ok24:,}；49 个价格全齐 {int(finite.sum()):,}"
        f"（剔除 {n_drop} 行前置缺价）")

    # ---- 分组：样本 × 格
    # ⚠️ full 是**嵌套样本**：它含 headline 那一批行（与 baselines_v2 的 full 同定义），
    # 所以一行会在两个样本里各出现一次。展开成 (样本, 行) 对，而不是把 full 定义成
    # 「非 headline」——后者会让 full 的 n 恰好少掉 headline 的数
    # （266,654 − 74,875 = 191,779，正是第一版跑出来的错数），
    # 与 baselines_v2 的 full n_pop 对不上（闸门 §2 就是这条对账）。
    is_head = sub["in_universe"].to_numpy(dtype=bool)
    reg = sub["regime"].to_numpy()
    cell_code = np.array([CELLS.index(x) for x in reg], dtype="int64")
    idx_head = np.flatnonzero(is_head)
    row_idx = np.concatenate([idx_head, np.arange(len(sub))])
    gid_all = np.concatenate([cell_code[idx_head], len(CELLS) + cell_code])
    labels = [(s, c) for s in SAMPLES for c in CELLS]

    # 组的 n（剔除前 = ok_24h 事件数）与剔除数
    n_ok_group = np.bincount(gid_all, minlength=len(labels))
    n_drop_group = np.bincount(gid_all[~finite[row_idx]], minlength=len(labels))

    # ---- 只留 49 点全齐的行，按组排好序
    keep = np.flatnonzero(finite[row_idx])
    gid_k = gid_all[keep]
    base_k = base[row_idx][keep]
    sid_k = sym_idx[row_idx][keep]
    p0_k = p0[row_idx][keep]
    pc_k = sub["price_change"].to_numpy(dtype="float64")[row_idx][keep]
    fwd1_k = sub["fwd_1h"].to_numpy(dtype="float64")[row_idx][keep]
    fwd24_k = sub["fwd_24h"].to_numpy(dtype="float64")[row_idx][keep]
    sym_k = pd.factorize(sub["symbol"].to_numpy())[0][row_idx][keep]

    order = np.argsort(gid_k, kind="stable")
    gid_s = gid_k[order]
    base_s, sid_s, p0_s = base_k[order], sid_k[order], p0_k[order]
    sym_s = sym_k[order]
    counts = np.bincount(gid_s, minlength=len(labels))
    starts = np.concatenate(([0], np.cumsum(counts)[:-1])).astype("int64")

    rows = []
    for gi, (sample, cell) in enumerate(labels):
        s0, s1 = int(starts[gi]), int(starts[gi] + counts[gi])
        n_clusters = int(np.unique(sym_s[s0:s1]).size)
        for k in KS:
            seg = mat[base_s[s0:s1] + k, sid_s[s0:s1]] / p0_s[s0:s1] - 1.0
            b, V = sc.cluster_se(np.ones((seg.size, 1), dtype="float64"), seg,
                                 sym_s[s0:s1])
            se = float(np.sqrt(V[0, 0]))
            rows.append({
                "sample": sample, "regime": cell, "k": k,
                "n": int(seg.size),
                "n_ok24h": int(n_ok_group[gi]),
                "mean_cum": float(b[0]),
                "median_cum": float(np.median(seg)),
                "se_cum": se,
                "ci_lo": float(b[0]) - 1.96 * se,
                "ci_hi": float(b[0]) + 1.96 * se,
                "n_clusters": n_clusters,
            })
        log(f"  {sample:<8s} {cell}  n {int(counts[gi]):,}（剔除 {int(n_drop_group[gi])}）"
            f" 合约 {n_clusters}  k {KS[0]}…{KS[-1]}")
    df = pd.DataFrame(rows)

    # ---- 逐事件复核量（不落表，只给闸门）：按同一排序切片取格均值
    pc_s, fwd1_s, fwd24_s = pc_k[order], fwd1_k[order], fwd24_k[order]
    cum_m1 = mat[base_s - 1, sid_s] / p0_s - 1.0        # k = −1 的累计收益
    exact_m1 = 1.0 / (1.0 + pc_s) - 1.0                 # = P(T−1)/P(T) − 1 的解析值
    cum_p1 = mat[base_s + 1, sid_s] / p0_s - 1.0        # k = +1
    cum_p24 = mat[base_s + PATH_K, sid_s] / p0_s - 1.0  # k = +24

    def _mu(x: np.ndarray) -> np.ndarray:
        return np.array([x[starts[i]:starts[i] + counts[i]].mean()
                         for i in range(len(labels))], dtype="float64")

    r2 = pc_s ** 2 / (1.0 + pc_s)          # k=−1 均值对 −mean(r) 的二阶残差项
    audit_extra = {
        "mu_pc": _mu(pc_s), "mu_fwd1": _mu(fwd1_s), "mu_fwd24": _mu(fwd24_s),
        "mu_cum_m1": _mu(cum_m1), "mu_cum_p1": _mu(cum_p1), "mu_cum_p24": _mu(cum_p24),
        "mu_r2": _mu(r2), "m1_max_dev": float(np.abs(cum_m1 - exact_m1).max()),
    }

    # ---- 记账
    audit = {
        "n_ok24": n_ok24, "n_drop": n_drop,
        "base_s": base_s, "sid_s": sid_s, "p0_s": p0_s, "sym_s": sym_s,
        "gid_s": gid_s, "counts": counts, "starts": starts,
        "n_ok_group": n_ok_group, "n_drop_group": n_drop_group, "labels": labels,
        **audit_extra,
    }
    df["unit"] = "decimal_return"
    df["method"] = "symbol_cluster"
    df["note"] = NOTE_PATH % n_drop
    gate.note(f"剔除的 {n_drop} 行（占 ok_24h 的 {n_drop / n_ok24:.4%}）全在 k<0 一侧："
              "该小时没有成交 → bar 缺行 → 收盘价缺失；前向侧 ok_24h 已保证 0 缺失")
    return df, audit


def gate_path(g: Gate, df: pd.DataFrame, audit: dict) -> None:
    """§1 口径闸门（任务书四条）+ §2 与已有 v2 表的对账。"""
    g.section("1. 实验 12 口径闸门（k=0 恰好 0 / 49 点覆盖 / n 恒定 / k=−1 ≈ −事件那一小时的移动）")
    g.check("★ 行数 = 2 样本 × 4 格 × 49 个 k = 392", len(df) == 392,
            f"{len(df)} 行 = {df['sample'].nunique()} × {df['regime'].nunique()} × "
            f"{df['k'].nunique()}")
    groups = list(df.groupby(["sample", "regime"], observed=True))
    g.check("★ 每个 (sample, regime) 的 k 覆盖 −24…+24 共 49 个点（无缺口、无重复）",
            all(sorted(sub["k"].tolist()) == list(KS) for _, sub in groups),
            "；".join(f"{s}/{c} {len(sub)} 点 [{sub['k'].min()}, {sub['k'].max()}]"
                     for (s, c), sub in groups[:2]) + " … 共 8 组")
    g.check("★ 每个 (sample, regime) 的 n 在 49 个 k 上恒定（逐位相同，不是「差 5% 以内」）",
            bool((df.groupby(["sample", "regime"], observed=True)["n"].nunique() == 1).all()),
            "；".join(f"{s}/{c} n={int(sub['n'].iloc[0]):,}"
                     for (s, c), sub in groups[:4]) + " …")
    z = df[df["k"] == 0]
    g.check("★★ k=0 处均值**恰好**为 0（容差 1e-12）",
            float(z["mean_cum"].abs().max()) <= 1e-12,
            f"max|mean_cum| = {float(z['mean_cum'].abs().max()):.1e}（8 个 (样本, 格) 全查）")
    g.check("★★ k=0 处中位数**恰好**为 0（容差 1e-12）",
            float(z["median_cum"].abs().max()) <= 1e-12,
            f"max|median_cum| = {float(z['median_cum'].abs().max()):.1e}")
    g.check("k=0 处 se = 0（每个事件的 cum_0 都是 0，方差必为 0）",
            float(z["se_cum"].abs().max()) == 0.0, f"{float(z['se_cum'].abs().max()):.1e}")
    g.check("★ se 全部有限且 ≥ 0；ci_lo ≤ 均值 ≤ ci_hi",
            bool(np.isfinite(df["se_cum"]).all()) and bool((df["se_cum"] >= 0).all())
            and bool((df["ci_lo"] <= df["mean_cum"]).all())
            and bool((df["ci_hi"] >= df["mean_cum"]).all()),
            f"se 中位数 {float(df['se_cum'].median()):.2e}，最大 {float(df['se_cum'].max()):.4f}")
    g.check("单位闸门：|mean_cum| < 0.5（小数口径，D14.2；原始路径可出现 ±20%）",
            float(df["mean_cum"].abs().max()) < 0.5,
            f"max|mean_cum| = {float(df['mean_cum'].abs().max()):.4f}"
            f"（若误写成百分数会 > 10）")
    n_head = int(df[df["sample"] == "headline"].groupby("regime")["n"].first().sum())
    n_full = int(df[df["sample"] == "full"].groupby("regime")["n"].first().sum())
    g.check("n 的加总：四格相加 = 该样本的总事件数（headline 255,701 = 255,807 − 106；"
            "full 921,731 = 921,972 − 241）",
            n_head == int(audit["counts"][:4].sum()) and n_full == int(audit["counts"][4:].sum()),
            f"headline {n_head:,} / full {n_full:,}（ok_24h {audit['n_ok24']:,}，"
            f"剔除 {audit['n_drop']}；headline 组只剔了 {int(audit['n_drop_group'][:4].sum())} 行，"
            f"full 组剔了 {int(audit['n_drop_group'][4:].sum())} 行）")

    g.note("★ k=−1 的逐事件恒等式：cum_{−1} = P(T−1)/P(T) − 1 = 1/(1+price_change) − 1")
    g.check("★★ k=−1 的累计收益逐事件等于 1/(1+r) − 1（r = 事件那一小时的 price_change）",
            float(audit["m1_max_dev"]) <= 1e-12,
            f"921,748 行逐元素 max|Δ| = {float(audit['m1_max_dev']):.1e}")
    m1 = df[df["k"] == -1]["mean_cum"].to_numpy()
    gap = m1 + audit["mu_pc"]                       # = −mean(r/(1+r)) + mean(r) = mean(r²/(1+r))
    g.check("★ k=−1 的**均值** ≈ −(事件那一小时的平均移动)：一阶 ≈ −mean(r)，"
            "二阶残差逐格**精确**等于 mean(r²/(1+r))（1e-12）",
            float(np.abs(gap - audit["mu_r2"]).max()) <= 1e-12,
            f"max|Δ − mean(r²/(1+r))| = {float(np.abs(gap - audit['mu_r2']).max()):.1e}")
    g.lines.append("        八个 (样本, 格) 的 k=−1 对账：")
    g.lines.append("          sample   regime   cum−1        −mean(r)     残差 Δ      "
                   "mean(r²/(1+r))   −mean(r) 的绝对值里 Δ 占")
    for gi, (sample, cell) in enumerate(audit["labels"]):
        g.lines.append(
            f"          {sample:<8s} {cell}     {m1[gi]:+.8f}  {-audit['mu_pc'][gi]:+.8f}  "
            f"{gap[gi]:+.3e}  {audit['mu_r2'][gi]:+.3e}   "
            f"{gap[gi] / abs(audit['mu_pc'][gi]):.2%}")
    g.note("左边那半段是「事件就是被大移动选出来的」：四个格在 k=−1…−24 上分开得很大，"
           "符号由事件方向决定（R1/R2 在负区间为负、R3/R4 为正）")

    g.section("2. 与已有 v2 表对账（样本量 / k=+1 / k=+24）")
    bl = pd.read_parquet(TBL_DIR / "baselines_v2.parquet")
    st = bl[(bl["family"] == "state") & (bl["statistic"] == "level_mean")
            & (bl["h"] == H_MAIN)]
    worst_n, rows = 0, []
    for gi, (sample, cell) in enumerate(audit["labels"]):
        exp = int(st[(st["sample"] == sample) & (st["group"] == cell)]["n"].iloc[0])
        got = int(df[(df["sample"] == sample) & (df["regime"] == cell)]["n_ok24h"].iloc[0])
        worst_n = max(worst_n, abs(exp - got))
        rows.append([sample, cell, f"{got:,}", f"{exp:,}", f"{int(audit['n_drop_group'][gi])}"])
    g.check("★ n_ok24h（剔除前）逐格 = baselines_v2 的 h=24 level_mean n（同一批 ok_24h 事件）",
            worst_n == 0, f"8 格 max|Δ| = {worst_n}")
    g.table(["sample", "regime", "n_ok24h（本表）", "n（baselines h=24）", "剔除"], rows)
    g.near("headline ∩ ok_24h 事件数（D16 锚点 255,807）",
           float(df[df["sample"] == "headline"].groupby("regime")["n_ok24h"].first().sum()),
           255807.0, tol=0, fmt="%.0f")
    d24 = float(np.abs(df[df["k"] == PATH_K]["mean_cum"].to_numpy() - audit["mu_fwd24"]).max())
    g.check("★★ k=+24 的格均值 = 同一批行的 mean(fwd_24h)（事件表自带的原始前向收益）",
            d24 <= 1e-6,
            f"8 格 max|Δ| = {d24:.1e}（fwd_24h 是 float32，1e-6 的容差是它的量级）")
    d1 = float(np.abs(df[df["k"] == 1]["mean_cum"].to_numpy() - audit["mu_fwd1"]).max())
    g.check("★ k=+1 的格均值 = 同一批行的 mean(fwd_1h)", d1 <= 1e-6, f"8 格 max|Δ| = {d1:.1e}")
    dev = float(np.abs(df[df["k"] == PATH_K]["mean_cum"].to_numpy()
                       - audit["mu_cum_p24"]).max())
    g.check("表里 k=+24 的均值 = 逐事件 cum_24 的格均值（聚合没错）", dev <= 1e-15,
            f"max|Δ| = {dev:.1e}")


def gate_v1(g: Gate, df: pd.DataFrame) -> None:
    """§2b 与归档的 v1 事件路径对照（证据，不进口径）。

    v1 的 event_path.parquet 已按 DECISIONS「清理与归档」移进 _archive_v1，
    tables/freq=1h 下**没有**同名文件，所以本次没有覆盖任何东西。
    两边都是**原始收益**（这一点 v1 没算错）；v2 的区别是：n 在 49 个 k 上恒定
    （剔除 241 行前置缺价）、补 ci / n_clusters / n_ok24h、se 换成按合约聚类。
    """
    g.section("2b. 与归档的 v1 事件路径对照（只作证据，不进口径）")
    g.check("tables/freq=1h 下没有旧的 event_path.parquet（v1 已归档，本次没覆盖任何文件）",
            not (TBL_DIR / "event_path.parquet").exists(), str(TBL_DIR / "event_path.parquet"))
    v1 = pd.read_parquet(V1_PATH)
    m = df.merge(v1, on=["sample", "regime", "k"], suffixes=("", "_v1"))
    g.check("v1 也是 2 样本 × 4 格 × 49 个 k = 392 行（同一套键）", len(m) == 392,
            f"v1 {len(v1)} 行，合并后 {len(m)} 行")
    nun_v1 = v1.groupby(["sample", "regime"])["n"].nunique()
    nun_v2 = df.groupby(["sample", "regime"])["n"].nunique()
    g.check("★★ v1 的 n **随 k 变**（8/8 组，最多 24 个不同取值）—— 这正是要重算的理由；"
            "v2 每组只有一个 n",
            bool((nun_v1 > 1).all()) and bool((nun_v2 == 1).all()),
            f"v1 nunique 最大 {int(nun_v1.max())}（n 范围 "
            f"{int(v1.groupby(['sample', 'regime'])['n'].min().min()):,}–"
            f"{int(v1.groupby(['sample', 'regime'])['n'].max().max()):,}），v2 nunique 全为 1")
    d_by = (m["mean_cum"] - m["mean_cum_v1"]).abs().groupby(
        [m["sample"], m["regime"]]).max()
    dev = float(d_by.max())
    dev_h = float(d_by.loc["headline"].max())
    g.check("★ 两版均值几乎相同（同一批事件的同一套原始收益）：全样本 max|Δ| ≤ 5e-4、"
            "headline ≤ 1e-4 —— 差异只来自 v1 按每个 k 各自丢缺价行",
            dev <= 5e-4 and dev_h <= 1e-4,
            f"全样本 {dev:.2e}（最大在 {d_by.idxmax()[0]}/{d_by.idxmax()[1]}），"
            f"headline {dev_h:.2e}")
    first = m[m["k"] == -PATH_K]
    g.check("k=−24 上 4 个 headline 组的 n 与 v1 逐位相同（同一批人；full 差 ≤ 8 行，"
            "v1 那 8 行是它自己按 k 丢的）",
            bool((first[first["sample"] == "headline"]["n"]
                  == first[first["sample"] == "headline"]["n_v1"]).all())
            and int((first["n"] - first["n_v1"]).abs().max()) <= 8,
            f"k=−24 的 Δn：headline 全 0，full {[int(x) for x in first[first['sample'] == 'full']['n_v1'] - first[first['sample'] == 'full']['n']]}")
    g.lines.append("        结论：v1 的价格口径没错（原始收益、同一批事件），错在 n 随 k 漂移"
                   "（每个 k 各自丢 NaN，于是每格 49 个点的样本各不相同，均值之差里混进组成变化）。"
                   "v2 一次丢掉 49 点不齐的 241 个事件，n 恒定，并补 ci / n_clusters / n_ok24h。")


# ============================================================ B. 图（全部从表读）
_TAB: dict[str, pd.DataFrame] = {}


def table(name: str) -> pd.DataFrame:
    """读一张 v2 表（同一次运行内只读一次）。图的每个数字都必须来自这里。"""
    if name not in _TAB:
        _TAB[name] = pd.read_parquet(TBL_DIR / f"{name}.parquet")
        log(f"读表 {name}.parquet（{_TAB[name].shape[0]:,} 行 × {_TAB[name].shape[1]} 列）")
    return _TAB[name]


def path_drop() -> tuple[int, int]:
    """从表里读「ok_24h 事件数 / 剔除数」。full 是嵌套样本，只用 full 那一半，免得重复计数。"""
    p = table(PATH_TABLE)
    f = p[p["sample"] == "full"]
    n_ok = int(f.groupby("regime")["n_ok24h"].first().sum())
    return n_ok, n_ok - int(f.groupby("regime")["n"].first().sum())


def _caption(fig, text: str, fontsize: float = 6.4, top: float = 1.0) -> None:
    """把图注放在图底部的预留带里（英文，3–6 行）；top < 1 给图例留出顶部空间。"""
    lines = wrap(text, 150)
    h_in = float(fig.get_size_inches()[1])
    band = min(0.40, (len(lines) * fontsize * 1.5 / 72.0 + 0.12) / h_in)
    fig.tight_layout(rect=(0.0, band, 1.0, top))
    fig.text(0.008, band * 0.5, "\n".join(lines), fontsize=fontsize,
             color="0.30", va="center", ha="left", linespacing=1.5)


def _save(fig, name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    p = FIG_DIR / name
    fig.savefig(p, dpi=int(EVENT.figure_dpi), facecolor="white")
    plt.close(fig)
    log(f"写图 {name}（{p.stat().st_size / 1024:.0f} KB，{int(EVENT.figure_dpi)} dpi）")
    return p


def png_dpi(path: Path) -> float:
    """从 PNG 的 pHYs 块读 DPI（不依赖 PIL；1 米 = 39.3701 英寸）。"""
    raw = path.read_bytes()
    i = raw.find(b"pHYs")
    ppu = int.from_bytes(raw[i + 4:i + 8], "big")
    return ppu * 0.0254


def chi2_crit(dof: float, alpha: float = 0.05) -> float:
    """χ²(dof) 的 1−α 分位（用 stats_core.chi2_sf 二分反解；环境没有 scipy）。"""
    lo, hi = 0.0, 1.0
    while sc.chi2_sf(dof, hi) > alpha:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if sc.chi2_sf(dof, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------- f1
def fig_forward_return() -> dict:
    """f1：四格 × 四个 h 的 mean_winsor，带 95% 区间。"""
    core = table("descriptive_core")
    bl = table("baselines_v2")
    ci = bl[(bl["family"] == "state") & (bl["statistic"] == "level_mean")
            & (bl["sample"] == "headline")]
    dev = 0.0
    fig, ax = plt.subplots(figsize=(7.6, 4.7))
    x = np.asarray(HS, dtype="float64")
    for cell in CELLS:
        s = core[core["cell"] == cell].sort_values("h")
        y = s["mean_winsor"].to_numpy() * 100.0
        c = ci[ci["group"] == cell].set_index("h").reindex(s["h"].to_numpy())
        lo = c["ci_lo"].to_numpy() * 100.0
        hi = c["ci_hi"].to_numpy() * 100.0
        dev = max(dev, float(np.abs(c["estimate"].to_numpy()
                                    - s["mean_winsor"].to_numpy()).max()))
        ax.errorbar(x, y, yerr=[y - lo, hi - y], color=COLORS[cell], marker="o", ms=4.5,
                    lw=1.4, capsize=3.5, elinewidth=1.0, label=cell)
    ax.axhline(0.0, color="k", lw=0.7)
    ax.set_xscale("log")
    ax.set_xticks(list(HS))
    ax.set_xticklabels([f"{h}h" for h in HS])
    ax.minorticks_off()
    ax.set_xlabel("forward horizon")
    ax.set_ylabel("mean forward return (%)")
    ax.set_title("f1  Forward return by state and horizon — headline (95% CI)", fontsize=9.5)
    ax.grid(axis="y", color="0.92", lw=0.6)
    ax.legend(title="state", fontsize=7.5, title_fontsize=7.5, frameon=False)

    n24 = core.loc[core["h"] == H_MAIN].set_index("cell")["n"].reindex(list(CELLS))
    n_txt = f"{int(n24.sum()):,}"
    n_cell_txt = " / ".join(f"{int(v):,}" for v in n24.to_numpy())
    caption = (
        "f1 · Source: descriptive_core.parquet (16 rows = 4 states × 4 horizons) for the points; "
        "95% CI from baselines_v2.parquet (family=state, statistic=level_mean, symbol-clustered; "
        f"the two tables' means agree to |Δ| ≤ {dev:.0e}). "
        "Sample: headline only (top-50 liquidity, 249 contracts); full is not plotted here. "
        "Convention: winsor = market-neutral + 1%/99% winsorized (D13), i.e. mean_winsor — not raw. "
        f"Unit: percent (table is decimal, ×100). n = {n_txt} headline events at h=24 "
        f"({n_cell_txt} for R1/R2/R3/R4); horizon = 1/4/8/24h on a log axis."
    )
    _caption(fig, caption)
    _save(fig, "f1_forward_return.png")
    return {"name": "f1_forward_return.png",
            "sources": {"descriptive_core": len(core), "baselines_v2": len(bl)},
            "n": {"h=24 headline 事件数": n_txt, "h=24 四格 n": n_cell_txt},
            "extra": {"两表均值 max|Δ|": f"{dev:.1e}"}}


# ---------------------------------------------------------------- f2
def fig_event_path() -> dict:
    """f2：事件路径，headline 与 full，四格，前后各 24h。"""
    p = table(PATH_TABLE)
    fig, axes = plt.subplots(len(CELLS), 2, figsize=(10.8, 9.6))
    n_txt = {}
    for row, cell in enumerate(CELLS):
        for col, (k0, k1, title) in enumerate(
                ((-PATH_K, 0, "before the event (k ≤ 0)"),
                 (0, PATH_K, "after the event (k ≥ 0)"))):
            ax = axes[row][col]
            for sample in SAMPLES:
                s = p[(p["sample"] == sample) & (p["regime"] == cell)
                      & (p["k"] >= k0) & (p["k"] <= k1)].sort_values("k")
                k = s["k"].to_numpy()
                ax.fill_between(k, s["ci_lo"].to_numpy() * 100.0,
                                s["ci_hi"].to_numpy() * 100.0,
                                color=SAMPLE_COLORS[sample], alpha=0.13, lw=0)
                ax.plot(k, s["mean_cum"].to_numpy() * 100.0, color=SAMPLE_COLORS[sample],
                        lw=1.7, label=f"{sample} — mean")
                ax.plot(k, s["median_cum"].to_numpy() * 100.0, color=SAMPLE_COLORS[sample],
                        lw=1.0, ls="--", label=f"{sample} — median")
            ax.axhline(0.0, color="k", lw=0.6)
            ax.axvline(0.0, color="k", lw=0.8)
            ax.grid(color="0.93", lw=0.6)
            ax.set_xticks([k0, (k0 + k1) // 2, k1] if col else [k0, -16, -8, 0])
            if row == 0:
                ax.set_title(title, fontsize=9)
            if col == 0:
                ax.set_ylabel(CELL_LABEL[cell] + "\ncum. raw return (%)", fontsize=8)
            else:
                ax.set_ylabel("cum. raw return (%)", fontsize=8)
            if row == len(CELLS) - 1:
                ax.set_xlabel("hours relative to the event")
            if col == 0:
                nh = int(p[(p["sample"] == "headline") & (p["regime"] == cell)]["n"].iloc[0])
                nf = int(p[(p["sample"] == "full") & (p["regime"] == cell)]["n"].iloc[0])
                t = f"headline n={nh:,}\nfull n={nf:,}"
                # n 放在曲线起点对面的那个角（按起点在纵轴上的位置选，写死会让某个格压线）
                y0 = float(p[(p["sample"] == "full") & (p["regime"] == cell)
                             & (p["k"] == k0)]["mean_cum"].iloc[0]) * 100.0
                lo_, hi_ = ax.get_ylim()
                up = y0 <= 0.5 * (lo_ + hi_)
                ax.text(0.03, 0.96 if up else 0.04, t, transform=ax.transAxes,
                        fontsize=6.1, color="0.25", va="top" if up else "bottom", ha="left")
                n_txt[f"headline/{cell}"] = f"{nh:,}"
                n_txt[f"full/{cell}"] = f"{nf:,}"
    h_, l_ = axes[0][0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="lower center", ncol=4, frameon=False, fontsize=6.8,
               bbox_to_anchor=(0.5, 0.972))
    n_ok, n_drop = path_drop()
    caption = (
        "f2 · Source: event_path_v2.parquet (392 rows = 2 samples × 4 states × 49 k values). "
        "Sample: headline (blue, top-50 liquidity) and full (orange, all 285 contracts, includes headline rows). "
        "Convention: raw close-to-close cumulative return cum_k = P(T+k)/P(T) − 1 — not market-neutral, "
        "not winsorized. Unit: percent. Solid = mean with 95% CI band (symbol-clustered SE); dashed = median. "
        "Each panel autoscales: the left half is the move that selected the event (several pp), the right half "
        "spans ~1pp, so slopes must not be compared across panels. n is printed in the left column of every row "
        f"(constant across all 49 k by construction; {n_drop} of {n_ok} ok_24h events lack a pre-event close and are dropped)."
    )
    _caption(fig, caption, top=0.965)
    _save(fig, "f2_event_path.png")
    return {"name": "f2_event_path.png", "sources": {PATH_TABLE: len(p)},
            "n": n_txt, "extra": {}}


# ---------------------------------------------------------------- f3
def fig_baselines() -> dict:
    """f3：五个价差并排（h=24，headline，带区间）。"""
    sp = table("baselines_spread")
    s24 = sp[(sp["h"] == H_MAIN) & (sp["sample"] == "headline")].set_index("group")
    order = ["price", "oi", "funding", "four_state", "random"]
    tick = {"price": "price only\n(up − down)", "oi": "OI only\n(up − down)",
            "funding": "funding\n(>p75 − ≤p25)", "four_state": "four-state\n(R1 − R4)",
            "random": "random contract\n(same hour)"}
    fill = {"price": "#c8c8c8", "oi": "#c8c8c8", "funding": "#8c8c8c",
            "four_state": "#1f77b4", "random": "#dcdcdc"}
    est = np.array([float(s24.loc[g, "estimate"]) for g in order]) * 1e4
    lo = np.array([float(s24.loc[g, "ci_lo"]) for g in order]) * 1e4
    hi = np.array([float(s24.loc[g, "ci_hi"]) for g in order]) * 1e4

    fig, ax = plt.subplots(figsize=(8.2, 4.9))
    bars = ax.bar(range(len(order)), est, width=0.62,
                  color=[fill[g] for g in order], edgecolor="0.35", lw=0.6)
    ax.errorbar(range(len(order)), est, yerr=[est - lo, hi - est], fmt="none",
                ecolor="0.15", capsize=5, elinewidth=1.1)
    for i, v in enumerate(est):
        ax.annotate(f"{v:+.1f}", (i, v), xytext=(0, 8 if v >= 0 else -8),
                    textcoords="offset points", ha="center", fontsize=7.5,
                    va="bottom" if v >= 0 else "top",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    ax.set_axisbelow(True)
    ax.axhline(0.0, color="k", lw=0.8)
    ax.set_xticks(range(len(order)))
    n_lab = {g: f"{int(s24.loc[g, 'n_long']):,} / {int(s24.loc[g, 'n_short']):,}"
             for g in order}
    ax.set_xticklabels([tick[g] + "\nn " + n_lab[g] for g in order], fontsize=7.2)
    ax.set_ylabel("long − short, 24h return (bp)")
    ax.set_title("f3  Five long-short spreads at h=24 — headline", fontsize=9.5)
    ax.grid(axis="y", color="0.92", lw=0.6)

    caption = (
        "f3 · Source: baselines_spread.parquet (40 rows = 2 samples × 4 horizons × 5 spreads; "
        "5 rows used: sample=headline, h=24). Sample: headline (top-50 liquidity); full is not plotted. "
        "Convention: winsor = market-neutral + 1%/99% winsorized 24h return (D13). "
        "Unit: basis points (table is decimal, ×1e4; 1bp = 0.01%). "
        "Error bars are the table's own ci_lo/ci_hi: for the four symbol-clustered rows that is "
        "estimate ± 1.96·SE (95%); for the random row it is the [p5, p95] band of 1000 same-hour "
        "random-contract redraws (90%, Monte-Carlo) — a different object, not a 95% CI. "
        "Tick labels: n = n_long / n_short (events in each leg)."
    )
    _caption(fig, caption)
    _save(fig, "f3_baselines.png")
    return {"name": "f3_baselines.png", "sources": {"baselines_spread": len(sp)},
            "n": {f"n_long/n_short {g}": n_lab[g] for g in order}, "extra": {}}


# ---------------------------------------------------------------- f4
def fig_cont_rev() -> dict:
    """f4：续势 / 反转比例（四格 × 四个 h）。"""
    core = table("descriptive_core")
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.6), sharex=True)
    for ax, col, ttl in (
            (axes[0], "p_cont", "continuation:  P(sign(fwd) = sign(price move))"),
            (axes[1], "p_rev", "reversal:  P(sign(fwd) = −sign(price move))")):
        for cell in CELLS:
            s = core[core["cell"] == cell].sort_values("h")
            ax.plot(s["h"].to_numpy(), s[col].to_numpy() * 100.0, color=COLORS[cell],
                    marker="o", ms=4.2, lw=1.5, label=cell)
        ax.axhline(50.0, color="k", lw=0.7, ls=":")
        ax.set_xscale("log")
        ax.set_xticks(list(HS))
        ax.set_xticklabels([f"{h}h" for h in HS])
        ax.minorticks_off()
        ax.set_xlabel("forward horizon")
        ax.set_ylabel("share of events (%)")
        ax.set_title(ttl, fontsize=8.6)
        ax.grid(color="0.93", lw=0.6)
        ax.margins(y=0.08)
    h_, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="lower center", ncol=4, frameon=False, fontsize=7.8,
               bbox_to_anchor=(0.5, 0.945), title="state", title_fontsize=7.8)
    n24 = core.loc[core["h"] == H_MAIN].set_index("cell")["n"].reindex(list(CELLS))
    n_txt = f"{int(n24.sum()):,}"
    n_cell_txt = " / ".join(f"{int(v):,}" for v in n24.to_numpy())
    caption = (
        "f4 · Source: descriptive_core.parquet (16 rows = 4 states × 4 horizons; columns p_cont / p_rev). "
        "Sample: headline only (top-50 liquidity, 249 contracts). "
        "Convention: winsor-direction-free proportions — cont/rev/flat are computed on the raw forward "
        "return's sign, not on the winsorized level; flat (fwd = 0) is the remainder and is not plotted. "
        "Dotted line = 50% (coin flip; every state's continuation sits below it). "
        f"Unit: percent of events (table is a 0–1 proportion, ×100). n = {n_txt} headline events at h=24 "
        f"({n_cell_txt} for R1/R2/R3/R4). p_cont is numerically identical to the hit rate — same identity, "
        "not independent evidence (D19.1 / descriptive.py §2)."
    )
    _caption(fig, caption, top=0.89)
    _save(fig, "f4_cont_rev.png")
    return {"name": "f4_cont_rev.png", "sources": {"descriptive_core": len(core)},
            "n": {"h=24 headline 事件数": n_txt, "h=24 四格 n": n_cell_txt}, "extra": {}}


# ---------------------------------------------------------------- f5
def fig_path_risk() -> dict:
    """f5：MFE vs MAE 散点，每点标 h。"""
    dp = table("descriptive_path")
    H_OFF = {"R1": (6, 6), "R2": (6, -12), "R3": (6, 17), "R4": (6, -23)}
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.9))
    for ax, (xm, ym, ttl, sub) in zip(axes, (
            ("mfe_mean", "mae_mean", "mean excursion", "mean — dominated by the tail (D7)"),
            ("mfe_p50", "mae_p50", "median (p50) excursion", "typical path"))):
        for cell in CELLS:
            s = dp[dp["cell"] == cell].sort_values("h")
            xs = s[xm].to_numpy() * 100.0
            ys = s[ym].to_numpy() * 100.0
            ax.plot(xs, ys, color=COLORS[cell], marker="o", ms=4.4, lw=1.2, label=cell)
            dx, dy = H_OFF[cell]      # 四个格在 1h 处几乎重合，标签必须错开才不会叠成一团
            for h, xx, yy in zip(s["h"].to_numpy(), xs, ys):
                ax.annotate(f"{int(h)}h", (xx, yy), textcoords="offset points",
                            xytext=(dx, dy), fontsize=6.2, color=COLORS[cell])
        ax.axhline(0.0, color="k", lw=0.7)
        ax.axvline(0.0, color="k", lw=0.7)
        ax.set_xlabel("MFE — maximum favourable excursion (%)")
        ax.set_ylabel("MAE — maximum adverse excursion (%)")
        ax.set_title("f5  Path risk: " + ttl + "  (" + sub + ")", fontsize=8.8)
        ax.grid(color="0.93", lw=0.6)
    axes[0].legend(title="state", fontsize=7.2, title_fontsize=7.2, frameon=False)
    n24 = dp.loc[dp["h"] == H_MAIN].set_index("cell")["n"].reindex(list(CELLS))
    n_txt = f"{int(n24.sum()):,}"
    n_cell_txt = " / ".join(f"{int(v):,}" for v in n24.to_numpy())
    caption = (
        "f5 · Source: descriptive_path.parquet (16 rows = 4 states × 4 horizons; columns mfe_* / mae_*). "
        "Sample: headline only (top-50 liquidity). "
        "Convention: raw path extremes, direction-adjusted (d = −1 rows flipped), NOT winsorized by design "
        "(D7: no truncation, no flag) — so the left panel's means are pulled by a few extreme paths and the "
        "right panel (p50) is the typical path. "
        f"Unit: percent (table is decimal, ×100). Each point is labelled with its horizon h. n = {n_txt} "
        f"headline events at h=24 ({n_cell_txt} for R1/R2/R3/R4); n differs slightly across h (see table)."
    )
    _caption(fig, caption)
    _save(fig, "f5_path_risk.png")
    return {"name": "f5_path_risk.png", "sources": {"descriptive_path": len(dp)},
            "n": {"h=24 headline 事件数": n_txt, "h=24 四格 n": n_cell_txt}, "extra": {}}


# ---------------------------------------------------------------- f6
def fig_ic_decay() -> dict:
    """f6：IC 衰减 —— 四状态分数 vs 纯价格动量，headline / full 两面板。

    只画两个**分数**（four / price）。表里的 price_minus_four 是两者的差，
    不是分数，画上去会被读成第三条信号 —— 按任务书不画。
    """
    ic = table("ic_decay_v2")
    scores = ("four", "price")
    slab = {"four": "four-state score  (R1=+1, R4=−1, else 0)",
            "price": "pure price momentum  (sign of the price move)"}
    scol = {"four": "#1f77b4", "price": "#7f7f7f"}
    n_txt: dict[str, str] = {}
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.9), sharey=True)
    flip = {}
    for ax, sample in zip(axes, SAMPLES):
        for sc in scores:
            s = ic[(ic["sample"] == sample) & (ic["score"] == sc)].sort_values("h")
            y = s["mean_ic"].to_numpy()
            ax.errorbar(s["h"].to_numpy(), y, yerr=1.96 * s["se_nw"].to_numpy(),
                        color=scol[sc], marker="o", ms=4.5, lw=1.6, capsize=3.5,
                        elinewidth=1.0, label=slab[sc])
            n_txt[f"{sample}/{sc}"] = f"{int(s[s['h'] == H_MAIN]['n_hours'].iloc[0]):,}"
            flip[f"{sample}/{sc}"] = float(s[s["h"] == H_MAIN]["mean_ic"].iloc[0])
        ax.axhline(0.0, color="k", lw=0.7)
        ax.set_xscale("log")
        ax.set_xticks(list(HS))
        ax.set_xticklabels([f"{h}h" for h in HS])
        ax.minorticks_off()
        ax.set_xlabel("forward horizon")
        ax.set_title(f"{sample} sample", fontsize=9)
        ax.grid(color="0.93", lw=0.6)
        ax.text(0.03, 0.95,
                f"n_h at 24h:  four {n_txt[sample + '/four']} · price {n_txt[sample + '/price']}",
                transform=ax.transAxes, fontsize=6.8, color="0.25", va="top", ha="left")
        ax.margins(y=0.12)
    axes[0].set_ylabel("mean Spearman IC  (negative = reversal)")
    h_, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="lower center", ncol=2, frameon=False, fontsize=7.6,
               bbox_to_anchor=(0.5, 0.958))
    caption = (
        "f6 · Source: ic_decay_v2.parquet (24 rows = 2 samples × 4 horizons × 3 scores; 16 plotted — "
        "the 8 'price_minus_four' rows are a DIFFERENCE between scores, not a score, so they are not plotted). "
        "Sample: headline (left) and full (right, all 285 contracts). "
        "Convention: IC = within-hour Spearman rank correlation between the score and the **raw** forward "
        "return (not market-neutral, not winsorized — IC measures ranking, so the return scale is irrelevant), "
        "averaged over hours. The four-state score takes +1 / −1 / 0, i.e. it is non-zero ONLY on event rows, "
        "so its IC is mechanically diluted relative to price, which scores every valid row. "
        "95% CI = mean ± 1.96·se_nw, Newey-West with lag = h (overlapping forward windows). "
        "Unit: rank correlation (dimensionless); negative = cross-sectional reversal. "
        f"n_h (hours) at h=24: four {n_txt['headline/four']} / price {n_txt['headline/price']} (headline), "
        f"{n_txt['full/four']} / {n_txt['full/price']} (full). "
        f"Ranking flips at h=24: price is stronger at 1/4/8h, but at 24h the four-state score wins "
        f"({flip['headline/four']:+.4f} vs {flip['headline/price']:+.4f} on headline) — and that is despite "
        "the dilution handicap spelled out above."
    )
    _caption(fig, caption, top=0.94)
    _save(fig, "f6_ic_decay.png")
    return {"name": "f6_ic_decay.png", "sources": {"ic_decay_v2": len(ic)},
            "n": n_txt,
            "extra": {"画了哪些分数": list(scores),
                      "h=24 的 IC": [f"{k} {v:+.6f}" for k, v in flip.items()]}}


# ---------------------------------------------------------------- f7
def fig_funding() -> dict:
    """f7：funding 四档水平随 h 变化（新图，替代 v1 的 by_state）。"""
    bl = table("baselines_v2")
    fnd = bl[(bl["family"] == "funding") & (bl["statistic"] == "level_mean")]
    groups = ["funding_low", "funding_mid", "funding_high", "funding_extreme"]
    glab = {"funding_low": "f ≤ p25", "funding_mid": "p25 < f ≤ p75",
            "funding_high": "f > p75", "funding_extreme": "f > p90  (subset of > p75)"}
    gcol = {"funding_low": "#9ecae1", "funding_mid": "#6baed6",
            "funding_high": "#2171b5", "funding_extreme": "#08306b"}
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.7), sharey=True)
    n_lab = {}
    for ax, sample in zip(axes, SAMPLES):
        for grp in groups:
            s = fnd[(fnd["sample"] == sample) & (fnd["group"] == grp)].sort_values("h")
            y = s["estimate"].to_numpy() * 1e4
            ax.fill_between(s["h"].to_numpy(), s["ci_lo"].to_numpy() * 1e4,
                            s["ci_hi"].to_numpy() * 1e4, color=gcol[grp], alpha=0.16, lw=0)
            n_h = int(s[s["h"] == H_MAIN]["n"].iloc[0])
            n_lab[f"{sample}/{grp}"] = f"{n_h:,}"
            ax.plot(s["h"].to_numpy(), y, color=gcol[grp], marker="o", ms=4, lw=1.6,
                    label=f"{glab[grp]}  (n={n_h:,})")
        ax.axhline(0.0, color="k", lw=0.7)
        ax.set_xscale("log")
        ax.set_xticks(list(HS))
        ax.set_xticklabels([f"{h}h" for h in HS])
        ax.minorticks_off()
        ax.set_xlabel("forward horizon")
        ax.set_title(f"{sample} sample", fontsize=9)
        ax.grid(color="0.93", lw=0.6)
    axes[0].set_ylabel("mean forward return (bp)")
    axes[0].legend(fontsize=6.6, frameon=False, loc="lower left")
    fig.suptitle("f7  Funding buckets: level of the forward return by horizon", fontsize=10, y=0.99)
    n24h = n_lab["headline/funding_low"]
    caption = (
        "f7 · Source: baselines_v2.parquet (200 rows; used: family=funding, statistic=level_mean, 32 rows). "
        "Sample: headline (left) and full (right, all 285 contracts). "
        "Convention: winsor = market-neutral + 1%/99% winsorized forward return (D13/D14.3), i.e. the level "
        "of the return inside each funding bucket — this replaces the v1 by_state figure. "
        "Unit: basis points (table is decimal, ×1e4). Band = 95% CI from the table's ci_lo/ci_hi "
        "(symbol-clustered). Buckets are the note's four funding tiers; f > p90 is a SUBSET of f > p75 "
        "(D12 / baselines_v2.py), so the two lines are not disjoint cells. "
        f"Legend shows n at h=24 (headline tier 1 has n={n24h})."
    )
    _caption(fig, caption)
    _save(fig, "f7_funding.png")
    return {"name": "f7_funding.png", "sources": {"baselines_v2": len(bl)},
            "n": n_lab, "extra": {}}


# ---------------------------------------------------------------- f8
def fig_oi_increment() -> dict:
    """f8：oi_increment 的三个 Wald 块（W / df / p 用文字标注）。"""
    oi = table("oi_increment")
    w = oi[oi["statistic"] == "wald"].set_index("block")
    blocks = ["oi_dimension", "interaction", "joint"]
    blab = {"oi_dimension": "OI dimension\n(q, q²)", "interaction": "interaction\n(Pq, Pq²)",
            "joint": "joint\n(all four)"}
    W = np.array([float(w.loc[b, "estimate"]) for b in blocks])
    DF = np.array([float(w.loc[b, "df"]) for b in blocks])
    P = np.array([float(w.loc[b, "p"]) for b in blocks])
    crit = np.array([chi2_crit(d) for d in DF])

    fig, ax = plt.subplots(figsize=(7.8, 4.9))
    ax.bar(range(len(blocks)), W, width=0.55, color="#8c8c8c", edgecolor="0.3", lw=0.6)
    for i in range(len(blocks)):
        ax.annotate(f"W = {W[i]:.3f}\ndf = {DF[i]:.0f}\np = {P[i]:.3f}",
                    (i, W[i]), textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=7.6)
        ax.plot([i - 0.32, i + 0.32], [crit[i], crit[i]], color="#d62728", lw=1.6)
        ax.annotate(f"5% crit = {crit[i]:.2f}", (i, crit[i]),
                    textcoords="offset points", xytext=(0, 4), ha="center",
                    va="bottom", fontsize=6.4, color="#d62728")
    ax.set_axisbelow(True)
    ax.set_xlim(-0.6, len(blocks) - 0.4)
    ax.set_xticks(range(len(blocks)))
    ax.set_xticklabels([blab[b] for b in blocks], fontsize=8)
    ax.set_ylabel("Wald χ² statistic")
    ax.set_ylim(0.0, float(max(W.max(), crit.max())) * 1.30)
    ax.set_title("f8  OI increment over price-only — six-cell model, headline, h=24", fontsize=9.5)
    ax.grid(axis="y", color="0.92", lw=0.6)

    nr = oi[oi["statistic"] == "n_rows"].set_index("block")["n"]
    tot_txt = f"{int(nr.loc['total_rows']):,}"
    ev_txt = f"{int(nr.loc['event_rows']):,}"
    ct_txt = f"{int(nr.loc['control_rows']):,}"
    caption = (
        "f8 · Source: oi_increment.parquet (25 rows; 3 used: statistic=wald). "
        "Sample: headline, h=24 — six-cell model = price sign × OI three states (extreme down / quiet / "
        "extreme up) + log(shock) control, symbol-clustered. "
        f"n = {tot_txt} rows = {ev_txt} events + {ct_txt} price-over-threshold / OI-quiet controls. "
        "Convention: winsor = market-neutral + 1%/99% winsorized 24h return (D13). "
        "Unit: χ² statistic (not a return). The three blocks are joint Wald tests; the annotation on each "
        "bar is the table's W / df / p. Red tick = 5% critical value, obtained by inverting "
        "stats_core.chi2_sf at that df (not a hard-coded number). None of the three rejects."
    )
    _caption(fig, caption)
    _save(fig, "f8_oi_increment.png")
    return {"name": "f8_oi_increment.png", "sources": {"oi_increment": len(oi)},
            "n": {"h=24 六格模型总行数": tot_txt, "事件行": ev_txt, "OI 安静对照行": ct_txt},
            "extra": {"W/df/p 标注": [f"W = {W[i]:.3f}  df = {DF[i]:.0f}  p = {P[i]:.3f}"
                                   for i in range(len(blocks))]}}


# ---------------------------------------------------------------- 全部图
def draw_all() -> list[dict]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    figs = [fig_forward_return(), fig_event_path(), fig_baselines(),
            fig_cont_rev(), fig_path_risk(), fig_ic_decay(),
            fig_funding(), fig_oi_increment()]
    log(f"共画 {len(figs)} 张图：{', '.join(f['name'] for f in figs)}")
    return figs


# ============================================================ C. 图闸门
def parse_n(txt: str) -> int:
    """把图上渲染出来的 n（"255,807"）解析回整数。"""
    return int(str(txt).replace(",", "").strip())


def gate_figures(g: Gate, figs: list[dict]) -> None:
    g.section("3. 图结构 + 「图里的 n == 表里的 n」核对（n 从图上的文字解析回整数，"
              "期望值**重新读一遍 parquet** 算）")
    by = {f["name"]: f for f in figs}

    for f in figs:
        p = FIG_DIR / f["name"]
        dpi = png_dpi(p)
        img = plt.imread(p)
        g.check(f"{f['name']}：PNG 存在、{int(EVENT.figure_dpi)} dpi、{img.shape[1]}×{img.shape[0]} px",
                p.exists() and abs(dpi - EVENT.figure_dpi) < 1.0 and img.shape[1] >= 1400,
                f"{p.stat().st_size / 1024:.0f} KB，dpi {dpi:.1f}")
        for tname, nrow in f["sources"].items():
            actual = len(pd.read_parquet(TBL_DIR / f"{tname}.parquet"))
            g.check(f"    {f['name']} 的源表 {tname} 行数 = {nrow:,}（重读 parquet 一致）",
                    actual == nrow, f"{actual:,} 行")

    # ---- n 对账：期望值全部从 parquet 重算
    rows = []
    core = pd.read_parquet(TBL_DIR / "descriptive_core.parquet")
    n24 = core.loc[core["h"] == H_MAIN].set_index("cell")["n"].reindex(list(CELLS))
    n24_txt = " / ".join(f"{int(v):,}" for v in n24.to_numpy())
    for fname in ("f1_forward_return.png", "f4_cont_rev.png"):
        f = by[fname]
        ok = (parse_n(f["n"]["h=24 headline 事件数"]) == int(n24.sum())
              and [parse_n(x) for x in f["n"]["h=24 四格 n"].split("/")]
              == [int(v) for v in n24.to_numpy()])
        g.check(f"{fname}：图内 n（{f['n']['h=24 headline 事件数']}，四格 "
                f"{f['n']['h=24 四格 n']}）== descriptive_core h=24 的 n", ok,
                f"表：{int(n24.sum()):,}（{n24_txt}）")
        rows.append([fname, "descriptive_core", f"{len(core)}",
                     f["n"]["h=24 headline 事件数"], f"{int(n24.sum()):,}", "OK" if ok else "MISMATCH"])

    path = pd.read_parquet(TBL_DIR / f"{PATH_TABLE}.parquet")
    f2 = by["f2_event_path.png"]
    ok2 = True
    detail = []
    for sample in SAMPLES:
        for cell in CELLS:
            exp = int(path[(path["sample"] == sample) & (path["regime"] == cell)]["n"].iloc[0])
            got = parse_n(f2["n"][f"{sample}/{cell}"])
            ok2 &= got == exp
            detail.append(f"{sample}/{cell} 图 {got:,} = 表 {exp:,}")
    g.check("f2_event_path.png：图内 8 个 n（headline/full × R1–R4）== event_path_v2 的 n",
            ok2, "；".join(detail[:4]) + " …")
    g.lines.append("        └ " + "；".join(detail))
    rows.append(["f2_event_path.png", "event_path_v2", f"{len(path)}",
                 "8 个（见上）", "8 个（见上）", "OK" if ok2 else "MISMATCH"])

    sp = pd.read_parquet(TBL_DIR / "baselines_spread.parquet")
    s24 = sp[(sp["h"] == H_MAIN) & (sp["sample"] == "headline")].set_index("group")
    f3 = by["f3_baselines.png"]
    ok3, det3 = True, []
    for grp in ["price", "oi", "funding", "four_state", "random"]:
        got = [parse_n(x) for x in f3["n"][f"n_long/n_short {grp}"].split("/")]
        exp = [int(s24.loc[grp, "n_long"]), int(s24.loc[grp, "n_short"])]
        ok3 &= got == exp
        det3.append(f"{grp} 图 {got[0]:,}/{got[1]:,} = 表 {exp[0]:,}/{exp[1]:,}")
    g.check("f3_baselines.png：图内 n_long/n_short（5 个价差）== baselines_spread h=24 headline",
            ok3, "；".join(det3[:2]) + " …")
    g.lines.append("        └ " + "；".join(det3))
    rows.append(["f3_baselines.png", "baselines_spread", f"{len(sp)}",
                 "5 组 n_long/n_short", "5 组（逐组相同）", "OK" if ok3 else "MISMATCH"])

    dp = pd.read_parquet(TBL_DIR / "descriptive_path.parquet")
    p24 = dp.loc[dp["h"] == H_MAIN].set_index("cell")["n"].reindex(list(CELLS))
    f5 = by["f5_path_risk.png"]
    ok5 = (parse_n(f5["n"]["h=24 headline 事件数"]) == int(p24.sum())
           and [parse_n(x) for x in f5["n"]["h=24 四格 n"].split("/")]
           == [int(v) for v in p24.to_numpy()])
    g.check("f5_path_risk.png：图内 n（h=24 四格）== descriptive_path h=24 的 n", ok5,
            f"图 {f5['n']['h=24 headline 事件数']}（{f5['n']['h=24 四格 n']}）vs "
            f"表 {int(p24.sum()):,}（{' / '.join(f'{int(v):,}' for v in p24.to_numpy())}）")
    rows.append(["f5_path_risk.png", "descriptive_path", f"{len(dp)}",
                 f5["n"]["h=24 headline 事件数"],
                 f"{int(p24.sum()):,}", "OK" if ok5 else "MISMATCH"])

    icd = pd.read_parquet(TBL_DIR / "ic_decay_v2.parquet")
    f6 = by["f6_ic_decay.png"]
    ok6, det6 = True, []
    for sample in SAMPLES:
        for sc in ("four", "price"):
            exp = int(icd[(icd["sample"] == sample) & (icd["score"] == sc)
                          & (icd["h"] == H_MAIN)]["n_hours"].iloc[0])
            got = parse_n(f6["n"][f"{sample}/{sc}"])
            ok6 &= got == exp
            det6.append(f"{sample}/{sc} 图 {got:,} = 表 {exp:,}")
    g.check("f6_ic_decay.png：图内 4 个 n_h（h=24；headline/full × four/price）== ic_decay_v2 的 n_hours",
            ok6, "；".join(det6[:2]) + " …")
    g.lines.append("        └ " + "；".join(det6))
    rows.append(["f6_ic_decay.png", "ic_decay_v2", f"{len(icd)}", "4 个（见上）", "4 个（见上）",
                 "OK" if ok6 else "MISMATCH"])

    bl = pd.read_parquet(TBL_DIR / "baselines_v2.parquet")
    fnd = bl[(bl["family"] == "funding") & (bl["statistic"] == "level_mean")
             & (bl["h"] == H_MAIN)]
    f7 = by["f7_funding.png"]
    ok7, det7 = True, []
    for sample in SAMPLES:
        for grp in ["funding_low", "funding_mid", "funding_high", "funding_extreme"]:
            exp = int(fnd[(fnd["sample"] == sample) & (fnd["group"] == grp)]["n"].iloc[0])
            got = parse_n(f7["n"][f"{sample}/{grp}"])
            ok7 &= got == exp
            det7.append(f"{sample}/{grp} 图 {got:,} = 表 {exp:,}")
    g.check("f7_funding.png：图例里的 8 个 n（headline/full × 四档）== baselines_v2 h=24 的 n",
            ok7, "；".join(det7[:2]) + " …")
    g.lines.append("        └ " + "；".join(det7))
    rows.append(["f7_funding.png", "baselines_v2", f"{len(bl)}",
                 "8 个（见上）", "8 个（见上）", "OK" if ok7 else "MISMATCH"])

    oi = pd.read_parquet(TBL_DIR / "oi_increment.parquet")
    nr = oi[oi["statistic"] == "n_rows"].set_index("block")["n"]
    f8 = by["f8_oi_increment.png"]
    ok8 = (parse_n(f8["n"]["h=24 六格模型总行数"]) == int(nr.loc["total_rows"])
           and parse_n(f8["n"]["事件行"]) == int(nr.loc["event_rows"])
           and parse_n(f8["n"]["OI 安静对照行"]) == int(nr.loc["control_rows"]))
    g.check("f8_oi_increment.png：图内 n（总/事件/对照）== oi_increment 的 n_rows", ok8,
            f"图 {f8['n']['h=24 六格模型总行数']} = {f8['n']['事件行']} + "
            f"{f8['n']['OI 安静对照行']}；表 {int(nr.loc['total_rows']):,} = "
            f"{int(nr.loc['event_rows']):,} + {int(nr.loc['control_rows']):,}")
    rows.append(["f8_oi_increment.png", "oi_increment", f"{len(oi)}",
                 f8["n"]["h=24 六格模型总行数"], f"{int(nr.loc['total_rows']):,}",
                 "OK" if ok8 else "MISMATCH"])

    g.table(["figure", "source table(s)", "rows", "n in figure", "n in table", "match"], rows)

    # ---- 图里不许硬编码：所有数值列都能在源表里找到同名列
    g.section("4. 反硬编码自检（图上每个量都指得回表列）")
    g.check("f8 的三个 W/df/p 标注逐字等于 oi_increment 的 W/df/p 三列",
            by["f8_oi_increment.png"]["extra"]["W/df/p 标注"]
            == [f"W = {float(oi[(oi['statistic'] == 'wald') & (oi['block'] == b)]['estimate'].iloc[0]):.3f}  "
                f"df = {float(oi[(oi['statistic'] == 'wald') & (oi['block'] == b)]['df'].iloc[0]):.0f}  "
                f"p = {float(oi[(oi['statistic'] == 'wald') & (oi['block'] == b)]['p'].iloc[0]):.3f}"
                for b in ("oi_dimension", "interaction", "joint")],
            "；".join(by["f8_oi_increment.png"]["extra"]["W/df/p 标注"]))
    g.check("f1 的区间来自 baselines_v2 的 ci_lo/ci_hi，且该表的 estimate 与 descriptive_core 的 "
            "mean_winsor 逐格相同（两张表口径一致，不是各画一套）",
            float(by["f1_forward_return.png"]["extra"]["两表均值 max|Δ|"]) <= 1e-12,
            f"max|Δ| = {by['f1_forward_return.png']['extra']['两表均值 max|Δ|']}（1e-16 量级）")
    g.check("f3 的随机行区间来自 [p5, p95]（不是 95% CI）：ci_lo == p5、ci_hi == p95，"
            "图注已写明这一点",
            bool(np.allclose(s24.loc["random", ["ci_lo", "ci_hi"]].to_numpy(dtype="float64"),
                             s24.loc["random", ["p5", "p95"]].to_numpy(dtype="float64"))),
            f"ci [{float(s24.loc['random', 'ci_lo']):+.6f}, {float(s24.loc['random', 'ci_hi']):+.6f}]"
            f" = p5/p95")

    g.section("5. f6 的源表与「只画分数、不画差值」（曾被跳过，ic_decay_v2 已产出）")
    g.check("ic_decay_v2.parquet 存在", IC_PATH.exists(), f"{IC_PATH.name}")
    ic = pd.read_parquet(IC_PATH)
    g.check("★ 源表 24 行 = 2 样本 × 4 个 h × 3 个 score", len(ic) == 24,
            f"{len(ic)} 行；sample {sorted(map(str, ic['sample'].unique()))}，"
            f"h {[int(x) for x in sorted(ic['h'].unique())]}，"
            f"score {sorted(map(str, ic['score'].unique()))}")
    g.check("★ 图里只画两 个分数（four / price），price_minus_four 的 8 行不进图",
            sorted(by["f6_ic_decay.png"]["extra"]["画了哪些分数"]) == ["four", "price"]
            and int((ic["score"] == "price_minus_four").sum()) == 8,
            "画 " + "/".join(by["f6_ic_decay.png"]["extra"]["画了哪些分数"])
            + f"；表里 price_minus_four 有 {int((ic['score'] == 'price_minus_four').sum())} 行（差值，不画）")
    g.check("f6 的 95% 区间来自 se_nw（Newey-West，滞后 = h）：se_nw 全部有限且 > 0",
            bool(np.isfinite(ic["se_nw"]).all()) and bool((ic["se_nw"] > 0).all()),
            f"se_nw ∈ [{float(ic['se_nw'].min()):.2e}, {float(ic['se_nw'].max()):.2e}]")
    g.check("f6 的四个 h=24 点与表一致（图注里的翻转那句话不是手写的）",
            by["f6_ic_decay.png"]["extra"]["h=24 的 IC"]
            == [f"{s}/{sc} "
                f"{float(ic[(ic['sample'] == s) & (ic['score'] == sc) & (ic['h'] == H_MAIN)]['mean_ic'].iloc[0]):+.6f}"
                for s in SAMPLES for sc in ("four", "price")],
            "；".join(by["f6_ic_decay.png"]["extra"]["h=24 的 IC"]))


# ============================================================ D. main
def write_table(df: pd.DataFrame, name: str) -> None:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TBL_DIR / f"{name}.parquet", index=False)
    df.to_csv(TBL_DIR / f"{name}.csv", index=False, encoding="utf-8")
    log(f"写盘 {name}.parquet / .csv（{len(df)} 行 × {df.shape[1]} 列）")


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 · 实验 12 事件路径表 + 8 张图")
    ap.add_argument("--only", default="all", choices=("all", "path", "figures"),
                    help="all = 表 + 图（默认）；path = 只重算事件路径表；figures = 只画图（读已有表）")
    args = ap.parse_args()
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    gate = Gate(f"event_study · 实验 12 事件路径 + 图（figures_v2.py，实现者 I）· "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
    gate.lines.append("样本：headline = in_universe（当月流动性前 50，249 合约）；"
                      "full = 全部 285 合约（含 headline 行）。"
                      f"freq={FREQ}，k ∈ [−{PATH_K}, +{PATH_K}]")
    gate.lines.append("单位：表里一律小数（D14.2）；图里 f1/f2/f4/f5 用百分数（×100）、"
                      "f3/f7 用 bp（×1e4）、f8 是 χ² 统计量。图注逐张写明样本 / 口径 / 单位")

    figs: list[dict] = []
    if args.only in ("all", "path"):
        df, audit = build_path(gate)
        gate_path(gate, df, audit)
        if gate.n_fail:
            txt = gate.text("有 FAIL → 停在写表之前（闸门没过时表里的数不可信）")
            CHECKS_PATH.write_text(txt, encoding="utf-8")
            print(txt)
            log(f"闸门写盘 {CHECKS_PATH}（FAIL {gate.n_fail} 项，停止）")
            return 1
        gate_v1(gate, df)
        write_table(df, PATH_TABLE)
        if args.only == "path":
            print(gate.text("--only path：只重算事件路径表，不画图（不写闸门文件）"))
            return 0

    if args.only in ("all", "figures"):
        figs = draw_all()
        gate_figures(gate, figs)

    if gate.n_fail:
        txt = gate.text("有 FAIL → 图或 n 核对没过，先看 §3/§4")
        CHECKS_PATH.write_text(txt, encoding="utf-8")
        print(txt)
        log(f"闸门写盘 {CHECKS_PATH}（FAIL {gate.n_fail} 项）")
        return 1

    n_ok, n_drop = path_drop()
    ic_tab = table("ic_decay_v2")
    ic24 = {(s, sc): float(ic_tab[(ic_tab["sample"] == s) & (ic_tab["score"] == sc)
                                  & (ic_tab["h"] == H_MAIN)]["mean_ic"].iloc[0])
            for s in SAMPLES for sc in ("four", "price")}
    footer = (
        "读图须知：\n"
        "1) f2 是本阶段**唯一**用原始收益的图：cum_k = P(T+k)/P(T) − 1，不中性化、不截尾。"
        "它回答「事件前后价格怎么走」，不回答「有没有超额收益」—— 后者看 f1/f3/f7（winsor 口径）。"
        "两种口径不可混读：事件那一小时的移动在 f2 里就是全部左半边的来源。\n"
        "2) f2 的 8 个面板各有独立纵轴：左半边（事件前）跨几个百分点，右半边（事件后）约 1 个百分点。"
        "不要跨面板比斜率；要数值请读 event_path_v2.parquet 的 mean_cum / median_cum。\n"
        "3) f3 的 random 那根误差棒是 1000 轮同刻随机合约重抽的 [p5, p95]（90%，Monte-Carlo），"
        "其余四根是 estimate ± 1.96·SE（95%，按合约聚类）—— 两种区间不是同一个对象。\n"
        "4) f6（IC 衰减）：IC 用**原始**前向收益、Newey-West 滞后 = h，负值 = 横截面反转。"
        "排序在 h=24 翻转：1/4/8h 是纯价格更强，24h 是四状态更强"
        f"（headline {ic24[('headline', 'four')]:+.4f} vs {ic24[('headline', 'price')]:+.4f}）。"
        "但四状态分数是**稀疏**的（只有事件取 ±1，其余为 0），IC 天然被稀释，这个比较对它不利 ——"
        "它是在这个 handicap 下于 24h 反超的，值得单独一句。表里的 price_minus_four 是差值、不是分数，图上不画。\n"
        f"5) 事件路径剔除了 {n_drop} 个（{n_drop / n_ok:.4%}）ok_24h 事件：它们在 T−24…T−1 缺一个收盘价"
        "（bar 缺行），前置路径画不出来。前向一侧 0 缺失（ok_24h 已保证），所以右半边是同一批人。\n"
        "口径出处：D13（市场中性 + 全池 1%/99% 截尾，用于 f1/f3/f4 的 winsor 口径）；"
        "D14.2（小数）；D14.3（阈值取全市场 pool）；D17（只按合约聚类）；D7（路径极值不截断）；"
        "D19.1（p_cont ≡ 命中率，不是独立证据）；D20（三口径敏感性：原始 +14.94bp / 中性不截尾 "
        "+26.19bp / 中性+截尾 +6.23bp —— f2 画的是路径，不是这三个；DiD 一律以 confirmatory 为准）。\n"
        "复现：python phase3_event/figures_v2.py（表 + 图 + 本文件）；"
        "python phase3_event/figures_v2.py --only path（只重算表）。"
    )
    txt = gate.text(footer)
    CHECKS_PATH.write_text(txt, encoding="utf-8")
    print(txt)
    log(f"闸门写盘 {CHECKS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
