"""Phase 3 · §15 日频汇总稳健性 —— 把观测压到「合约 × 自然日」后重跑实验 1 与实验 3

note 的第三条要求是 *Daily aggregation for robustness*。这一步不改任何上游数据、不改事件定义，
只换**观测单位**：从「1 小时行」换成「合约 × 自然日 × 方向 × 格」，组内对因变量取均值。

口径（与实验 1/3 只差观测单位这一处）：
- 样本：headline、`ok_{h}h`、`dir != 0`（价格超阈），与 exp1_4.py 完全同一批行
- 聚合键：(symbol, day, dir, cell)，day = hour // 24（UTC 自然日）
  · `dir` 进键是必须的：`cell == 0`（价格超阈但 OI 安静）同时含涨和跌两种行
  · `y` 取组内 `y_raw` 均值；`lrv` 取组内均值（跳过 NaN；全 NaN 的组整组丢掉，与 exp1_4
    的 `isfinite` 过滤等价）
- 检验：合约 + 月份**双向固定效应**、合约 + 月份**双向聚类**；
  样本 = 同向、价格超阈的全部行（含该状态自己），基准/比较组 = 其中 dummy=0 的行
  （另一个状态 + OI 安静行）—— 一个字都没改，只是每一行现在是「信号日」而不是「1 小时」
- 权重变了：从「每个事件等权」变成「每个信号日等权」。这正是这一步要检验的东西

规模（h=1 实测）：dir != 0 的 555,008 行 → 276,389 个（合约×日×方向×格）组；
R1 39,292 / R2 32,147 / R3 28,457 / R4 46,846；OI 安静（cell=0）129,647（dir=+1 65,280 / dir=−1 64,367）。

能说 / 不能说：
- 能说：把观测压到日频、每个信号日等权之后，实验 1/3 的结论还在不在
- **不能说**：日线 bar 定义的事件下也成立（那是「1d 标签」，是换定义，不是聚合）

用法：python phase3_event/experiment/robust_daily.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "phase3_event"))

from config import EVENT  # noqa: E402
import infer as I  # noqa: E402

HORIZONS = list(EVENT.horizons)
PANEL = ROOT / "data/06_event_study/panel/freq=1h"
TABLE_DIR = ROOT / "data/06_event_study/tables/freq=1h"
T0 = pd.Timestamp("2021-12-01", tz="UTC")
CELLS = ((1, 1), (2, 1), (3, -1), (4, -1))
METRICS = (("15 日频·收益", "y"), ("15 日频·波动", "lrv"))
ANCHOR = {1: 39_292, 2: 32_147, 3: 28_457, 4: 46_846}     # h=1 的（合约×日）组数锚点


def aggregate(d: pd.DataFrame) -> pd.DataFrame:
    """把 1 小时行压成「合约 × 日 × 方向 × 格」的组均值。"""
    d = d[d["dir"] != 0].copy()                       # 与 exp1_4 同一批行
    d["day"] = d["hour"] // 24
    d["mth"] = pd.factorize((T0 + pd.to_timedelta(d["hour"], unit="h"))
                            .dt.strftime("%Y-%m"))[0]
    return (d.groupby(["symbol", "mth", "day", "dir", "cell"], as_index=False, sort=True)
              .agg(y=("y_raw", "mean"), lrv=("lrv", "mean"), n=("y_raw", "size")))


def fit(sub: pd.DataFrame, ycol: str, cell: int) -> tuple[float, float]:
    """双向固定效应 OLS；丢掉被解释变量非有限的行（与 exp1_4.fit 同规格）。"""
    s = sub[np.isfinite(sub[ycol].to_numpy("float64"))]
    cc = s["symbol"].to_numpy("int64")
    mm = s["mth"].to_numpy("int64")
    X = (s["cell"].to_numpy() == cell).astype("float64")[:, None]
    beta, _, se = I.fe_ols(s[ycol].to_numpy("float64"), X, cc, int(cc.max()) + 1,
                           mm, int(mm.max()) + 1)
    return float(beta[0]), float(se[0])


def drop5(sub: pd.DataFrame, ycol: str, cell: int) -> float:
    """剔除贡献最大的 5 个合约后重估的 t（与 exp1_4 同做法）。"""
    s = sub[np.isfinite(sub[ycol].to_numpy("float64"))].reset_index(drop=True)
    cc = s["symbol"].to_numpy("int64")
    mm = s["mth"].to_numpy("int64")
    n_c, n_m = int(cc.max()) + 1, int(mm.max()) + 1
    x = (s["cell"].to_numpy() == cell).astype("float64")
    y = s[ycol].to_numpy("float64")
    Xd = I.demean2(x, cc, n_c, mm, n_m)
    yd = I.demean2(y, cc, n_c, mm, n_m)
    b = float(Xd @ yd / float(Xd @ Xd))
    score = np.bincount(cc, weights=Xd * (yd - b * Xd), minlength=n_c)
    worst = np.argsort(-np.abs(score))[:5]
    s2 = s[~np.isin(cc, worst)].reset_index(drop=True)
    return fit(s2, ycol, cell)[0] / fit(s2, ycol, cell)[1]


def self_test() -> list[tuple[bool, str, str]]:
    """已知答案验证：每个「合约 × 月 × 日」的 A 组 = +2bp、B 组 = −3bp（噪声组内均值归零），
    先过聚合、再过双向 FE，必须精确复现 +5bp。"""
    rng = np.random.default_rng(11)
    rows = []
    for c in range(30):
        for m in range(8):
            for day in range(10):
                hour = m * 720 + day * 24                 # 每块 30 天
                for cell, base in ((1, 2e-4), (0, -3e-4)):
                    e = rng.normal(0, 1e-3, 2)
                    e -= e.mean()                         # 组内均值归零 → 组均值精确等于 base
                    for v in e:
                        rows.append({"symbol": c, "hour": hour, "dir": 1,
                                     "cell": cell, "y_raw": base + v, "lrv": np.nan})
    raw = pd.DataFrame(rows)
    g = aggregate(raw)
    est, se = fit(g[g["dir"] == 1].reset_index(drop=True), "y", 1)
    return [
        (abs(est - 5e-4) < 1e-12, "自检：聚合 + 双向 FE 精确复现已知 +5bp",
         f"{est*1e4:+.6f}bp（SE {se*1e4:.4f}bp）"),
        (len(g) == 30 * 8 * 10 * 2, "自检：聚合后组数 = 合约×月×日×格",
         f"{len(g):,} = 30×8×10×2"),
    ]


def by_count(d: pd.DataFrame) -> pd.DataFrame:
    """机制表：把每个（合约×日）按「当天该格的小时数」分桶（1/2/3/4/5+），
    报每天等权的均值与行等权的均值。

    这张表解释「为什么日频汇总会给出不同答案」——它不是检验，只报数。
    """
    d = d[d["dir"] != 0].copy()
    d["day"] = d["hour"] // 24
    rows = []
    for cell in (1, 2, 3, 4):
        sub = d[d["cell"] == cell]
        g = sub.groupby(["symbol", "day"])["y_raw"].agg(["mean", "size"])
        g["bucket"] = np.minimum(g["size"], 5)
        for b, gb in g.groupby("bucket"):
            rows.append(dict(cell=f"R{cell}", bucket=int(b), n_days=int(len(gb)),
                             n_rows=int(gb["size"].sum()),
                             daymean=float(gb["mean"].mean())))
    return pd.DataFrame(rows)


def main() -> int:
    t0 = time.time()
    gate = self_test()
    rows = []
    bc = []

    def check(name, cond, detail=""):
        gate.append((bool(cond), name, detail))

    for h in HORIZONS:
        d = pd.read_parquet(PANEL / f"h={h}.parquet",
                            columns=["symbol", "hour", "dir", "cell", "y_raw", "lrv"])
        g = aggregate(d)
        n_src = int((d["dir"] != 0).sum())
        print(f"  h={h:<3} 行 {n_src:,} → 组 {len(g):,}", flush=True)
        check(f"h={h} 组内行数之和 = 原来的行数", int(g["n"].sum()) == n_src,
              f"{int(g['n'].sum()):,} = {n_src:,}")

        b = by_count(d)
        b.insert(0, "h", h)
        bc.append(b)
        n_ev = int((d["cell"] >= 1).sum())          # 机制表只覆盖 R1–R4 的行
        check(f"h={h} 机制表行数守恒、桶数 = 4 格 × 5 桶",
              int(b["n_rows"].sum()) == n_ev and len(b) == 20,
              f"{int(b['n_rows'].sum()):,} = {n_ev:,}；{len(b)} 行")

        for cell, dirv in CELLS:
            sub = g[g["dir"] == dirv].reset_index(drop=True)
            if h == 1:
                n_cell = int(g[g["cell"] == cell].shape[0])
                check(f"h=1 R{cell} 的（合约×日）组数 = {ANCHOR[cell]:,}",
                      n_cell == ANCHOR[cell], f"{n_cell:,}")
            for nm, ycol in METRICS:
                est, se = fit(sub, ycol, cell)
                rows.append(dict(experiment=nm, h=h, cell=f"R{cell}", estimate=est, se=se,
                                 n_groups=len(sub), t_drop5=drop5(sub, ycol, cell)))
                shown = (f"{est*1e4:+8.3f}bp" if ycol == "y"
                         else f"{(np.exp(est)-1)*100:+8.2f}%")
                print(f"    h={h:<3} R{cell} {nm[2:]:<4} {shown}  t {est/se:+6.2f}  "
                      f"组 {len(sub):,}", flush=True)

    out = pd.DataFrame(rows)
    out["ci_lo"] = out["estimate"] - 1.96 * out["se"]
    out["ci_hi"] = out["estimate"] + 1.96 * out["se"]
    out["t"] = out["estimate"] / out["se"]
    out["p"] = [I.p_two(x) if np.isfinite(x) else np.nan for x in out["t"]]
    out["p_bh"] = np.nan
    for nm in out["experiment"].unique():          # BH 家族 = 每个指标 16 个（4 格 × 4 期）
        msk = out["experiment"] == nm
        out.loc[msk, "p_bh"] = I.bh(out.loc[msk, "p"].to_numpy())

    check("行数 = 2 个指标 × 4 格 × 4 期", len(out) == 32, f"{len(out)} 行")
    check("SE 全部 > 0", bool((out["se"] > 0).all()), f"min {out['se'].min():.3e}")
    check("t 与 t_drop5 全部有限",
          bool(np.isfinite(out["t"]).all() and np.isfinite(out["t_drop5"]).all()), "")

    cols = ["experiment", "h", "cell", "estimate", "se", "ci_lo", "ci_hi",
            "t", "p", "p_bh", "t_drop5", "n_groups"]
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    out[cols].to_parquet(TABLE_DIR / "robust_daily.parquet", index=False)
    out[cols].to_csv(TABLE_DIR / "robust_daily.csv", index=False, encoding="utf-8-sig")
    bcdf = pd.concat(bc, ignore_index=True)
    bcdf.to_parquet(TABLE_DIR / "robust_daily_bycount.parquet", index=False)
    bcdf.to_csv(TABLE_DIR / "robust_daily_bycount.csv", index=False, encoding="utf-8-sig")

    n_pass = sum(x for x, _, _ in gate)
    for x, n, dd in gate:
        print(f"  [{'PASS' if x else 'FAIL'}] {n}  {dd}")
    print("\n=== 15 日频汇总（观测 = 合约×日×格）===")
    print(out[["experiment", "h", "cell", "estimate", "t", "p_bh", "t_drop5", "n_groups"]]
          .to_string(index=False, float_format=lambda v: f"{v:+.6f}"))
    print("\n=== 机制：R1 的收益随「当天 R1 小时数」单调上升（h=1，每天等权；bp）===")
    b1 = bcdf[(bcdf["h"] == 1)]
    for cell in ("R1", "R2", "R3", "R4"):
        s = b1[b1["cell"] == cell].set_index("bucket")
        print(f"  {cell}: " + "  ".join(f"{b}个 {s.loc[b, 'daymean']*1e4:+7.1f}({int(s.loc[b, 'n_days']):,}天)"
                                        for b in s.index))
    print(f"\n闸门 PASS {n_pass}/{len(gate)}；耗时 {time.time()-t0:.0f}s")
    return 0 if n_pass == len(gate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
