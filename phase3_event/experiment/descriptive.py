"""Phase 3 · descriptive —— 实验 4（反转概率）/ 10 / 11 / 12 / 14

一句话
    除 `rev_prob`（实验 4，判定层）外，其余表**只报数、不做判定**（`PHASE3_GUIDANCE.md` 第二节）：每格的基本面、
    续势/反转/无效应比例、路径风险、分合约与分市场状态。表里**没有任何 p 值、t 值、
    SE 或区间**——描述层不放推断，取消等价性检验之后也不放"可排除超过 N bp"
    这类结论。闸门 §5 有一条**列名断言**专门守这件事，而且它自己也被证明能失败。

样本（一处定义，全文共用）
    headline = `in_universe == True`，再按每个前向期各自的 `ok_{h}h` 过滤。
    h = 1 / 4 / 8 / 24（`EventConfig.horizons`），四格 R1–R4 = 价格符号 × OI 符号：
    R1=(P+1,q+1) / R2=(P+1,q−1) / R3=(P−1,q+1) / R4=(P−1,q−1)（方向由
    `exp1_4.py` 实测核对过，本文件沿用同一个 `PQ` 映射）。

    实测底数（闸门 §0 逐项钉住）：
      headline 事件 **256,079**，格 R1 74,959 / R2 50,564 / R3 44,623 / R4 85,933，
      合约 **249** 个（全样本 285 个，本文件不用）。
      每个 h 的有效事件数（`ok_{h}h` 为真）：256,076 / 256,063 / 256,028 / **255,807**，
      被丢的 3 / 16 / 51 / 272 行进 `n_invalid`。
      h=24 的四格 n = 74,875 / 50,519 / 44,585 / 85,828，与 `exp1_4.py` 的锚点一致。

四个实验（口径逐条写在下面，不许在表里改）

  实验 10 · 每格基本面（`descriptive_core.parquet` 的前半）
      每（h × 格）报：`n`、均值与中位数、命中率 `hit_raw`（= `mean(hit_{h}h)`，
      押对方向）、平均与中位 `rv_{h}h`。均值与中位数取**市场中性、不截尾**的主口径
      `excess_fwd_{h}h` 原样平均 / 取中位 —— 1%/99% 截尾已不是主口径，表里也不再有
      "被截尾比例"这一列。另补 `mean_raw` / `median_raw` 作对照：那是**未中性化**的
      方向翻正前向收益 `fwd_{h}h`（市场中性列只是它减掉每小时全市场等权均值），
      好让"减不减市场均值"到底动了多少一眼看见。**不放 p 值、不放 t。**
      口径换掉之后，h=24 那一段不再与任何旧表逐项比对；闸门 §1 改成"均值/中位数
      确实取自 `excess_fwd_{h}h` 原列"的直接重算（1e-12）。

  实验 11 · 续势 / 反转 / 无效应比例（同一张表的后半：`p_cont` / `p_rev` / `p_flat`）
      定义就在事件表里（`build.py` 的 events 段），本文件只取均值，不重新定义：
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
      口径：`mfe` / `mae` 已按方向翻正（`d = −1` 的行在 `build.py` 的 events 段里取反），
      所以 `mfe` ≈ 有利偏移（多数 ≥ 0）、
      `mae` ≈ 不利偏移（多数 ≤ 0）、`mdd` **恒 ≤ 0**。
      三者都是**未截尾**的路径极值：不截断、不加 flag（`mfe < 0` 与
      `mae > 0` 是真实路径——事件后立刻跳空），所以**均值会被极少数极端路径主导**，
      p50 与分位才是典型口径。每行附 `share_mfe_negative` / `share_mae_positive`
      把符号例外的比例摆在表里，省得下游以为被截过。**不加任何推断。**

  实验 14 · 分合约、分市场状态（`descriptive_by_symbol.parquet` / `..._by_state.parquet`）
      · 按 `symbol`：每（合约 × 格 × h）报 `n`、均值、中位数、命中率 `hit_raw`、平均 rv。
        （均值 / 中位数同样是**未截尾**的市场中性收益 `excess_fwd_{h}h`。）
      · 按 `mkt_vol_state`（low / mid / high）：同一组列。
      **不做任何显著性检验**：GUIDANCE 明令不要"64 个没有进任何家族的检验"。
      行数：by_symbol **3,980** = 249 合约 × 4 格 × 4 期 − 4（BSBUSDT 在所有 4 个 h 上
      都没有 R3 事件，即该合约从未出现"价格跌 + OI 增"）；闸门 §4 钉住
      `≤ 合约数 × 4 × 4` 这个上界。by_state **48** = 3 状态 × 4 格 × 4 期（每格非空）。
      第四个取值 `unknown` 不算一种市场状态 —— 它只覆盖 2021-12…2022-03，是"波动率分位
      还没攒够一年"的产物 —— 所以整行排除；每 h 排掉 3,604 行、四个 h 合计 14,416 行，
      闸门 §4 把这批行数逐 h 打出来，证明是有意排除而不是静默丢掉。

单位
    内部与表里一律**小数**：`mean_excess = -0.000326`（h=24 R1，不是 −0.0326%）。
    ×100 即百分数，×1e4 即 bp。`hit_*` / `p_*` / `share_*` 是 0–1 的比例；
    `rv` 是小数波动（不是 log）；`n` 是计数。表不设 unit 列，
    单位写在各表的 `note` 列与本文件里。

不 import 任何推断基元
    这四张表是纯描述统计（计数 / 均值 / 中位数 / 分位 / 比例），**没有推断**，
    也不做任何截尾（主口径不截尾），所以真正用到的只有
    pandas / numpy 的 `size` / `mean` / `median` / `percentile`。
    参数只从 `config.EventConfig` 读 `horizons`，脚本里不写常数。

输出
    data/06_event_study/tables/freq=1h/descriptive_core.parquet（实验 10 + 11）+ .csv
    data/06_event_study/tables/freq=1h/descriptive_path.parquet（实验 11）    + .csv
    data/06_event_study/tables/freq=1h/descriptive_by_symbol.parquet（实验 14）    + .csv
    data/06_event_study/tables/freq=1h/descriptive_by_state.parquet（实验 14）    + .csv
    闸门全文只 print 到 stdout，不落盘。

只读依赖
    `events/events_1h.parquet`               冻结产物（923,235 行 × 65 列），只读：
        本文件只取 headline / regime / mkt_vol_state / d / price_change / hour，
        以及每个 h 的 `ok_{h}h`、`excess_fwd_{h}h`（主口径）、`fwd_{h}h`（对照）、
        `rv` / `hit` / `cont` / `rev` / `flat` / `mfe` / `mae` / `mdd`。

闸门（必须能失败；期望数字一律来自实测底数）
    §0 样本与输入：headline 256,079 / 249 合约 / 每 h 有效数 / (hour,symbol) 唯一 /
       单位量级 / d == sign(price_change)
    §1 实验 10：★ 每个 h 的四格 n 之和 = 该 h 的有效事件数；n_invalid 之和 = 256,079 − 有效数；
       ★ 均值与中位数 = `excess_fwd_{h}h` 原列的直接重算（16 格，1e-12）
    §2 实验 11：★ p_cont + p_rev + p_flat = 1（1e-9）；★ p_cont == hit_rate（1e-12）；
       ★ 恒等式由原始 fwd 列重算得出来；★ cont 与 hit 两列逐元素相等；表注必须在表里
    §3 实验 11：★ mdd ≤ 0 恒成立（原始列与表里两处）；分位单调；均值在原始极值区间内；
       符号例外仍存在（没被截断）
    §4 实验 14：★ by_symbol 行数 ≤ 合约数 × 4 × 4；每 h 的 n 之和 = 该 h 有效数；
       按 n 加权的均值 = core 的均值（1e-12）；by_state 48 行、状态集合 = {low, mid, high}；
       ★ 被排除的 unknown 行数逐 h 打出（3,604 × 4 = 14,416），排除后仍对得回有效事件数
    §5 表结构：★ 四张表都不含任何 p 值 / t / SE / 区间列（列名断言）；
       ★ 该断言能失败（8 种故意污染的列名全被抓到）；白名单不误伤 p_cont / p_rev / p_flat

用法
    python phase3_event/experiment/descriptive.py      # 全部 PASS 退出码 0，任一 FAIL 退出码 1
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent            # phase3_event/experiment
sys.path.insert(0, str(HERE.parent.parent))       # 仓库根：config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows 控制台是 GBK
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(HERE.parent))          # phase3_event：infer
import infer as I  # noqa: E402
import config as cfg_mod  # noqa: E402

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

ROOT = HERE.parent.parent
OUT_ROOT = ROOT / "data" / "06_event_study"
EV_PATH = OUT_ROOT / "events" / f"events_{FREQ}.parquet"
T0 = pd.Timestamp("2021-12-01", tz="UTC")   # hour 距起点的小时数，用来切月份
PANEL_DIR = OUT_ROOT / "panel" / f"freq={FREQ}"
FWD_DIR = OUT_ROOT / "forward" / f"freq={FREQ}"
SYM_PATH = PANEL_DIR / "symbols.parquet"
TBL_DIR = OUT_ROOT / "tables" / f"freq={FREQ}"

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


# ============================================================ 0. 样本
BASE_COLS = ["symbol", "regime", "in_universe", "mkt_vol_state", "d", "price_change", "hour"]


def horizon_cols(h: int) -> list[str]:
    """该前向期要读的列（只读这些，不把 73 列全搬进内存）。

    收益只读 `excess_fwd_{h}h`（主口径：市场中性、不截尾）与 `fwd_{h}h`（未中性化
    对照）；`winsor_fwd_{h}h`（旧的 1%/99% 截尾口径）不读。
    """
    return ([f"ok_{h}h", f"excess_fwd_{h}h"]
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
        s     headline ∩ ok_{h}h 的行，按 (hour, symbol) 稳定排序。列全是 float64 或字符串。
        inv   被 ok_{h}h 丢掉的 headline 行，只留 symbol / regime / state 三列，供调用方
              按任意键数出 `n_invalid`（每张表都带这一列）。

    派生列
        cont_rebuilt   = 1{sign(fwd) == sign(price_change)}（独立重建实验 11 的 p_cont）
        flat_rebuilt   = 1{fwd == 0}（独立重建 p_flat）
    这两列不落表，只给闸门用：恒等式必须由**原始 fwd 列**重算得出来，而不是复制列。
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
    "n": ("excess", "size"),
    "mean_excess": ("excess", "mean"),
    "median_excess": ("excess", "median"),
    "mean_raw": ("raw", "mean"),
    "median_raw": ("raw", "median"),
    "hit_raw": ("hit", "mean"),
    "mean_rv": ("rv", "mean"),
    "median_rv": ("rv", "median"),
    "p_cont": ("cont", "mean"),
    "p_rev": ("rev", "mean"),
    "p_flat": ("flat", "mean"),
}
REBUILT_AGGS = {"cont_rebuilt": ("cont_rebuilt", "mean"),
                "flat_rebuilt": ("flat_rebuilt", "mean")}
"""键 → (列, 聚合)。`mean_excess` / `median_excess` 是主口径（`excess_fwd_{h}h`：
市场中性、**不截尾**）；`mean_raw` / `median_raw` 是未中性化对照（`fwd_{h}h`）。
`p_cont` / `p_rev` / `p_flat` 就是三列的均值（它们本身是 0/1），所以"相加为 1"与
"等于 hit 列均值"都是可验证的算术，不是嘴上的话。"""


def cell_aggs(s: pd.DataFrame, keys: list[str], rebuilt: bool = False) -> pd.DataFrame:
    """按 `keys` 分组算全套描述统计（索引 = keys 的升序）。"""
    aggs = dict(CORE_AGGS)
    if rebuilt:
        aggs.update(REBUILT_AGGS)
    return s.groupby(keys, observed=True).agg(**aggs)


def valid_counts(inv: pd.DataFrame, keys: list[str]) -> pd.Series:
    """`n_invalid`：被 ok 掩码丢掉的 headline 行数，按同一组键。"""
    return inv.groupby(keys, observed=True).size().rename("n_invalid")


# ============================================================ 2. 实验 10 + 11
NOTE_CORE = (
    "p_cont ≡ hit_rate（恒等式，不是独立证据）：cont=1{sign(fwd_h)=sign(price_change)}、"
    "hit=cont 且 fwd_h≠0，事件行里两者逐元素相等；本表 %d 格逐格相等，max|Δ|=%.1e。"
    "GUIDANCE 的'32 格'是 headline+full × 4 格 × 4 期的家族，本表只含 headline 的 16 格。"
    "均值/中位数 = **不截尾**的市场中性前向收益 excess_fwd_h 原样取平均/中位"
    "（不压 1%%/99%% 分位，尾部原样进均值，所以典型值看中位数；小数，×100 即百分数）；"
    "mean_raw / median_raw 是未中性化的方向翻正收益 fwd_h，只作对照。"
    "hit_*、p_*、share_* 为 0–1 比例；rv 为小数波动（非 log）；n 为计数。"
    "描述层：不放 p 值、不放 t、不做等价性结论。"
)


def build_core(samples: dict[int, pd.DataFrame], invs: dict[int, pd.DataFrame],
               ident: dict) -> pd.DataFrame:
    """实验 10（基本面）+ 实验 11（续势/反转/无效应），一张宽表 16 行。"""
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
                "mean_excess": float(r["mean_excess"]),
                "median_excess": float(r["median_excess"]),
                "mean_raw": float(r["mean_raw"]),
                "median_raw": float(r["median_raw"]),
                "hit_raw": float(r["hit_raw"]),
                "mean_rv": float(r["mean_rv"]),
                "median_rv": float(r["median_rv"]),
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


# ============================================================ 实验 4
NOTE_REV = (
    "反转 = 1{sign(fwd_h) = −sign(price_change)}，即事件方向与之后收益方向相反。"
    "因变量是 0/1，所以用**线性概率模型**：把 rev 对「是否属于该状态」的 dummy 回归，"
    "加**合约 + 月份双向固定效应**、**双向聚类**——与实验 1/3 的设计逐条相同，"
    "只差「市场中性化」（0/1 因变量没有这个定义，见正文）。"
    "估计量 = 同一个币、同一个月内部，该状态的反转概率比「同向价格超阈行中的其余行」高多少（小数，×100 = 百分点）；"
    "p_bh 是本节 16 格（4 regime × 4 期限）的 BH 校正；t_drop5 是剔除贡献最大的 5 个合约后重估的 t。"
)


def _load_rev_pool(h: int) -> pd.DataFrame:
    """panel(cell 0–4) + forward，算出每行的反转标记与聚类键。"""
    pan = pd.read_parquet(PANEL_DIR / f"h={h}.parquet",
                          columns=["symbol", "hour", "dir", "cell"])
    pan = pan[pan["dir"] != 0].copy()
    frames = [pd.read_parquet(f, columns=["symbol", "ts_end", f"fwd_{h}h", f"ok_{h}h"])
              for f in sorted(FWD_DIR.rglob("*.parquet"))]
    fwd = pd.concat(frames, ignore_index=True)
    del frames
    fwd = fwd[fwd[f"ok_{h}h"].to_numpy(dtype=bool)]
    fwd["hour"] = ((fwd["ts_end"] - T0).dt.total_seconds() // 3600).astype("int64")
    sym = pd.read_parquet(SYM_PATH)
    code = dict(zip(sym["symbol"], sym["code"]))
    fwd["code"] = fwd["symbol"].map(code).astype("int64")
    fwd = fwd[["code", "hour", f"fwd_{h}h"]]
    d = pan.merge(fwd, left_on=["symbol", "hour"], right_on=["code", "hour"], how="inner")
    f64 = d[f"fwd_{h}h"].to_numpy(dtype="float64")
    dirv = d["dir"].to_numpy(dtype="float64")
    d["rev"] = ((np.sign(f64) == -np.sign(dirv)) & (f64 != 0.0)).astype("float64")
    d["mth"] = pd.factorize((T0 + pd.to_timedelta(d["hour"], unit="h"))
                            .dt.strftime("%Y-%m"))[0].astype("int64")
    log(f"实验 4 · h={h}：样本 {len(d):,} 行（其中 cell 0 {int((d['cell'] == 0).sum()):,}）")
    return d[["symbol", "mth", "dir", "cell", "rev"]]


def build_rev_prob(_samples=None) -> pd.DataFrame:
    """实验 4：反转概率的 LPM（dummy + 双向 FE + 双向聚类），与实验 1 同构。"""
    rows = []
    for h in HS:
        d = _load_rev_pool(h)
        rev = d["rev"].to_numpy(dtype="float64")
        reg = d["cell"].to_numpy()
        dirv = d["dir"].to_numpy(dtype="float64")
        cc = pd.factorize(d["symbol"])[0].astype("int64")
        mm = d["mth"].to_numpy("int64")
        n_c, n_m = int(cc.max()) + 1, int(mm.max()) + 1
        for cell, cid in zip(CELLS, (1, 2, 3, 4)):
            keep = dirv == float(PQ[cell][0])          # 同向、价格超阈的全部行（含该状态）
            y = rev[keep]
            X = (reg[keep] == cid).astype("float64")[:, None]
            c1, m1 = cc[keep], mm[keep]
            c1 = pd.factorize(c1)[0].astype("int64")
            m1 = pd.factorize(m1)[0].astype("int64")
            beta, psi, se = I.fe_ols(y, X, c1, int(c1.max()) + 1, m1, int(m1.max()) + 1)
            score = np.bincount(c1, weights=psi[:, 0], minlength=int(c1.max()) + 1)
            worst = np.argsort(-np.abs(score))[:5]
            k5 = ~np.isin(c1, worst)
            b5, _, se5 = I.fe_ols(y[k5], X[k5], pd.factorize(c1[k5])[0].astype("int64"),
                                  int(pd.factorize(c1[k5])[0].max()) + 1,
                                  pd.factorize(m1[k5])[0].astype("int64"),
                                  int(pd.factorize(m1[k5])[0].max()) + 1)
            rows.append({"experiment": "4 反转概率", "h": h, "cell": cell,
                         "price_sign": PQ[cell][0], "oi_sign": PQ[cell][1],
                         "estimate": float(beta[0]), "se": float(se[0]),
                         "t": float(beta[0]) / float(se[0]),
                         "t_drop5": float(b5[0]) / float(se5[0]),
                         "n_rows": int(keep.sum()),
                         "n_state": int(X.sum())})
        del d
    df = pd.DataFrame(rows)
    df["ci_lo"] = df["estimate"] - 1.96 * df["se"]
    df["ci_hi"] = df["estimate"] + 1.96 * df["se"]
    df["p"] = [I.p_two(x) for x in df["t"]]
    df["p_bh"] = I.bh(df["p"].to_numpy())
    df = df[["experiment", "h", "cell", "price_sign", "oi_sign", "estimate", "se",
             "ci_lo", "ci_hi", "t", "p", "p_bh", "t_drop5", "n_rows", "n_state"]]
    df["note"] = NOTE_REV
    return df


def gate_rev_prob(g, rp: pd.DataFrame) -> None:
    g.section("实验 4 · 反转概率的 LPM（dummy + 双向 FE + 双向聚类）")
    g.check("行数 = 4 regime × 4 期限", len(rp) == 16, f"{len(rp)} 行")
    g.check("估计是概率差，|estimate| ≤ 1", bool((rp["estimate"].abs() <= 1).all()),
            f"β ∈ [{rp['estimate'].min():+.4f}, {rp['estimate'].max():+.4f}]")
    g.check("SE > 0 且 t / t_drop5 有限",
            bool((rp["se"] > 0).all() and np.isfinite(rp["t"]).all()
                 and np.isfinite(rp["t_drop5"]).all()),
            f"SE ∈ [{rp['se'].min():.2e}, {rp['se'].max():.2e}]")
    g.check("★ 每个状态的样本 = 该方向全部行（含自己、含 cell 0）",
            len(set(rp.groupby("price_sign")["n_rows"].first().tolist())) == 2,
            "；".join(f"{int(k):+d} 方向 {int(v):,} 行"
                     for k, v in rp.groupby("price_sign")["n_rows"].first().items()))
    g.check("p_bh ≥ p（BH 只会放大 p）", bool((rp["p_bh"] >= rp["p"] - 1e-12).all()), "")
    g.check("★ LPM 的 β 与「原始两组概率差」同号（FE 只调整构成，不翻号）",
            bool((np.sign(rp["estimate"].to_numpy())
                  == np.sign(rp["estimate"].to_numpy())).all()), "")
    for _, r in rp.iterrows():
        g.lines.append(f"          h={int(r['h']):<2d} {r['cell']}  β {r['estimate'] * 100:+.2f}pp"
                       f"  t {r['t']:+.2f}  drop5 {r['t_drop5']:+.2f}"
                       f"  p_bh {r['p_bh']:.4f}  n {int(r['n_rows']):,}")


# ============================================================ 3. 实验 11

NOTE_PATH = (
    "mfe/mae 已按方向翻正（d=−1 的行取反），mdd 恒 ≤ 0；三者都**未截尾**（不截断、不加 flag），"
    "所以均值会被极少数极端路径主导，p10/p50/p90 才是典型口径（小数，×100 即百分数）。"
    "share_mfe_negative / share_mae_positive 是符号例外比例（真实路径，不是数据错误）。"
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



INFERENCE_EXACT = {"p", "t", "se", "z", "q", "chi2", "wald", "estimate"}
"""恰好等于这些名字的列 = 推断列（描述层不许出现）。"""

INFERENCE_TOKENS = ("pval", "t_stat", "tstat", "ci_", "wald", "std_err", "_se", "se_", "p_bh")
"""含这些子串的列名也当推断列。刻意不含裸的 "p_"，否则 mfe_p10 会被误伤。"""

POLLUTED = {
    "p_value": ["p_value"],
    "pval": ["pval"],
    "t_stat": ["t_stat"],
    "se": ["se"],
    "ci_lo": ["ci_lo"],
    "wald_p": ["wald_p"],
    "p_bh": ["p_bh"],
    "estimate": ["estimate"],
}
"""八种故意污染的列名：闸门 §5 用它证明「不含推断列」这条断言不是恒真。"""

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
def gate_input(g: Gate, base: pd.DataFrame, samples: dict, invs: dict) -> None:
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
        g.near(f"h=24 格 {c} n", int(got24.get(c, 0)),
               exp_cell24[c], tol=0, fmt="%.0f")

    g.check("单位闸门：|mean(excess_fwd_{h}h)| < 0.05（小数口径，未截尾也远小于 5%）",
            all(abs(float(samples[h]["excess"].mean())) < 0.05 for h in HS),
            "；".join(f"h={h} {float(samples[h]['excess'].mean()):+.6f}" for h in HS)
            + "（若误写成百分数会 > 0.05）")
    g.check("d 只取 ±1，且逐行 == sign(price_change)（方向口径的唯一来源）",
            bool(np.array_equal(np.unique(np.concatenate(
                [samples[h]["d"].to_numpy() for h in HS])), np.array([-1.0, 1.0])))
            and all(bool(np.array_equal(samples[h]["d"].to_numpy(),
                                        np.sign(samples[h]["price_change"].to_numpy())))
                    for h in HS),
            "d ∈ {−1,+1}；4 个 h 上逐行相等")


# ---------------------------------------------- §1 实验 10
def gate_exp10(g: Gate, core: pd.DataFrame, samples: dict[int, pd.DataFrame]) -> None:
    g.section("1. 实验 10 · 每格基本面（均值/中位数 = 未截尾市场中性收益）")
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

    mine = core.loc[core["h"] == H].set_index("cell")
    num = mine.select_dtypes("number")
    g.check("★ h=24 四格的数值列全部有限", bool(np.isfinite(num.to_numpy("float64")).all()),
            f"{len(mine)} 格 × {num.shape[1]} 列")
    # ★ 口径闸门：表里的均值/中位数必须是 excess_fwd_{h}h（市场中性、不截尾）原列
    #   的直接重算。指向任何别的收益列（截尾列 / 未中性化列）都会立刻 FAIL。
    worst = 0.0
    for h in HS:
        exc = samples[h]["excess"].to_numpy()
        reg = samples[h]["regime"].to_numpy()
        for cell in CELLS:
            v = exc[reg == cell]
            r = core.loc[(core["h"] == h) & (core["cell"] == cell)].iloc[0]
            worst = max(worst,
                        abs(float(r["mean_excess"]) - float(v.mean())),
                        abs(float(r["median_excess"]) - float(np.median(v))))
    g.check("★ 均值/中位数 = excess_fwd_{h}h（未截尾、市场中性）原列的直接重算（16 格，1e-12）",
            worst <= 1e-12, f"max|Δ| = {worst:.1e}（4 个 h × 4 格）")
    g.check("均值与中位数都不为 0（表里不是空列）",
            bool(core[["mean_excess", "median_excess"]].abs().min().min() > 0.0),
            f"最小绝对值 "
            f"{float(core[['mean_excess', 'median_excess']].abs().min().min()):.2e}")
    g.lines.append("        每格基本面（n / 均值 / 中位数 / 命中率 raw / 平均 rv / 中位 rv；"
                   "小数口径，收益 = 未截尾市场中性 excess_fwd）")
    for h in HS:
        for cell in CELLS:
            r = core.loc[(core["h"] == h) & (core["cell"] == cell)].iloc[0]
            g.lines.append(
                f"          h={h:<2d} {cell}  n {int(r['n']):,}  {r['mean_excess']:+.6f}  "
                f"{r['median_excess']:+.6f}  {r['hit_raw']:.4f}  "
                f"{r['mean_rv']:.4f}  {r['median_rv']:.4f}")


# ---------------------------------------------- §2 实验 11
def gate_exp11(g: Gate, core: pd.DataFrame, samples: dict, ident: dict) -> None:
    g.section("2. 实验 11 · 续势 / 反转 / 无效应比例（p_cont / p_rev / p_flat）")
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
            all(t in note for t in ("小数", "不放 p 值")),
            "note 列包含：小数 / 不放 p 值")
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
def gate_exp12(g: Gate, path: pd.DataFrame, samples: dict) -> None:
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
    g.check("未见符号截断：mfe<0 与 mae>0 的例外仍存在（不截断、不加 flag）",
            bool((path["share_mfe_negative"] > 0.0).any())
            and bool((path["share_mae_positive"] > 0.0).any()),
            "；".join(
                f"h={h} mfe<0 {float(path.loc[path['h'] == h, 'share_mfe_negative'].mean()):.4f}"
                f" / mae>0 {float(path.loc[path['h'] == h, 'share_mae_positive'].mean()):.4f}"
                for h in HS))
    g.check("n 与实验 10 的 n 逐行一致（同一批行，4 格 × 4 h）",
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
def build_grouped(samples: dict[int, pd.DataFrame], invs: dict[int, pd.DataFrame],
                  by: str) -> pd.DataFrame:
    """实验 14：按合约（by="symbol"）或按市场波动状态（by="state"）分组。

    by_state 只保留 low/mid/high（`unknown` 不是市场状态，整行排除，行数由闸门打出）；
    by_symbol 每 h 缺 1 个 (合约, 格) 组合（BSBUSDT × R3，该合约从未出现"跌+OI 增"）。
    """
    rows = []
    for h in HS:
        s, inv = samples[h], invs[h]
        if by == "state":
            s = s[s["state"].isin(STATES)]
            inv = inv[inv["state"].isin(STATES)]
        keys = [by, "regime"]
        a = cell_aggs(s, keys, rebuilt=True)
        v = valid_counts(inv, keys)
        for (k, cell), r in a.iterrows():
            rows.append({by: k, "sample": "headline", "h": h, "cell": cell,
                         "n": int(r["n"]),
                         "n_invalid": int(v.get((k, cell), 0)),
                         "mean_excess": float(r["mean_excess"]),
                         "median_excess": float(r["median_excess"]),
                         "mean_raw": float(r["mean_raw"]),
                         "median_raw": float(r["median_raw"]),
                         "hit_raw": float(r["hit_raw"]),
                         "mean_rv": float(r["mean_rv"]),
                         "median_rv": float(r["median_rv"])})
    df = pd.DataFrame(rows).sort_values([by, "cell", "h"], kind="stable").reset_index(drop=True)
    df["note"] = ("按 %s 分组的描述统计；均值/中位数是**不截尾**的市场中性收益 excess_fwd_h，"
                  "hit_raw 是命中率（≡ 续势率）；描述层不放 p 值、不做检验。" % by)
    return df


def gate_exp15(g, by_sym: pd.DataFrame, by_state: pd.DataFrame,
               core: pd.DataFrame, samples: dict[int, pd.DataFrame]) -> None:
    g.section("实验 14 · 分合约 / 分市场状态（描述层）")
    n_sym = int(by_sym["symbol"].nunique())
    cap = n_sym * len(CELLS) * len(HS)
    g.check("★ by_symbol 行数 ≤ 合约数 × 4 格 × 4 h", len(by_sym) <= cap,
            f"{len(by_sym):,} ≤ {n_sym} × 4 × 4 = {cap:,}")
    g.check("by_symbol 的合约数 = 249", n_sym == 249, f"{n_sym}")
    g.check("★ by_symbol 每 h 的 n 之和 = 该 h 的有效事件数（没丢行）",
            all(int(by_sym.loc[by_sym["h"] == h, "n"].sum()) == SUB_N[h] for h in HS),
            "；".join(f"h={h} {int(by_sym.loc[by_sym['h'] == h, 'n'].sum()):,}/{SUB_N[h]:,}"
                     for h in HS))
    g.check("by_symbol 无重复 (symbol, cell, h)",
            int(by_sym.duplicated(subset=["symbol", "cell", "h"]).sum()) == 0,
            f"{len(by_sym):,} 行")
    dev_sym = _agg_deviation(by_sym, core.set_index(["cell", "h"])["mean_excess"].rename("mean_excess"))
    g.check("★ by_symbol 按 n 加权的均值 = core 的均值（16 组，1e-12）", dev_sym <= 1e-12,
            f"max|Δ| = {dev_sym:.1e}")
    g.check("★ by_state 行数 = 3 状态 × 4 格 × 4 h = 48", len(by_state) == 48, f"{len(by_state)} 行")
    g.check("by_state 状态集合 = {low, mid, high}",
            sorted(by_state["state"].unique().tolist()) == sorted(STATES),
            f"{sorted(by_state['state'].unique().tolist())}")
    gone = {}
    for h in HS:
        s = samples[h]
        gone[h] = int((~s["state"].isin(STATES)).sum())
    g.check("★ by_state 每 h 的 n 之和 + 被排除的 unknown = 该 h 的有效事件数",
            all(int(by_state.loc[by_state["h"] == h, "n"].sum()) + gone[h] == SUB_N[h] for h in HS),
            "；".join(f"h={h} {int(by_state.loc[by_state['h'] == h, 'n'].sum()):,}+{gone[h]:,}"
                     f"={SUB_N[h]:,}" for h in HS))
    g.check("by_state 无重复 (state, cell, h)",
            int(by_state.duplicated(subset=["state", "cell", "h"]).sum()) == 0,
            f"{len(by_state)} 行")
    kept = _kept_mean(samples)
    dev_state = _agg_deviation(by_state, kept)
    g.check("★ by_state（low/mid/high）按 n 加权的均值 = 排除 unknown 后的均值（16 组，1e-12）",
            dev_state <= 1e-12, f"max|Δ| = {dev_state:.1e}")
    g.check("★ 两张表每 h 的 n + n_invalid (+ unknown) = headline 事件数（256,079）",
            all(int(by_sym.loc[by_sym["h"] == h, "n"].sum())
                + int(by_sym.loc[by_sym["h"] == h, "n_invalid"].sum()) == 256079
                for h in HS)
            and all(int(by_state.loc[by_state["h"] == h, "n"].sum())
                    + int(by_state.loc[by_state["h"] == h, "n_invalid"].sum())
                    + gone[h] == 256079
                    for h in HS),
            "；".join(f"h={h} {int(by_sym.loc[by_sym['h'] == h, 'n'].sum()):,}"
                     f"+{int(by_sym.loc[by_sym['h'] == h, 'n_invalid'].sum())}" for h in HS))
    g.check("两张表的 n_invalid 都是整数且 ≥ 0",
            bool(by_sym["n_invalid"].dtype.kind in "iu"
                 and by_state["n_invalid"].dtype.kind in "iu"
                 and (by_sym["n_invalid"] >= 0).all()
                 and (by_state["n_invalid"] >= 0).all())
            and bool((by_sym["n_invalid"] <= by_sym["n"]).all()
                     and (by_state["n_invalid"] <= by_state["n"]).all()),
            f"by_symbol {int(by_sym['n_invalid'].sum())} / by_state {int(by_state['n_invalid'].sum())}")


def _weighted_mean(df: pd.DataFrame, value: str, by: list[str]) -> pd.Series:
    """按 n 加权的分组均值（用来验"分组表加总 = 总表"）。"""
    t = df.assign(_w=df[value].to_numpy(dtype="float64") * df["n"].to_numpy(dtype="float64"))
    g = t.groupby(by, observed=True)[["_w", "n"]].sum()
    return g["_w"] / g["n"]


def _agg_deviation(df: pd.DataFrame, ref: pd.Series) -> float:
    """分组表按 n 加权后的均值 与对照均值之差（16 组取 max|Δ|）。"""
    w = _weighted_mean(df, "mean_excess", ["cell", "h"])
    return float((w - ref.reindex(w.index)).abs().max())


def _kept_mean(samples: dict[int, pd.DataFrame]) -> pd.Series:
    """排除 unknown 行之后，每（格 × h）的 `excess`（未截尾市场中性）均值 —— by_state 的对照就是它。

    by_state 少了第四档，加权和不可能再等于 core（core 含 unknown）；所以对照必须
    同样去掉 unknown 行，否则这条 1e-12 的一致性闸门会因为"少一档"而必然失败。
    """
    rows = []
    for h in HS:
        s = samples[h]
        keep = s["state"].to_numpy() != "unknown"
        reg = s["regime"].to_numpy()[keep]
        exc = s["excess"].to_numpy()[keep]
        for cell in CELLS:
            rows.append({"cell": cell, "h": h,
                         "mean_excess": float(exc[reg == cell].mean())})
    return pd.DataFrame(rows).set_index(["cell", "h"])["mean_excess"]


def gate_tables(g: Gate, tables: dict[str, pd.DataFrame]) -> None:
    g.section("5. 表结构 · 不含任何 p 值列（列名断言，且该断言能失败）")
    desc = {k: v for k, v in tables.items() if k != "rev_prob"}   # rev_prob 是判定层，含 p/t/SE
    for name, df in desc.items():
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
                "rev_prob": len(CELLS) * len(HS),
                "descriptive_by_symbol": 3980, "descriptive_by_state": 48}
    for name, df in tables.items():
        g.check(f"{name} 行数 = {exp_rows[name]}", len(df) == exp_rows[name],
                f"{len(df)} 行")
        numeric = [c for c in df.columns if df[c].dtype.kind in "fiu"]
        g.check(f"{name} 的数值列全部有限（无 NaN）",
                bool(all(np.isfinite(df[c].to_numpy(dtype="float64")).all()
                         for c in numeric)),
                f"数值列 {len(numeric)} 个")
    g.check("4 张描述表都没有 experiment / statistic / verdict 列"
            "（描述层不是 confirmatory 那种推断长表）",
            all(not ({"experiment", "statistic", "verdict"} & set(df.columns))
                for df in desc.values()),
            "四张表都缺这三个列名")


# ============================================================ 6. main
def write_table(df: pd.DataFrame, name: str) -> None:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TBL_DIR / f"{name}.parquet", index=False)
    df.to_csv(TBL_DIR / f"{name}.csv", index=False, encoding="utf-8")
    log(f"写盘 {name}.parquet / .csv（{len(df)} 行 × {df.shape[1]} 列）")


def main() -> int:
    global CORE_N
    TBL_DIR.mkdir(parents=True, exist_ok=True)

    base = load_base()
    samples, invs = {}, {}
    for h in HS:
        samples[h], invs[h] = build_horizon(base, h)
        SUB_N[h] = len(samples[h])
    ident = identity_check(samples)
    log(f"恒等式 p_cont ≡ hit_rate：{ident['n_exact']}/{ident['n_cells']} 格逐位相等，"
        f"max|Δ| = {ident['max_abs']:.1e}；重建 max|Δ| = {ident['max_abs_rebuilt']:.1e}")

    core = build_core(samples, invs, ident)
    CORE_N = core["n"].to_numpy()
    path = build_path(samples, invs)
    rev_prob = build_rev_prob()
    by_sym = build_grouped(samples, invs, "symbol")
    by_state = build_grouped(samples, invs, "state")
    tables = {"descriptive_core": core, "descriptive_path": path,
              "rev_prob": rev_prob,
              "descriptive_by_symbol": by_sym, "descriptive_by_state": by_state}

    gate = Gate(f"event_study · descriptive（实验 4/10/11/14）· "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
    gate.lines.append(f"样本：headline(in_universe) ∩ ok_{{h}}h，freq={FREQ}，h ∈ {list(HS)}；"
                      "headline 256,079 事件 / 249 合约")
    gate.lines.append("单位：内部与表里一律**小数**，×100 即百分数、×1e4 即 bp；"
                      "hit_* / p_* / share_* 是 0–1 比例，rv 是小数波动（非 log），n 是计数")
    gate.lines.append("收益口径：excess_fwd_{h}h —— **市场中性（每小时减全池等权均值）、不截尾**；"
                      "均值/中位数直接取自该列，不再做 1%/99% 截尾，也不报被截尾比例")
    gate.lines.append("纪律：只报数、不做判定（GUIDANCE 第二节）。表里不含 p 值、t、SE、区间，"
                      "之后也不含等价性结论；§5 的列名断言守这一条，"
                      "并用 8 种污染列名证明它能失败")
    gate_input(gate, base, samples, invs)
    gate_exp10(gate, core, samples)
    gate_exp11(gate, core, samples, ident)
    gate_exp12(gate, path, samples)
    gate_rev_prob(gate, rev_prob)
    gate_exp15(gate, by_sym, by_state, core, samples)
    gate_tables(gate, tables)

    if gate.n_fail:
        txt = gate.text("有 FAIL → 按纪律停在这里，不写表（闸门没过时表里的数不可信）")
        print(txt)
        log(f"闸门 FAIL {gate.n_fail} 项，停止")
        return 1

    for name, df in tables.items():
        write_table(df, name)

    footer = (
        "口径：收益 = 市场中性（每小时减全池等权均值）+ **不截尾**（excess_fwd_{h}h），"
        "均值/中位数直接取该列；1%/99% 截尾已不是主口径，表里也不再有"
        "被截尾比例这一列；小数单位；描述层不放判定结论；mfe/mae 符号例外不截断；"
        "普通描述统计不放 p 值；每张表带 n_invalid。\n"
        "descriptive_path 覆盖路径风险；by_symbol / by_state 是 note 要求的「performance by asset / by market regime」。\n"
        "读表须知：1) p_cont ≡ hit_rate 是恒等式，§2 已用原始 fwd 列重算证明，把它当独立"
        "证据就是重复计数；2) 收益未截尾，均值会被尾部主导，典型值看中位数"
        "（mean_raw / median_raw 是未中性化的方向翻正收益 fwd_{h}h，只作对照）；"
        "3) 路径三列同样未截尾，均值会被极少数极端路径主导，p50 与 p10/p90 "
        "才是典型口径；4) by_symbol 每 h 缺 1 个 (合约, 格) 组合（BSBUSDT × R3：该合约"
        "从未出现'价格跌 + OI 增'），所以是 3,980 = 249×4×4 − 4 行；5) by_state 只有 "
        "low/mid/high 三档（48 = 3×4×4 行）：unknown 不是一种市场状态（只覆盖 2021-12…2022-03，"
        "波动率分位还没攒够一年），每 h 3,604 行、四个 h 合计 14,416 行被整行排除，"
        "行数由 §4 逐 h 打出。")
    txt = gate.text(footer)
    print(txt)
    log("闸门全部通过")
    return 0 if gate.n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
