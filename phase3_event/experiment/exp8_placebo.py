"""实验 8 · 安慰剂：每个 regime 的平均前向收益 vs「同合约随机时刻」。

对每个 regime（R1–R4）× 四个前向期：
  真实值   = 该 regime 所有行的 mean(y_raw)（市场中性收益）
  随机分布 = 1000 轮，每轮在与该 regime **同一批合约的全部小时**里随机抽同样数量的时刻
             （任何小时都算，不管价格/OI 动没动、是什么 cell）
  输出     = 真实值、随机 p5/p50/p95、双侧安慰剂 p

只做收益指标：反转概率在随机时刻上没有定义（价格没动的小时谈不上"反转"），
reversal 的对照看实验 1/4 的基准（同一批真实事件里的其余行），不是本节的随机时刻。

写 tables/freq=1h/placebo.parquet / .csv。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402

EVENT = cfg_mod.EVENT
FREQ = "1h"
HS = tuple(sorted(EVENT.horizons))
CELLS = {"R1": 1, "R2": 2, "R3": 3, "R4": 4}

ROOT = HERE.parent.parent
OUT = ROOT / "data" / "06_event_study"
PANEL = OUT / "panel" / f"freq={FREQ}"
TBL = OUT / "tables" / f"freq={FREQ}"
REPS = int(EVENT.random_draws)     # 轮数来自 config，改一处就全链一致
SEED = int(EVENT.random_seed)      # 种子也来自 config（固定 → 结果可复现）
CHUNK = 50

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


def load(h: int) -> pd.DataFrame:
    d = pd.read_parquet(PANEL / f"h={h}.parquet",
                        columns=["symbol", "hour", "cell", "y_raw"])
    d = d.sort_values(["symbol", "hour"], kind="stable").reset_index(drop=True)
    log(f"h={h}: {len(d):,} 行（cell 0 = {int((d['cell'] == 0).sum()):,}，"
        f"cell −1 = {int((d['cell'] == -1).sum()):,}）")
    return d


def placebo(d: pd.DataFrame, h: int) -> list[dict]:
    """每个 regime vs 同合约的纯随机时刻（任何小时都算）。"""
    rng = np.random.default_rng(SEED + h)   # 每个期限一条独立、可复现的随机流
    cc = d["symbol"].to_numpy("int64")
    y = d["y_raw"].to_numpy("float64")
    cell = d["cell"].to_numpy()
    n_cl = int(cc.max()) + 1
    bounds = np.searchsorted(cc, np.arange(n_cl + 1))
    starts, lens = bounds[:-1], bounds[1:] - bounds[:-1]
    rows = []
    for name, cid in CELLS.items():
        ev = np.flatnonzero(cell == cid)
        cid_ev = cc[ev]
        act = float(y[ev].mean())
        sim = np.empty(REPS)
        k = 0
        while k < REPS:
            b = min(CHUNK, REPS - k)
            off = (rng.random((b, ev.size)) * lens[cid_ev]).astype("int64")
            sim[k:k + b] = y[starts[cid_ev][None, :] + off].mean(axis=1)
            k += b
        p5, p50, p95 = (float(x) for x in np.percentile(sim, [5, 50, 95]))
        lo, hi = float((sim <= act).mean()), float((sim >= act).mean())
        rows.append({"experiment": "8 安慰剂", "h": h, "cell": name,
                     "actual": act * 1e4, "rnd_p5": p5 * 1e4,
                     "rnd_p50": p50 * 1e4, "rnd_p95": p95 * 1e4,
                     "p_placebo": min(1.0, 2 * min(lo, hi)),
                     "verdict": ("高于随机 p95" if act > p95 else
                                 "低于随机 p5" if act < p5 else "落在随机区间内"),
                     "n_rows": int(ev.size), "n_rep": REPS})
    return rows


def main() -> int:
    TBL.mkdir(parents=True, exist_ok=True)
    rows = []
    for h in HS:
        rows.extend(placebo(load(h), h))
    df = pd.DataFrame(rows)
    df["note"] = (f"随机时刻 = 与该 regime 同一批合约的**全部小时**里均匀抽（任何状态，"
                  f"不管价格/OI 动没动）；每个格子 {REPS} 轮；"
                  "p_placebo 是双侧经验 p（2×min(≤,≥)）；单位 bp；种子 = config.EVENT.random_seed + h，轮数 = config.EVENT.random_draws。"
                  "只做收益：反转概率在随机时刻上没有定义。"
"只做收益：反转概率在随机时刻上没有定义。")
    df.to_parquet(TBL / "placebo.parquet", index=False)
    df.to_csv(TBL / "placebo.csv", index=False, encoding="utf-8")
    log(f"写盘 placebo.parquet / .csv（{len(df)} 行）")
    for h in HS:
        s = df[df["h"] == h]
        log(f"  h={h:<2d} " + "  ".join(
            f"{r['cell']} {r['actual']:+6.2f}[{r['rnd_p5']:+5.2f},{r['rnd_p95']:+5.2f}]"
            for _, r in s.iterrows()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
