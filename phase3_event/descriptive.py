"""Phase 3 · descriptive —— 实验 9 / 10 / 11 / 14（实现者 F）

一句话
    这四张表**只报数、不做判定**（`PHASE3_GUIDANCE.md` 第二节）：每格的基本面、
    续势/反转/无效应比例、路径风险、分合约与分市场状态。表里**没有任何 p 值、t 值、
    SE 或区间**——描述层不放推断，D15.2 取消等价性检验之后也不放"可排除超过 N bp"
    这类结论。闸门 §5 有一条**列名断言**专门守这件事，而且它自己也被证明能失败。

样本（一处定义，全文共用）
    headline = `in_universe == True`，再按每个前向期各自的 `ok_{h}h` 过滤。
    h = 1 / 4 / 8 / 24（`EventConfig.horizons`），四格 R1–R4 = 价格符号 × OI 符号：
    R1=(P+1,q+1) / R2=(P+1,q−1) / R3=(P−1,q+1) / R4=(P−1,q−1)（方向由
    `confirmatory.py` 实测核对过，本文件沿用同一个 `PQ` 映射）。

    实测底数（闸门 §0 逐项钉住）：
      headline 事件 **256,079**，格 R1 74,959 / R2 50,564 / R3 44,623 / R4 85,933，
      合约 **249** 个（全样本 285 个，本文件不用）。
      每个 h 的有效事件数（`ok_{h}h` 为真）：256,076 / 256,063 / 256,028 / **255,807**，
      被丢的 3 / 16 / 51 / 272 行进 `n_invalid`（D9）。
      h=24 的四格 n = 74,875 / 50,519 / 44,585 / 85,828，与 `confirmatory.py` 的锚点一致。

四个实验（口径逐条写在下面，不许在表里改）

  实验 9 · 每格基本面（`descriptive_core.parquet` 的前半）
      每（h × 格）报：`n`、均值与中位数（**winsor 口径**，即 D13/D14.3 的全池
      1%/99% 阈值压过的那一列）、命中率 `hit_raw`（= `mean(hit_{h}h)`，押对方向）、
      平均与中位 `rv_{h}h`、被截尾比例
      `mean(winsor_fwd ≠ excess_fwd)`。另按已有表 `descriptive_four_cell.parquet`
      的列序补 `mean/median_raw` 与 `mean/median_excess` 三条对照口径，好让
      "市场中性 + 截尾"到底动了多少一眼看见。**不放 p 值、不放 t。**
      这张表是已有 `descriptive_four_cell` 的**扩充**（4 个 h 而不是只有 24），
      所以 h=24 那 4 行必须逐项不变——闸门 §1 就是这条连续性（只比 12 个共同列；
      已有表里的 `hit_neutral`（中性口径命中率）已删，本表只剩 `hit_raw`）。

  实验 10 · 续势 / 反转 / 无效应比例（同一张表的后半：`p_cont` / `p_rev` / `p_flat`）
      定义就在事件表里（`build_event_table.py`），本文件只取均值，不重新定义：
        cont_h = 1{sign(fwd_h) == sign(price_change)}        续势
        rev_h  = 1{sign(fwd_h) == −sign(price_change)}       反转
        flat_h = 1{fwd_h == 0}                               无效应
      三者互斥且穷尽 → 每格相加恒为 1。
      ⚠️ **表注（`note` 列，逐行携带）**：`p_cont ≡ hit_rate`。这是**恒等式**，
      不是独立证据：事件行里 `d = sign(price_change)`，而
      `hit_h = 1{sign(fwd_h) = d 且 fwd_h ≠ 0}`，`cont_h` 已蕴含 `fwd_h ≠ 0`，
      所以两者逐元素相等。GUIDANCE 说的"32 格完全相等"是本阶段 headline + full 两样本
      × 4 格 × 4 期的家族；本表只含 headline，是其中的 **16 格**，逐格相等（闸门 §2
      实测 max|Δ| = 0，并另用原始 `fwd` 列重算一遍证明它不是复制列）。

  实验 11 · 路径风险（`descriptive_path.parquet`）
      每（h × 格）报 `mfe_{h}h` / `mae_{h}h` / `mdd_{h}h` 的**均值与 p10/p50/p90**。
      口径：`mfe` / `mae` 已按方向翻正（`d = −1` 的行在
      `build_event_table.py` 里取反），所以 `mfe` ≈ 有利偏移（多数 ≥ 0）、
      `mae` ≈ 不利偏移（多数 ≤ 0）、`mdd` **恒 ≤ 0**。
      三者都是**未截尾**的路径极值：D7 明令不截断、不加 flag（`mfe < 0` 与
      `mae > 0` 是真实路径——事件后立刻跳空），所以**均值会被极少数极端路径主导**，
      p50 与分位才是典型口径。每行附 `share_mfe_negative` / `share_mae_positive`
      把 D7 的例外比例摆在表里，省得下游以为被截过。**不加任何推断。**

  实验 14 · 分合约、分市场状态（`descriptive_by_symbol.parquet` / `..._by_state.parquet`）
      · 按 `symbol`：每（合约 × 格 × h）报 `n`、均值、中位数、命中率 `hit_raw`、
        平均 rv、被截尾比例。
      · 按 `mkt_vol_state`（low / mid / high）：同一组列。
      **不做任何显著性检验**：GUIDANCE 明令不要"64 个没有进任何家族的检验"。
      行数：by_symbol **3,980** = 249 合约 × 4 格 × 4 期 − 4（BSBUSDT 在所有 4 个 h 上
      都没有 R3 事件，即该合约从未出现"价格跌 + OI 增"）；闸门 §4 钉住
      `≤ 合约数 × 4 × 4` 这个上界。by_state **48** = 3 状态 × 4 格 × 4 期（每格非空）。
      第四个取值 `unknown` 不算一种市场状态 —— 它只覆盖 2021-12…2022-03，是"波动率分位
      还没攒够一年"的产物 —— 所以整行排除；每 h 排掉 3,604 行、四个 h 合计 14,416 行，
      闸门 §4 把这批行数逐 h 打出来，证明是有意排除而不是静默丢掉。

单位（D14.2）
    内部与表里一律**小数**：`mean_winsor = -0.001074`（不是 −0.1074%）。
    ×100 即百分数，×1e4 即 bp。`hit_*` / `p_*` / `share_*` 是 0–1 的比例；
    `rv` 是小数波动（不是 log）；`n` 是计数。表沿用 `descriptive_four_cell`
    的做法不设 unit 列（那张表也没有），单位写在各表的 `note` 列与本文件里。

为什么只用 `stats_core` 的两个基元
    这四张表是纯描述统计（计数 / 均值 / 中位数 / 分位 / 比例），**没有推断**，所以
    `cluster_se` / `wald_test` / `cell_medians_boot` / `*_cell_design` 一个都不调
    ——调了就会往表里塞 SE 和 p，直接违反"表里不放 p 值"。真正用到的只有：
      * `sc.winsorize`（§0 闸门：把 `excess_fwd_{h}h` 按**全池**阈值重压一遍，必须
        逐元素等于表里的 `winsor_fwd_{h}h`。按格内压会立刻失败 —— D14.3 的守门人）；
      * `sc.kurtosis`（§0 闸门：截尾列峰度必须远小于未截尾列，证明"winsor 口径的
        均值"真的是截尾后的，而不是原始收益冒充）；
      * `sc.WINSOR_LOWER / WINSOR_UPPER`（读回 `winsor_thresholds.json` 时核对分位）。
    参数全部从 `config.EventConfig` 读（`horizons` / `winsor_lower` /
    `winsor_upper`），脚本里不写常数。

输出
    data/06_event_study/tables/freq=1h/descriptive_core.parquet       （实验 9 + 10）+ .csv
    data/06_event_study/tables/freq=1h/descriptive_path.parquet       （实验 11）    + .csv
    data/06_event_study/tables/freq=1h/descriptive_by_symbol.parquet  （实验 14）    + .csv
    data/06_event_study/tables/freq=1h/descriptive_by_state.parquet   （实验 14）    + .csv
    data/06_event_study/docs/step9_checks_descriptive.txt             （闸门全文）

只读依赖
    `events/events_1h.parquet`               冻结产物（923,235 行 × 73 列），只读
    `docs/winsor_thresholds.json`            全池截尾阈值（h=24），只读
    `tables/freq=1h/descriptive_four_cell.parquet`  已有的 h=24 四格表，只读，
        用来钉"扩充后 h=24 那一段逐项不变"——这是"扩充已有表"的连续性证据

闸门（必须能失败；期望数字一律来自实测底数）
    §0 样本与输入：headline 256,079 / 249 合约 / 每 h 有效数 / (hour,symbol) 唯一 /
       单位量级 / d == sign(price_change) / 截尾口径逐 h 重压 / 峰度 50 以下
    §1 实验 9：★ 每个 h 的四格 n 之和 = 该 h 的有效事件数；n_invalid 之和 = 256,079 − 有效数；
       ★ 扩充后 h=24 与已有 four_cell 表逐项不变（1e-12）
    §2 实验 10：★ p_cont + p_rev + p_flat = 1（1e-9）；★ p_cont == hit_rate（1e-12）；
       ★ 恒等式由原始 fwd 列重算得出来；★ cont 与 hit 两列逐元素相等；表注必须在表里
    §3 实验 11：★ mdd ≤ 0 恒成立（原始列与表里两处）；分位单调；均值在原始极值区间内；
       D7 的符号例外仍存在（没被截断）
    §4 实验 14：★ by_symbol 行数 ≤ 合约数 × 4 × 4；每 h 的 n 之和 = 该 h 有效数；
       按 n 加权的均值 = core 的均值（1e-12）；by_state 48 行、状态集合 = {low, mid, high}；
       ★ 被排除的 unknown 行数逐 h 打出（3,604 × 4 = 14,416），排除后仍对得回有效事件数
    §5 表结构：★ 四张表都不含任何 p 值 / t / SE / 区间列（列名断言）；
       ★ 该断言能失败（8 种故意污染的列名全被抓到）；白名单不误伤 p_cont / p_rev / p_flat

用法
    python phase3_event/descriptive.py      # 全部 PASS 退出码 0，任一 FAIL 退出码 1
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

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
HS = tuple(sorted(EVENT.horizons))       # (1, 4, 8, 24)
H = max(HS)                              # 主前向期 = 24
"""前向期与列名全部由 `EventConfig.horizons` 生成，避免"手写 24h 与参数不一致"。"""

CELLS = ("R1", "R2", "R3", "R4")
PQ = {"R1": (+1, +1), "R2": (+1, -1), "R3": (-1, +1), "R4": (-1, -1)}
STATES = ("low", "mid", "high")
"""市场波动状态，只有这三档入表。`unknown` 不是一种市场状态：它只覆盖 2021-12…2022-03，
是"波动率分位还没攒够一年"的产物，所以整行排除、不并入任何一档，也不单列成第四档
（被排除的行数逐 h 打在闸门 §4 里，不是静默丢掉）。"""

ROOT = HERE.parent
OUT_ROOT = ROOT / "data" / "06_event_study"
EV_PATH = OUT_ROOT / "events" / f"events_{FREQ}.parquet"
TBL_DIR = OUT_ROOT / "tables" / f"freq={FREQ}"
DOC_DIR = OUT_ROOT / "docs"
CHECKS_PATH = DOC_DIR / "step9_checks_descriptive.txt"
THR_PATH = DOC_DIR / "winsor_thresholds.json"
FOUR_CELL_PATH = TBL_DIR / "descriptive_four_cell.parquet"

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


# ============================================================ 0. 样本
BASE_COLS = ["symbol", "regime", "in_universe", "mkt_vol_state", "d", "price_change", "hour"]


def horizon_cols(h: int) -> list[str]:
    """该前向期要读的列（只读这些，不把 73 列全搬进内存）。"""
    return ([f"ok_{h}h"]
            + [f"{b}_fwd_{h}h" for b in ("excess", "winsor")]
            + [f"fwd_{h}h", f"rv_{h}h"]
            + [f"{b}_{h}h" for b in ("hit", "cont", "rev", "flat", "mfe", "mae", "mdd")])


def load_base() -> pd.DataFrame:
    """事件表的底料：合约、格、样本标记、市场状态、方向、价格变动、小时。"""
    base = pd.read_parquet(EV_PATH, columns=BASE_COLS)
    head = base["in_universe"].to_numpy(dtype=bool)
    log(f"事件表 {len(base):,} 行；headline {int(head.sum()):,} 行；"
        f"合约 {int(base['symbol'].nunique())} 个（headline "
        f"{int(base.loc[head, 'symbol'].nunique())} 个）")
    return base


def build_horizon(base: pd.DataFrame, h: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """某个 h 的**有效样本**与**无效行索引**。

    返回
        (s, inv)
        s     headline ∩ ok_{h}h 的行，按 (hour, symbol) 稳定排序（与 confirmatory.py
              同序，这样 h=24 的均值/中位数能逐位对上已有表）。列全是 float64 或字符串。
        inv   被 ok_{h}h 丢掉的 headline 行，只留 symbol / regime / state 三列，供调用方
              按任意键数出 `n_invalid`（D9：每张表都带这一列）。

    派生列
        clipped        = 1{winsor ≠ excess}（被截尾比例）
        cont_rebuilt   = 1{sign(fwd) == sign(price_change)}（独立重建实验 10 的 p_cont）
        flat_rebuilt   = 1{fwd == 0}（独立重建 p_flat）
    后两列不落表，只给闸门用：恒等式必须由**原始 fwd 列**重算得出来，而不是复制列。
    """
    d = pd.read_parquet(EV_PATH, columns=horizon_cols(h))
    head = base["in_universe"].to_numpy(dtype=bool)
    ok = d[f"ok_{h}h"].to_numpy(dtype=bool)
    keep = head & ok
    bad = head & ~ok

    def col(name: str, mask: np.ndarray) -> np.ndarray:
        return d[name].to_numpy(dtype="float64")[mask]

    sym = base["symbol"].to_numpy()
    reg = base["regime"].to_numpy()
    st = base["mkt_vol_state"].to_numpy()
    s = pd.DataFrame({
        "hour": base["hour"].to_numpy()[keep],
        "symbol": sym[keep],
        "regime": reg[keep],
        "state": st[keep],
        "d": base["d"].to_numpy(dtype="float64")[keep],
        "winsor": col(f"winsor_fwd_{h}h", keep),
        "excess": col(f"excess_fwd_{h}h", keep),
        "raw": col(f"fwd_{h}h", keep),
        "rv": col(f"rv_{h}h", keep),
        "hit": col(f"hit_{h}h", keep),
        "cont": col(f"cont_{h}h", keep),
        "rev": col(f"rev_{h}h", keep),
        "flat": col(f"flat_{h}h", keep),
        "mfe": col(f"mfe_{h}h", keep),
        "mae": col(f"mae_{h}h", keep),
        "mdd": col(f"mdd_{h}h", keep),
        "price_change": base["price_change"].to_numpy(dtype="float64")[keep],
    })
    s["clipped"] = (s["winsor"].to_numpy() != s["excess"].to_numpy()).astype("float64")
    s["cont_rebuilt"] = (np.sign(s["raw"].to_numpy())
                         == np.sign(s["price_change"].to_numpy())).astype("float64")
    s["flat_rebuilt"] = (s["raw"].to_numpy() == 0.0).astype("float64")
    s = s.sort_values(["hour", "symbol"], kind="stable").reset_index(drop=True)

    inv = pd.DataFrame({"symbol": sym[bad], "regime": reg[bad], "state": st[bad]})
    log(f"h={h:2d}：有效 {len(s):,} 行（n_invalid {len(inv)} 行）；"
        f"格 { {c: int((s['regime'].to_numpy() == c).sum()) for c in CELLS} }")
    return s, inv


# ============================================================ 1. 逐格统计
CORE_AGGS = {
    "n": ("winsor", "size"),
    "mean_winsor": ("winsor", "mean"),
    "median_winsor": ("winsor", "median"),
    "mean_raw": ("raw", "mean"),
    "median_raw": ("raw", "median"),
    "mean_excess": ("excess", "mean"),
    "median_excess": ("excess", "median"),
    "hit_raw": ("hit", "mean"),
    "mean_rv": ("rv", "mean"),
    "median_rv": ("rv", "median"),
    "share_winsorized": ("clipped", "mean"),
    "p_cont": ("cont", "mean"),
    "p_rev": ("rev", "mean"),
    "p_flat": ("flat", "mean"),
}
REBUILT_AGGS = {"cont_rebuilt": ("cont_rebuilt", "mean"),
                "flat_rebuilt": ("flat_rebuilt", "mean")}
"""键 → (列, 聚合)。`p_cont` / `p_rev` / `p_flat` 就是三列的均值（它们本身是 0/1），所以
"相加为 1"与"等于 hit 列均值"都是可验证的算术，不是嘴上的话。"""


def cell_aggs(s: pd.DataFrame, keys: list[str], rebuilt: bool = False) -> pd.DataFrame:
    """按 `keys` 分组算全套描述统计（索引 = keys 的升序）。"""
    aggs = dict(CORE_AGGS)
    if rebuilt:
        aggs.update(REBUILT_AGGS)
    return s.groupby(keys, observed=True).agg(**aggs)


def valid_counts(inv: pd.DataFrame, keys: list[str]) -> pd.Series:
    """`n_invalid`：被 ok 掩码丢掉的 headline 行数，按同一组键。"""
    return inv.groupby(keys, observed=True).size().rename("n_invalid")


# ============================================================ 2. 实验 9 + 10
NOTE_CORE = (
    "p_cont ≡ hit_rate（恒等式，不是独立证据）：cont=1{sign(fwd_h)=sign(price_change)}、"
    "hit=cont 且 fwd_h≠0，事件行里两者逐元素相等；本表 %d 格逐格相等，max|Δ|=%.1e。"
    "GUIDANCE 的'32 格'是 headline+full × 4 格 × 4 期的家族，本表只含 headline 的 16 格。"
    "均值/中位数 = 全池 1%%/99%% 截尾后的市场中性收益（小数，×100 即百分数）；"
    "hit_*、p_*、share_* 为 0–1 比例；rv 为小数波动（非 log）；n 为计数。"
    "描述层：不放 p 值、不放 t、不做等价性结论（D15.2）。"
)


def build_core(samples: dict[int, pd.DataFrame], invs: dict[int, pd.DataFrame],
               ident: dict) -> pd.DataFrame:
    """实验 9（基本面）+ 实验 10（续势/反转/无效应），一张宽表 16 行。"""
    rows = []
    for h in HS:
        a = cell_aggs(samples[h], ["regime"], rebuilt=True)
        inv = valid_counts(invs[h], ["regime"])
        n_h = len(samples[h])
        for cell in CELLS:
            r = a.loc[cell]
            rows.append({
                "sample": "headline", "h": h, "cell": cell,
                "price_sign": PQ[cell][0], "oi_sign": PQ[cell][1],
                "n": int(r["n"]),
                "n_invalid": int(inv.get(cell, 0)),
                "share_of_sample": float(r["n"]) / n_h,
                "mean_winsor": float(r["mean_winsor"]),
                "median_winsor": float(r["median_winsor"]),
                "mean_raw": float(r["mean_raw"]),
                "median_raw": float(r["median_raw"]),
                "mean_excess": float(r["mean_excess"]),
                "median_excess": float(r["median_excess"]),
                "hit_raw": float(r["hit_raw"]),
                "mean_rv": float(r["mean_rv"]),
                "median_rv": float(r["median_rv"]),
                "share_winsorized": float(r["share_winsorized"]),
                "p_cont": float(r["p_cont"]),
                "p_rev": float(r["p_rev"]),
                "p_flat": float(r["p_flat"]),
            })
    df = pd.DataFrame(rows)
    df["note"] = NOTE_CORE % (ident["n_cells"], ident["max_abs"])
    return df


def identity_check(samples: dict[int, pd.DataFrame]) -> dict:
    """p_cont ≡ hit_rate 的实测差（逐格），表注与闸门都引用它。

    max_abs         16 格里 |p_cont − hit_raw| 的最大值；n_cells 是格数。
    max_abs_rebuilt 用**原始 fwd 列**重建的 p_cont / p_flat 与表里那两列的差，
                    证明恒等式来自定义而不是"同一列的复制"。
    """
    worst, worst_rebuilt, n_cells, n_eq = 0.0, 0.0, 0, 0
    for h in HS:
        a = cell_aggs(samples[h], ["regime"], rebuilt=True)
        for cell in CELLS:
            r = a.loc[cell]
            dev = abs(float(r["p_cont"]) - float(r["hit_raw"]))
            worst = max(worst, dev)
            n_eq += int(dev == 0.0)
            n_cells += 1
            worst_rebuilt = max(worst_rebuilt,
                                abs(float(r["cont_rebuilt"]) - float(r["p_cont"])),
                                abs(float(r["flat_rebuilt"]) - float(r["p_flat"])))
    return {"max_abs": worst, "max_abs_rebuilt": worst_rebuilt,
            "n_cells": n_cells, "n_exact": n_eq}


# ============================================================ 3. 实验 11
NOTE_PATH = (
    "mfe/mae 已按方向翻正（d=−1 的行取反），mdd 恒 ≤ 0；三者都**未截尾**（D7：不截断、不加 flag），"
    "所以均值会被极少数极端路径主导，p10/p50/p90 才是典型口径（小数，×100 即百分数）。"
    "share_mfe_negative / share_mae_positive 是 D7 的符号例外比例（真实路径，不是数据错误）。"
    "描述层：不加任何推断。"
)


def build_path(samples: dict[int, pd.DataFrame], invs: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """实验 11：路径风险的均值与 p10/p50/p90（16 行）。"""
    rows = []
    for h in HS:
        s = samples[h]
        inv = valid_counts(invs[h], ["regime"])
        reg = s["regime"].to_numpy()
        for cell in CELLS:
            m = reg == cell
            row = {"sample": "headline", "h": h, "cell": cell,
                   "price_sign": PQ[cell][0], "oi_sign": PQ[cell][1],
                   "n": int(m.sum()), "n_invalid": int(inv.get(cell, 0))}
            for metric in ("mfe", "mae", "mdd"):
                v = s[metric].to_numpy()[m]
                p10, p50, p90 = (float(x) for x in np.percentile(v, [10.0, 50.0, 90.0]))
                row[f"{metric}_mean"] = float(v.mean())
                row[f"{metric}_p10"] = p10
                row[f"{metric}_p50"] = p50
                row[f"{metric}_p90"] = p90
            row["share_mfe_negative"] = float(np.mean(s["mfe"].to_numpy()[m] < 0.0))
            row["share_mae_positive"] = float(np.mean(s["mae"].to_numpy()[m] > 0.0))
            rows.append(row)
    df = pd.DataFrame(rows)
    df["note"] = NOTE_PATH
    return df


# ============================================================ 4. 实验 14
NOTE_SYMBOL = ("实验 14：分合约描述层，**不做任何显著性检验**（GUIDANCE 明令）。"
               "口径同 descriptive_core：小数收益、0–1 比例、rv 为小数波动。")
NOTE_STATE = ("实验 14：分市场状态（low/mid/high）描述层，**不做任何显著性检验**。"
              "unknown 不是一种市场状态（只覆盖 2021-12…2022-03，波动率分位还没攒够一年），"
              "整行排除、不进本表。口径同 descriptive_core。")

GROUP_COLS = ("n", "mean_winsor", "median_winsor", "hit_raw",
              "mean_rv", "median_rv", "share_winsorized")


def build_grouped(samples: dict[int, pd.DataFrame], invs: dict[int, pd.DataFrame],
                  key: str) -> pd.DataFrame:
    """按 `key`（symbol / state）× 格 × h 的同一组描述统计。

    `key == "state"` 时先整行排除 `unknown`：它只覆盖 2021-12…2022-03，是"波动率分位
    还没攒够一年"的产物，不是一种市场状态，留着会让人把它当第四档去比。每 h 排掉
    3,604 行，所以 by_state 是 3 状态 × 4 格 × 4 h = 48 行。
    """
    parts = []
    for h in HS:
        src = samples[h]
        if key == "state":
            src = src.loc[src["state"].to_numpy() != "unknown"]
        a = cell_aggs(src, [key, "regime"])[list(GROUP_COLS)]
        a = a.join(valid_counts(invs[h], [key, "regime"]), how="left")
        a["n_invalid"] = a["n_invalid"].fillna(0).astype("int64")
        a = a.reset_index().rename(columns={"regime": "cell"})
        a["h"] = h
        a["price_sign"] = a["cell"].map({c: PQ[c][0] for c in CELLS})
        a["oi_sign"] = a["cell"].map({c: PQ[c][1] for c in CELLS})
        parts.append(a)
    df = pd.concat(parts, ignore_index=True)
    df["sample"] = "headline"
    df = df.sort_values([key, "cell", "h"], kind="stable").reset_index(drop=True)
    df = df[["sample", key, "cell", "h", "price_sign", "oi_sign"]
            + [c for c in GROUP_COLS if c != "n"] + ["n", "n_invalid"]]
    df["note"] = NOTE_SYMBOL if key == "symbol" else NOTE_STATE
    return df


# ============================================================ 5. 闸门
INFERENCE_TOKENS = ("p_value", "pvalue", "p_val", "pval", "q_value", "qval", "bh_", "_bh",
                    "fdr", "t_stat", "tstat", "std_err", "wald", "chi2", "_se", "se_",
                    "ci_lo", "ci_hi", "_ci", "signif", "p_adj")
INFERENCE_EXACT = {"p", "t", "se", "z", "q", "chi2", "wald", "estimate"}
PROPORTION_NAMES = {"p_cont", "p_rev", "p_flat"}
"""`PROPORTION_NAMES` 是**比例**（p = proportion），不是 p 值 —— 白名单只放这三个。
`INFERENCE_EXACT` 里的 `estimate` 也要挡：`confirmatory_*.parquet` 的推断表就是
statistic / estimate / se / t / p / ci_lo / ci_hi 那种长表，描述层一张都不许长成那样。"""


def inference_columns(df: pd.DataFrame) -> list[str]:
    """返回"看起来像推断列"的列名。空列表 = 这张表干净。

    规则（任何一条命中就报）：
      * 列名（小写）**恰好**是 p / t / se / z / q / chi2 / wald / estimate；
      * 以 `p_` 开头且不在那三个**比例**白名单里；
      * 含 `INFERENCE_TOKENS` 里任一子串。
    这条断言必须能失败 —— 闸门 §5 用故意污染的表证明它不是恒真。
    """
    bad = []
    for c in df.columns:
        nm = str(c).lower()
        if nm in PROPORTION_NAMES:
            continue
        if nm in INFERENCE_EXACT or nm.startswith("p_") \
                or any(tok in nm for tok in INFERENCE_TOKENS):
            bad.append(str(c))
    return bad


class Gate:
    """逐项记录 PASS/FAIL；任一 FAIL → 退出码 1。"""

    def __init__(self, header: str) -> None:
        self.lines = [header]
        self.n_pass = 0
        self.n_fail = 0

    def _emit(self, ok: bool, body: str) -> None:
        self.n_pass += int(ok)
        self.n_fail += int(not ok)
        self.lines.append("  [" + ("PASS" if ok else "FAIL") + "] " + body)

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(title)

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self._emit(bool(ok), label + (f"  [{detail}]" if detail else ""))

    def near(self, label: str, got: float, exp: float, tol: float = 1e-12,
             fmt: str = "%+.10f") -> None:
        dev = abs(float(got) - float(exp))
        self._emit(dev <= tol,
                   f"{label} = {fmt % float(got)}   期望 {fmt % float(exp)}   |Δ| {dev:.1e}")

    def note(self, body: str) -> None:
        self.lines.append(f"        └ {body}")

    def text(self, footer: str) -> str:
        total = self.n_pass + self.n_fail
        return ("\n".join(self.lines) + "\n\n"
                + f"闸门汇总：PASS {self.n_pass} / FAIL {self.n_fail}（共 {total} 项）\n"
                + footer + "\n")


SUB_N: dict[int, int] = {}          # 每个 h 的有效事件数（main 里填，闸门当期望值用）
CORE_N = np.zeros(0, dtype="int64")  # core 表的 n 列（path 表要对齐它）


# ---------------------------------------------- §0 样本与输入
def winsor_diagnostics(samples: dict[int, pd.DataFrame], thr: dict) -> dict:
    """每个 h 的截尾自洽：重压、阈值、峰度。

    `again` 用样本内 min/max 当阈值重压一遍 —— 这两个极值就是**全池阈值本身**
    （池上 1% 的行被压到 lo、99% 的被压到 hi，headline 子集两端各自都超过 1%，所以
    取满）。h=24 另外与落盘的 json 阈值逐位比对。
    """
    out = {}
    for h in HS:
        s = samples[h]
        win = s["winsor"].to_numpy()
        exc = s["excess"].to_numpy()
        lo, hi = float(win.min()), float(win.max())
        again, _ = sc.winsorize(exc, thresholds=(lo, hi))
        out[h] = {"winsor": win, "again": again,
                  "d_self": float(np.abs(again - win).max()),
                  "lo": lo, "hi": hi,
                  "kurt_winsor": sc.kurtosis(win), "kurt_excess": sc.kurtosis(exc),
                  "match_json": bool(h == H and lo == thr["lo"] and hi == thr["hi"])}
    return out


def gate_input(g: Gate, base: pd.DataFrame, samples: dict, invs: dict,
               thr: dict, winsor: dict) -> None:
    g.section("0. 样本与输入（headline × ok_{h}h；四格 R1–R4）")
    head = base["in_universe"].to_numpy(dtype=bool)
    reg = base["regime"].to_numpy()
    g.near("事件表行数", len(base), 923235, tol=0, fmt="%.0f")
    g.near("headline(in_universe) 行数", int(head.sum()), 256079, tol=0, fmt="%.0f")
    cell_n = {c: int((reg[head] == c).sum()) for c in CELLS}
    g.check("headline 四格 n 之和 = headline 行数",
            sum(cell_n.values()) == int(head.sum()),
            f"{cell_n} = {sum(cell_n.values()):,}")
    exp_all = {"R1": 74959, "R2": 50564, "R3": 44623, "R4": 85933}
    for c in CELLS:
        g.near(f"headline 格 {c} 全量 n", cell_n[c], exp_all[c], tol=0, fmt="%.0f")
    g.near("headline 合约数（实验 14 的上界要用）",
           int(base.loc[head, "symbol"].nunique()), 249, tol=0, fmt="%.0f")
    g.near("全样本合约数（285 个，本文件不用，只作对照）",
           int(base["symbol"].nunique()), 285, tol=0, fmt="%.0f")
    g.check("regime 只有 R1–R4 四个取值",
            set(np.unique(reg[head]).tolist()) == set(CELLS),
            f"{sorted(set(np.unique(reg[head]).tolist()))}")
    st = base["mkt_vol_state"].to_numpy()[head]
    g.check("mkt_vol_state 原始只有 low/mid/high/unknown 四类（unknown 随后整行排除）",
            set(np.unique(st).tolist()) == set(STATES) | {"unknown"},
            f"{sorted(set(np.unique(st).tolist()))}；"
            + " / ".join(f"{s} {int((st == s).sum()):,}" for s in STATES)
            + f" / unknown {int((st == 'unknown').sum()):,}（排除）")
    g.check("排除 unknown 后状态集合 = {low, mid, high}（只允许这三档入表）",
            all(set(np.unique(samples[h]["state"].to_numpy()).tolist()) - {"unknown"}
                == set(STATES) for h in HS),
            "；".join(f"h={h} 剩下 "
                     f"{sorted(set(np.unique(samples[h]['state'].to_numpy()).tolist()) - {'unknown'})}"
                     for h in HS))
    dup = int(base.loc[head].duplicated(subset=["hour", "symbol"]).sum())
    g.check("(hour, symbol) 无重复（一个合约一小时一行）", dup == 0, f"重复 {dup} 行")

    exp_ok = {1: 256076, 4: 256063, 8: 256028, 24: 255807}
    exp_bad = {1: 3, 4: 16, 8: 51, 24: 272}
    for h in HS:
        g.near(f"h={h} 有效事件数（headline ∩ ok_{h}h）", len(samples[h]), exp_ok[h],
               tol=0, fmt="%.0f")
        g.near(f"h={h} n_invalid（被 ok_{h}h 丢掉）", len(invs[h]), exp_bad[h],
               tol=0, fmt="%.0f")
        g.check(f"h={h} 有效 + 无效 = headline 行数",
                len(samples[h]) + len(invs[h]) == int(head.sum()),
                f"{len(samples[h]):,} + {len(invs[h])} = {len(samples[h]) + len(invs[h]):,}")
    exp_cell24 = {"R1": 74875, "R2": 50519, "R3": 44585, "R4": 85828}
    got24 = samples[24]["regime"].value_counts()
    for c in CELLS:
        g.near(f"h=24 格 {c} n（= confirmatory.py 的锚点）", int(got24.get(c, 0)),
               exp_cell24[c], tol=0, fmt="%.0f")

    g.check("单位闸门：|mean(winsor_fwd_{h}h)| < 0.05（小数口径，D14.2）",
            all(abs(float(samples[h]["winsor"].mean())) < 0.05 for h in HS),
            "；".join(f"h={h} {float(samples[h]['winsor'].mean()):+.6f}" for h in HS)
            + "（若误写成百分数会 > 0.05）")
    g.check("d 只取 ±1，且逐行 == sign(price_change)（方向口径的唯一来源）",
            bool(np.array_equal(np.unique(np.concatenate(
                [samples[h]["d"].to_numpy() for h in HS])), np.array([-1.0, 1.0])))
            and all(bool(np.array_equal(samples[h]["d"].to_numpy(),
                                        np.sign(samples[h]["price_change"].to_numpy())))
                    for h in HS),
            "d ∈ {−1,+1}；4 个 h 上逐行相等")
    g.lines.append("        └ 截尾口径（D14.3）逐 h 复核：把 excess_fwd 按【全池】阈值重压，"
                   "必须逐元素等于表里的 winsor_fwd")
    for h in HS:
        w = winsor[h]
        g.check(f"h={h} winsor_fwd == clip(excess_fwd, 池阈值)（逐元素，0 容差）",
                bool(np.array_equal(w["again"], w["winsor"])),
                f"max|Δ| {w['d_self']:.1e}；阈值 [{w['lo']:+.6f}, {w['hi']:+.6f}]")
    g.check(f"h={H} 的截尾阈值与 winsor_thresholds.json 逐位相等（所有行共用同一组）",
            winsor[H]["match_json"],
            f"json [{thr['lo']:+.16f}, {thr['hi']:+.16f}] vs "
            f"样本 [{winsor[H]['lo']:+.16f}, {winsor[H]['hi']:+.16f}]")
    g.check("★ 截尾真的在做：winsor 的峰度 < 50 且远小于 excess（未截尾）",
            all(winsor[h]["kurt_winsor"] < 50.0
                and winsor[h]["kurt_winsor"] < winsor[h]["kurt_excess"] for h in HS),
            "；".join(f"h={h} {winsor[h]['kurt_winsor']:.1f} vs "
                     f"{winsor[h]['kurt_excess']:.1f}" for h in HS))
    g.note("峰度用 stats_core.kurtosis（辅助函数，不属于 SPEC 第一节的接口）")
    g.check("截尾阈值文件的分位与 EventConfig 一致",
            thr["lower_quantile"] == sc.WINSOR_LOWER
            and thr["upper_quantile"] == sc.WINSOR_UPPER,
            f"json {thr['lower_quantile']:.2f}/{thr['upper_quantile']:.2f} vs "
            f"config {sc.WINSOR_LOWER:.2f}/{sc.WINSOR_UPPER:.2f}")


# ---------------------------------------------- §1 实验 9
FOUR_CELL_COLS = ("n", "share_of_sample", "mean_winsor", "median_winsor", "mean_raw",
                  "median_raw", "mean_excess", "median_excess", "hit_raw",
                  "mean_rv", "median_rv", "share_winsorized")


def gate_exp9(g: Gate, core: pd.DataFrame) -> None:
    g.section("1. 实验 9 · 每格基本面（扩充已有的 descriptive_four_cell）")
    tot_bad = 0
    for h in HS:
        sub = core.loc[core["h"] == h]
        n_sum = int(sub["n"].sum())
        inv_sum = int(sub["n_invalid"].sum())
        g.check(f"★ h={h} 四格 n 之和 = 该 h 的有效事件数",
                n_sum == SUB_N[h], f"{n_sum:,} / {SUB_N[h]:,}")
        g.check(f"h={h} 四格 n_invalid 之和 = headline − 有效数",
                inv_sum == 256079 - SUB_N[h], f"{inv_sum} / {256079 - SUB_N[h]}")
        g.check(f"h={h} 四格 share_of_sample 之和 = 1（1e-12）",
                abs(float(sub["share_of_sample"].sum()) - 1.0) <= 1e-12,
                f"{float(sub['share_of_sample'].sum()):.16f}")
        tot_bad += abs(n_sum - SUB_N[h])
    g.check("每个 h 的四格 n 之和都等于该 h 的有效事件数（4 个 h 汇总）", tot_bad == 0,
            f"全部偏差之和 {tot_bad}")

    four = pd.read_parquet(FOUR_CELL_PATH).set_index("cell")
    mine = core.loc[core["h"] == H].set_index("cell")
    worst, worst_col = 0.0, ""
    for c in FOUR_CELL_COLS:
        dev = float(np.abs(mine[c].loc[list(CELLS)].to_numpy()
                           - four[c].loc[list(CELLS)].to_numpy(dtype="float64")).max())
        if dev > worst:
            worst, worst_col = dev, c
    g.check("★ 扩充后 h=24 那 4 行与已有 descriptive_four_cell.parquet 逐项不变",
            worst <= 1e-12,
            f"{len(FOUR_CELL_COLS)} 列 × 4 格，max|Δ| {worst:.1e}（{worst_col}）")
    g.check("被截尾比例 ∈ (0, 0.1)（h=24 事件行名义 2%，实测 2.76%–3.21%，D16/D14.3）",
            bool(((core["share_winsorized"] > 0.0)
                  & (core["share_winsorized"] < 0.1)).all()),
            "；".join(f"h={h} " + "/".join(f"{x:.4f}" for x in
                                          core.loc[core["h"] == h, "share_winsorized"])
                     for h in HS))
    g.near("h=24 R1 被截尾比例（D16 逐格锚点 3.21%）",
           float(core.loc[(core["h"] == H) & (core["cell"] == "R1"),
                          "share_winsorized"].iloc[0]),
           0.032120, tol=1e-6, fmt="%.6f")
    g.check("均值与中位数都不为 0（表里不是空列）",
            bool(core[["mean_winsor", "median_winsor"]].abs().min().min() > 0.0),
            f"最小绝对值 "
            f"{float(core[['mean_winsor', 'median_winsor']].abs().min().min()):.2e}")
    g.lines.append("        每格基本面（n / 均值 / 中位数 / 命中率 raw / 平均 rv / "
                   "被截尾比例；小数口径）")
    for h in HS:
        for cell in CELLS:
            r = core.loc[(core["h"] == h) & (core["cell"] == cell)].iloc[0]
            g.lines.append(
                f"          h={h:<2d} {cell}  n {int(r['n']):,}  {r['mean_winsor']:+.6f}  "
                f"{r['median_winsor']:+.6f}  {r['hit_raw']:.4f}  "
                f"{r['mean_rv']:.4f}  {r['share_winsorized']:.4f}")


# ---------------------------------------------- §2 实验 10
def gate_exp10(g: Gate, core: pd.DataFrame, samples: dict, ident: dict) -> None:
    g.section("2. 实验 10 · 续势 / 反转 / 无效应比例（p_cont / p_rev / p_flat）")
    dev_sum = float(np.abs(core["p_cont"] + core["p_rev"] + core["p_flat"] - 1.0).max())
    g.check("★ p_cont + p_rev + p_flat = 1（16 格，1e-9）", dev_sum <= 1e-9,
            f"max|Σ − 1| = {dev_sum:.1e}")
    dev_hit = float(np.abs(core["p_cont"] - core["hit_raw"]).max())
    g.check("★ p_cont == hit_rate（16 格，1e-12）—— 恒等式，不是独立证据",
            dev_hit <= 1e-12,
            f"max|p_cont − hit_raw| = {dev_hit:.3e}"
            f"（{ident['n_exact']}/{ident['n_cells']} 格逐位相等）")
    dev_reb = ident["max_abs_rebuilt"]
    g.check("★ 恒等式由原始 fwd 列**重算**得出来（不是复制同一列）", dev_reb <= 1e-12,
            f"重建 1{{sign(fwd)=sign(pc)}} 与 1{{fwd=0}} vs 表里的 p_cont/p_flat，"
            f"max|Δ| = {dev_reb:.3e}")
    g.check("★ 机制：样本里 cont_{h}h 与 hit_{h}h 两列逐元素相等（4 个 h 全部）",
            all(bool(np.array_equal(samples[h]["cont"].to_numpy(),
                                    samples[h]["hit"].to_numpy())) for h in HS),
            "；".join(f"h={h} "
                     f"{bool(np.array_equal(samples[h]['cont'].to_numpy(), samples[h]['hit'].to_numpy()))}"
                     for h in HS))
    g.check("三个比例都在 [0,1] 且每 h 四格合计 = 4（互斥穷尽）",
            bool((core[["p_cont", "p_rev", "p_flat"]] >= 0.0).all().all())
            and bool((core[["p_cont", "p_rev", "p_flat"]] <= 1.0).all().all())
            and all(abs(float(core.loc[core["h"] == h, ["p_cont", "p_rev", "p_flat"]]
                              .to_numpy().sum()) - 4.0) <= 1e-9 for h in HS),
            "每 h：p_cont + p_rev + p_flat 的 4 格合计 = 4")
    g.check("p_rev > 0 且 p_flat > 0（不是退化表：确实有反转与无效应两类）",
            bool((core["p_rev"] > 0.0).all() and (core["p_flat"] > 0.0).all()),
            f"p_rev ∈ [{core['p_rev'].min():.4f}, {core['p_rev'].max():.4f}]，"
            f"p_flat ∈ [{core['p_flat'].min():.4f}, {core['p_flat'].max():.4f}]")
    note = str(core["note"].iloc[0])
    g.check("★ 表注在表里：note 列写明 p_cont ≡ hit_rate 且不是独立证据",
            "p_cont ≡ hit_rate" in note and "恒等式" in note and "不是独立证据" in note,
            "note 列逐行携带；删掉这句会立刻 FAIL")
    g.check("表注同时声明了单位与'不放 p 值 / 不放 t / 不做等价性结论'",
            all(t in note for t in ("小数", "不放 p 值", "D15.2")),
            "note 列包含：小数 / 不放 p 值 / D15.2")
    g.lines.append("        续势 / 反转 / 无效应（p_cont 与 hit_raw 逐格相同是恒等式；"
                   "三者相加 = 1）")
    for h in HS:
        for cell in CELLS:
            r = core.loc[(core["h"] == h) & (core["cell"] == cell)].iloc[0]
            g.lines.append(
                f"          h={h:<2d} {cell}  cont {r['p_cont']:.4f}  rev {r['p_rev']:.4f}  "
                f"flat {r['p_flat']:.4f}  "
                f"Σ {r['p_cont'] + r['p_rev'] + r['p_flat']:.10f}")


# ---------------------------------------------- §3 实验 11
def gate_exp11(g: Gate, path: pd.DataFrame, samples: dict) -> None:
    g.section("3. 实验 11 · 路径风险（mfe / mae / mdd 的均值与 p10/p50/p90）")
    g.check("★ mdd ≤ 0 恒成立（原始列，4 个 h 全部，0 容差）",
            all(bool(np.all(samples[h]["mdd"].to_numpy() <= 0.0)) for h in HS),
            "；".join(f"h={h} max {float(samples[h]['mdd'].max()):.3e}" for h in HS))
    cols = ["mdd_mean", "mdd_p10", "mdd_p50", "mdd_p90"]
    g.check("★ 表里的 mdd 也全 ≤ 0（均值与三个分位，4×4 行）",
            bool((path[cols] <= 0.0).all().all()),
            f"max = {float(path[cols].to_numpy().max()):.3e}")
    g.check("分位数单调：p10 ≤ p50 ≤ p90（三个指标 × 16 行）",
            all(bool((path[f"{m}_p10"] <= path[f"{m}_p50"]).all())
                and bool((path[f"{m}_p50"] <= path[f"{m}_p90"]).all())
                for m in ("mfe", "mae", "mdd")))
    inside = True
    for h in HS:
        s = samples[h]
        reg = s["regime"].to_numpy()
        for cell in CELLS:
            m = reg == cell
            row = path.loc[(path["h"] == h) & (path["cell"] == cell)].iloc[0]
            for metric in ("mfe", "mae", "mdd"):
                v = s[metric].to_numpy()[m]
                inside = bool(inside and (float(v.min()) <= row[f"{metric}_mean"]
                                          <= float(v.max())))
    g.check("均值落在该格的原始极值区间内（均值没算错）", inside,
            "min ≤ mean ≤ max，三个指标 × 16 行")
    g.check("未见符号截断：mfe<0 与 mae>0 的例外仍存在（D7 明令不截断、不加 flag）",
            bool((path["share_mfe_negative"] > 0.0).any())
            and bool((path["share_mae_positive"] > 0.0).any()),
            "；".join(
                f"h={h} mfe<0 {float(path.loc[path['h'] == h, 'share_mfe_negative'].mean()):.4f}"
                f" / mae>0 {float(path.loc[path['h'] == h, 'share_mae_positive'].mean()):.4f}"
                for h in HS))
    g.check("n 与实验 9 的 n 逐行一致（同一批行，4 格 × 4 h）",
            bool((path["n"].to_numpy() == CORE_N).all()),
            f"16 格 max|Δ| = {int(np.abs(path['n'].to_numpy() - CORE_N).max())}")
    g.note("mfe/mae/mdd 未截尾，均值受极少数极端路径主导（h=1 的 mdd 最小 "
           f"{min(float(samples[h]['mdd'].min()) for h in HS):+.3f}）；"
           "p50 与 p10/p90 才是典型口径")
    g.lines.append("        路径风险一览（均值 / p10 / p50 / p90，小数口径）")
    for h in HS:
        for cell in CELLS:
            row = path.loc[(path["h"] == h) & (path["cell"] == cell)].iloc[0]
            g.lines.append(
                f"          h={h:<2d} {cell}  "
                + "   ".join(f"{m} {row[f'{m}_mean']:+.4f} / {row[f'{m}_p10']:+.4f} / "
                             f"{row[f'{m}_p50']:+.4f} / {row[f'{m}_p90']:+.4f}"
                             for m in ("mfe", "mae", "mdd")))


# ---------------------------------------------- §4 实验 14
def _weighted_mean(df: pd.DataFrame, value: str, by: list[str]) -> pd.Series:
    """按 n 加权的分组均值（用来验"分组表加总 = 总表"）。"""
    t = df.assign(_w=df[value].to_numpy(dtype="float64") * df["n"].to_numpy(dtype="float64"))
    g = t.groupby(by, observed=True)[["_w", "n"]].sum()
    return g["_w"] / g["n"]


def _agg_deviation(df: pd.DataFrame, ref: pd.Series) -> float:
    """分组表按 n 加权后的均值 与对照均值之差（16 组取 max|Δ|）。"""
    w = _weighted_mean(df, "mean_winsor", ["cell", "h"])
    return float((w - ref.reindex(w.index)).abs().max())


def _kept_mean(samples: dict[int, pd.DataFrame]) -> pd.Series:
    """排除 unknown 行之后，每（格 × h）的 winsor 均值 —— by_state 的对照就是它。

    by_state 少了第四档，加权和不可能再等于 core（core 含 unknown）；所以对照必须
    同样去掉 unknown 行，否则这条 1e-12 的一致性闸门会因为"少一档"而必然失败。
    """
    rows = []
    for h in HS:
        s = samples[h]
        keep = s["state"].to_numpy() != "unknown"
        reg = s["regime"].to_numpy()[keep]
        win = s["winsor"].to_numpy()[keep]
        for cell in CELLS:
            rows.append({"cell": cell, "h": h,
                         "mean_winsor": float(win[reg == cell].mean())})
    return pd.DataFrame(rows).set_index(["cell", "h"])["mean_winsor"]


def gate_exp14(g: Gate, by_sym: pd.DataFrame, by_state: pd.DataFrame,
               core: pd.DataFrame, samples: dict[int, pd.DataFrame]) -> None:
    g.section("4. 实验 14 · 分合约、分市场状态（**不做任何显著性检验**）")
    n_sym = int(by_sym["symbol"].nunique())
    cap = n_sym * len(CELLS) * len(HS)
    g.check("★ by_symbol 行数 ≤ 合约数 × 4 格 × 4 h", len(by_sym) <= cap,
            f"{len(by_sym):,} ≤ {n_sym} × 4 × 4 = {cap:,}"
            f"（差 {cap - len(by_sym)} 行 = 每个 h 各缺 1 个 (合约, 格) 组合）")
    g.near("by_symbol 的合约数", n_sym, 249, tol=0, fmt="%.0f")
    for h in HS:
        sub = by_sym.loc[by_sym["h"] == h]
        present = set(zip(sub["symbol"], sub["cell"]))
        miss = sorted({(s, c) for s in by_sym["symbol"].unique() for c in CELLS} - present)
        g.check(f"h={h} by_symbol 恰好缺 1 个 (合约, 格) 组合（249×4 − 995）",
                len(miss) == 1, f"缺 {miss}")
    g.check("★ by_symbol 每 h 的 n 之和 = 该 h 的有效事件数（没丢行）",
            all(int(by_sym.loc[by_sym["h"] == h, "n"].sum()) == SUB_N[h] for h in HS),
            "；".join(f"h={h} {int(by_sym.loc[by_sym['h'] == h, 'n'].sum()):,}/"
                     f"{SUB_N[h]:,}" for h in HS))
    g.check("by_symbol 无重复 (symbol, cell, h)",
            int(by_sym.duplicated(subset=["symbol", "cell", "h"]).sum()) == 0,
            f"{len(by_sym):,} 行")
    ref = core.set_index(["cell", "h"])["mean_winsor"]
    dev_sym = _agg_deviation(by_sym, ref)
    g.check("★ by_symbol 按 n 加权的均值 = core 的均值（16 组，1e-12）", dev_sym <= 1e-12,
            f"max|Δ| {dev_sym:.1e}")

    g.check("★ by_state 行数 = 3 状态 × 4 格 × 4 h = 48（unknown 整行排除后）",
            len(by_state) == 48, f"{len(by_state)} 行（排除前 64 行）")
    g.check("by_state 状态集合 = {low, mid, high}（unknown 被样本过滤掉，不单列也不并入任何一档）",
            sorted(by_state["state"].unique().tolist()) == sorted(STATES),
            f"{sorted(by_state['state'].unique().tolist())}")
    gone = {h: int((samples[h]["state"].to_numpy() == "unknown").sum()) for h in HS}
    g.check("★ 被排除的 unknown 行数逐 h 打出（每 h 3,604，四个 h 合计 14,416）—— 有意排除，不是静默丢掉",
            list(gone.values()) == [3604] * len(HS) and sum(gone.values()) == 14416,
            "；".join(f"h={h} 排除 {gone[h]:,} 行" for h in HS)
            + f"；合计 {sum(gone.values()):,} 行")
    g.check("★ by_state 每 h 的 n 之和 + 被排除的 unknown = 该 h 的有效事件数（排除之外一行没丢）",
            all(int(by_state.loc[by_state["h"] == h, "n"].sum()) + gone[h] == SUB_N[h]
                for h in HS),
            "；".join(f"h={h} {int(by_state.loc[by_state['h'] == h, 'n'].sum()):,} "
                     f"+ {gone[h]:,} = "
                     f"{int(by_state.loc[by_state['h'] == h, 'n'].sum()) + gone[h]:,}"
                     f" / {SUB_N[h]:,}" for h in HS))
    g.check("by_state 无重复 (state, cell, h)",
            int(by_state.duplicated(subset=["state", "cell", "h"]).sum()) == 0,
            f"{len(by_state)} 行")
    dev_state = _agg_deviation(by_state, _kept_mean(samples))
    g.check("★ by_state（low/mid/high）按 n 加权的均值 = 排除 unknown 后的 core 均值（16 组，1e-12）",
            dev_state <= 1e-12, f"max|Δ| {dev_state:.1e}")
    total_bad = 3 + 16 + 51 + 272
    g.check("两张分组表都带 n_invalid 列（D9），非负整数，且合计 = 各 h 无效行之和 342",
            by_sym["n_invalid"].dtype.kind in "iu"
            and by_state["n_invalid"].dtype.kind in "iu"
            and int(by_sym["n_invalid"].sum()) == total_bad
            and int(by_state["n_invalid"].sum()) == total_bad,
            f"by_symbol {int(by_sym['n_invalid'].sum())} / "
            f"by_state {int(by_state['n_invalid'].sum())} / 应为 {total_bad}")
    g.check("两张分组表的 n_invalid 每一行都 ≤ 该行 n（一个无效行不能多于该格行数）",
            bool((by_sym["n_invalid"] <= by_sym["n"]).all())
            and bool((by_state["n_invalid"] <= by_state["n"]).all()))
    g.lines.append(f"        分市场状态摘要（h={H}；n / 均值 / 中位数 / 命中率 raw；不做检验）")
    for st in STATES:
        for cell in CELLS:
            r = by_state.loc[(by_state["h"] == H) & (by_state["state"] == st)
                             & (by_state["cell"] == cell)].iloc[0]
            g.lines.append(
                f"          h={H:<2d} {st:<7s} {cell}  n {int(r['n']):,}  "
                f"{r['mean_winsor']:+.6f}  {r['median_winsor']:+.6f}  {r['hit_raw']:.4f}")


# ---------------------------------------------- §5 表结构（不放 p 值）
POLLUTED = {"p_value": ["p_value"], "pval": ["pval"], "t_stat": ["t_stat"],
            "se": ["se"], "ci_lo": ["ci_lo"], "wald_p": ["wald_p"], "p_bh": ["p_bh"],
            "estimate+se+t+p": ["estimate", "se", "t", "p"]}


def gate_tables(g: Gate, tables: dict[str, pd.DataFrame]) -> None:
    g.section("5. 表结构 · 不含任何 p 值列（列名断言，且该断言能失败）")
    for name, df in tables.items():
        bad = inference_columns(df)
        g.check(f"★ {name} 不含任何 p 值 / t / SE / 区间列", bad == [],
                f"{df.shape[0]:,} 行 × {df.shape[1]} 列；命中 {bad if bad else '无'}")
    caught = {k: inference_columns(pd.DataFrame({c: [0.0] for c in cols}))
              for k, cols in POLLUTED.items()}
    g.check("★ 该断言能失败：8 种故意污染的列名全部被抓到",
            all(bool(v) for v in caught.values()),
            "；".join(f"{k}→{v}" for k, v in caught.items()))
    clean = pd.DataFrame({"p_cont": [0.5], "p_rev": [0.3], "p_flat": [0.2],
                          "mfe_p10": [0.0], "share_of_sample": [1.0]})
    g.check("白名单不误伤：p_cont / p_rev / p_flat（比例）与 mfe_p10 不被当成 p 值",
            inference_columns(clean) == [], f"命中 {inference_columns(clean)}")
    exp_rows = {"descriptive_core": len(CELLS) * len(HS),
                "descriptive_path": len(CELLS) * len(HS),
                "descriptive_by_symbol": 3980, "descriptive_by_state": 48}
    for name, df in tables.items():
        g.check(f"{name} 行数 = {exp_rows[name]}", len(df) == exp_rows[name],
                f"{len(df)} 行")
        numeric = [c for c in df.columns if df[c].dtype.kind in "fiu"]
        g.check(f"{name} 的数值列全部有限（无 NaN）",
                bool(all(np.isfinite(df[c].to_numpy(dtype="float64")).all()
                         for c in numeric)),
                f"数值列 {len(numeric)} 个")
    g.check("4 张表都没有 experiment / statistic / verdict 列"
            "（描述层不是 confirmatory 那种推断长表）",
            all(not ({"experiment", "statistic", "verdict"} & set(df.columns))
                for df in tables.values()),
            "四张表都缺这三个列名")


# ============================================================ 6. main
def write_table(df: pd.DataFrame, name: str) -> None:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TBL_DIR / f"{name}.parquet", index=False)
    df.to_csv(TBL_DIR / f"{name}.csv", index=False, encoding="utf-8")
    log(f"写盘 {name}.parquet / .csv  （{len(df)} 行 × {df.shape[1]} 列）")


def main() -> int:
    global CORE_N
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    base = load_base()
    thr = json.loads(THR_PATH.read_text(encoding="utf-8"))
    samples, invs = {}, {}
    for h in HS:
        samples[h], invs[h] = build_horizon(base, h)
        SUB_N[h] = len(samples[h])
    winsor = winsor_diagnostics(samples, thr)
    ident = identity_check(samples)
    log(f"恒等式 p_cont ≡ hit_rate：{ident['n_exact']}/{ident['n_cells']} 格逐位相等，"
        f"max|Δ| = {ident['max_abs']:.1e}；重建 max|Δ| = {ident['max_abs_rebuilt']:.1e}")

    core = build_core(samples, invs, ident)
    CORE_N = core["n"].to_numpy()
    path = build_path(samples, invs)
    by_sym = build_grouped(samples, invs, "symbol")
    by_state = build_grouped(samples, invs, "state")
    tables = {"descriptive_core": core, "descriptive_path": path,
              "descriptive_by_symbol": by_sym, "descriptive_by_state": by_state}

    gate = Gate(f"event_study · descriptive（实验 9/10/11/14）· "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
    gate.lines.append(f"样本：headline(in_universe) ∩ ok_{{h}}h，freq={FREQ}，h ∈ {list(HS)}；"
                      "headline 256,079 事件 / 249 合约")
    gate.lines.append("单位：内部与表里一律**小数**（D14.2），×100 即百分数、×1e4 即 bp；"
                      "hit_* / p_* / share_* 是 0–1 比例，rv 是小数波动（非 log），n 是计数")
    gate.lines.append("纪律：只报数、不做判定（GUIDANCE 第二节）。表里不含 p 值、t、SE、区间，"
                      "D15.2 之后也不含等价性结论；§5 的列名断言守这一条，"
                      "并用 8 种污染列名证明它能失败")
    gate_input(gate, base, samples, invs, thr, winsor)
    gate_exp9(gate, core)
    gate_exp10(gate, core, samples, ident)
    gate_exp11(gate, path, samples)
    gate_exp14(gate, by_sym, by_state, core, samples)
    gate_tables(gate, tables)

    if gate.n_fail:
        txt = gate.text("有 FAIL → 按纪律停在这里，不写表（闸门没过时表里的数不可信）")
        CHECKS_PATH.write_text(txt, encoding="utf-8")
        print(txt)
        log(f"闸门写盘 {CHECKS_PATH}（FAIL {gate.n_fail} 项，停止）")
        return 1

    for name, df in tables.items():
        write_table(df, name)

    footer = (
        "口径出处：D13（市场中性 + 全池 1%/99% 截尾）/ D14.2（小数）/ D14.3（阈值取全市场 "
        "pool，禁止格内截尾）/ D15.2（普通显著性；描述层不放等价性结论）/ D16（h=24 被截尾"
        "比例锚点）/ D7（mfe/mae 符号例外不截断、不加 flag）/ D9（每张表带 n_invalid）。\n"
        "与已有产物的关系：descriptive_core 是 descriptive_four_cell 的扩充（4 个 h 而不是只有"
        " 24h），h=24 那 4 行与它的 12 个共同列逐项相同（已有表的 hit_neutral 中性口径已删，"
        "本表只剩 hit_raw）；descriptive_path / by_symbol / by_state 是新增的。\n"
        "读表须知：1) p_cont ≡ hit_rate 是恒等式，§2 已用原始 fwd 列重算证明，把它当独立"
        "证据就是重复计数；2) 路径三列未截尾，均值会被极少数极端路径主导，p50 与 p10/p90 "
        "才是典型口径；3) by_symbol 每 h 缺 1 个 (合约, 格) 组合（BSBUSDT × R3：该合约"
        "从未出现'价格跌 + OI 增'），所以是 3,980 = 249×4×4 − 4 行；4) by_state 只有 "
        "low/mid/high 三档（48 = 3×4×4 行）：unknown 不是一种市场状态（只覆盖 2021-12…2022-03，"
        "波动率分位还没攒够一年），每 h 3,604 行、四个 h 合计 14,416 行被整行排除，"
        "行数由 §4 逐 h 打出。")
    txt = gate.text(footer)
    CHECKS_PATH.write_text(txt, encoding="utf-8")
    print(txt)
    log(f"闸门写盘 {CHECKS_PATH}")
    return 0 if gate.n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
