"""Phase 3 · baselines_v2 —— 实验 13（四条基准并排）+ 实验 8（五个价差并排）

一句话
    note §9 的判定句是"只有比这些简单基线更好才算有价值"。本文件把四类**简单基线**
    放在与四状态事件**完全相同的因变量、样本与推断口径**下各估一遍，再把五组多空价差
    并到一张表里比。**只报数、不做判定**（`PHASE3_GUIDANCE.md` 第二章：实验 9–15
    报数即可，表里不放 p 值）。

四条基线（都带 SE，一条都不许是 NaN）
    1 纯价格   `|price_change| > price_thr` 的全部 ok 行（**不管 OI**），
              方向 = `sign(price_change)`。向上 / 向下 / 合计三行。
    2 纯 OI    `|oi_change| > oi_thr` 的全部 ok 行（**不管价格**），
              方向 = `sign(oi_change)`。三行。
    3 纯 funding  note §7 的**四档**：`f ≤ p25` / `p25 < f ≤ p75` / `f > p75` / `f > p90`。
              ⚠️ **`f > p90` 是 `f > p75` 的子集，两者重叠**（实测 324,054 行全部重叠，
              `lib/schema.py` 也写明"四个 funding bool 是【重叠条件】不是分区"）——所以
              `funding_high` 的均值**不能**用四个重叠哑变量做饱和回归（那样解出来的是
              "高于 p75 且不高于 p90"那一格，实测会把 +0.0018 变成 +0.0010）。本文件用
              **互斥的三格**（low / mid / high 含 extreme）+ 单独一格 extreme，每格的系数
              才真的是该档均值（闸门 §4 用格均值逐格对拍，差 < 1e-12）。
              funding **无方向含义**，只报水平（均值 + 中位数）。
    4 随机时点  每个事件换成**同一时刻、同一波动状态下的另一个随机合约**（note §7）。
              v1 是"同一合约的随机时刻"，那会把市场状态固定住 —— 随机对照于是变成
              "这小时的共同因子"，测不出"事件本身有没有料"。**1000 轮**，报表给中位数
              与 [p5, p95]。层 = (hour, mkt_vol_state)：实测 `mkt_vol_state` 在同一小时的
              所有合约上取值相同（40,898 个小时里 nunique 全为 1），所以这一层等价于
              "同一小时"；闸门 §0 专门验这条（不唯一的话分层就是错的）。
              同一小时内对**除自己以外**的候选合约做均匀抽样：候选块长度 c、自己在块内
              位置 p，移位 s ~ U{1..c−1}，取 (p + s) mod c —— 不用拒绝法，也不会抽到自己。
              c = 1 的小时没有"另一个合约"可换，该事件丢掉（数量在闸门 §4 报出来）。

五个价差（note §9 的表；同一口径 = 水平差 mean(多头) − mean(空头)，SE 按合约聚类）
    | 组 | 多头 | 空头 |
    | 纯价格 | 价格极端上涨 | 价格极端下跌 |
    | 纯 OI | OI 极端增加 | OI 极端减少 |
    | 纯 funding | f > p75 | f ≤ p25 |
    | 四状态 | R1 | R4 |
    | 随机（同刻随机合约） | 同方向（上涨事件换成随机合约） | 同方向（下跌事件换成随机合约） |

    "水平差"而不是"符号化均值之差"：多空组合的收益是"多头腿取 +y、空头腿取 −y"，
    即 mean(y|多头) − mean(y|空头)。符号化的 `sig_mean = mean(d·y)` 另列一行报，
    两者是**不同的估计量**；混用会让价差差出 2·mean(y|空头)。

与 v1 的五处口径差异（`event_study.py` 的 `experiment_baselines` 已过时：不改、不用）
    1 因变量：v1 是**原始** `fwd_h`（其 `mean_fwd` = mean(fwd_24h)），v2 是
      `winsor_fwd_h` —— 市场中性 + 全池 1%/99% 截尾（D13 / D14.3）。原始收益下
      funding 高档是 +0.2785pp，与 v2 的水平不可比。
    2 推断：v1 是双向聚类，v2 **只按合约**（D17，`stats_core.cluster_se`）。
    3 funding：v1 只有三档、缺 `> p90`，且三行的 `se_sig` 全 NaN；v2 四档、每档带 SE。
    4 随机对照：v1 是"同合约随机时刻"（D5 的分层 = 合约 × 波动状态），v2 是
      "同刻同波动状态的**另一个合约**"。
    5 样本量锚点沿用 v1（它是对的）：纯价格 n_pop = 2,041,947（full）/ 555,012
      （headline），纯 OI = 2,001,052 / 546,440 —— 本文件逐位复现（闸门 §2）。

样本与口径（一处定义，全文共用）
    headline = `in_universe`（当月流动性前 50），full = 全部 285 个合约（只作稳健性）。
    行集合 = 标签层 `excl_reason == "ok"` 的全部 7,010,789 行。
    因变量 = `winsor_fwd_h`（h = EventConfig.horizons = 1/4/8/24）：
      · **事件行直接读事件表** `events_1h.parquet` 里存的值；
      · **非事件行现拼**，但必须与事件表同一口径：去均值基 = label-ok 全池 7,010,789 行
        逐小时等权去均值（`stats_core.cross_sectional_demean`，n_per_hour 中位数 173），
        截尾阈值 = 同一池上的 1%/99% 分位（`docs/winsor_thresholds.json` 的 h=24 那一组，
        本文件逐位复现；h=1/4/8 没有落盘的 JSON，用**同一条管线**在同一池上算，
        并在闸门 §1 与事件表逐行对拍 max|Δ| = 0）。
    验收（本文件的核心闸门）：现算的 winsor / excess 取到事件行上必须与事件表**逐行
      相等**，四个 h 都是 max|Δ| = 0.000e+00（923,210 / 923,130 / 922,995 / 921,972 行）。
      这条过不了就 `raise SystemExit`，不往下走 —— 口径没对齐时往下算出来的任何数都是垃圾。
    推断：`stats_core.cluster_se`，**只按合约 symbol 聚类**（D17），无小样本校正；
      均值与 OLS 一次都不重抽。中位数没有解析标准误，用 `stats_core.cell_medians_boot`
      （按小时有放回、整小时带走，reps / seed 取自 `EventConfig`）。
    单位：内部一律**小数**（D14.2），表里 `unit = decimal_return`，×100 = 百分数、×1e4 = bp。

估计量（每个都带 SE，且 SE > 0 —— v1 的 NaN 不许重现）
    level_mean    组内 winsor 收益的均值 + 按合约聚类 SE。用**饱和回归**（互斥组哑变量）
                  一次给出所有组的均值与整块协方差，于是任何线性组合（合计、价差）的 SE
                  都是 `sqrt(w'Vw)`，不必重算聚类。闸门 §4 逐格对拍 b_j 与原始格均值。
    sig_mean      `mean(d·y)`，d = 方向符号。只对**混合了方向**的合计组有意义（方向在
                  组成员内恒定时它只是 level 的 ±1 倍，故不重复报）；由同一回归的线性组合
                  给出：w = (n_up, −n_dn) / n_all。
    level_median  组内中位数 + 按小时重抽 1000 轮的 sd；区间取重抽分布 2.5/97.5 百分位。
                  ⚠️ 只在 headline 报：full 的 funding 中位数要 7,000,165 行 × 1000 轮
                  = 477 秒/期（实测），四个 h 就是 32 分钟，而 full 只作稳健性。
                  缺失集合被闸门 §4 钉死为 {sample=full} × {statistic=level_median}。
    random_*      1000 轮重抽分布的**中位数**、[p5, p95]，以及重抽 sd 当 SE
                  （Monte-Carlo，不是按合约聚类，不可与事件 SE 直接比 —— 表注写明）。

输出
    data/06_event_study/tables/freq=1h/baselines_v2.parquet      + .csv（每条基线的水平 + SE）
    data/06_event_study/tables/freq=1h/baselines_spread.parquet  + .csv（五个价差）
    data/06_event_study/docs/step10_checks_baselines.txt         （闸门全文 + 并排结果）

用法
    python phase3_event/baselines_v2.py       # 全部 PASS 退出码 0，任一 FAIL 退出码 1
"""
from __future__ import annotations

import json
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
HS = tuple(EVENT.horizons)         # (1, 4, 8, 24)；主前向期 = 最大值
H_MAIN = max(HS)
SAMPLES = ("headline", "full")
"""headline 为主、full 作稳健性（D13）。顺序即表里的顺序。"""

Z95 = NormalDist().inv_cdf(0.975)  # 1.959963984540054，与 confirmatory/oi_increment 同一个数

ROOT = HERE.parent
OUT_ROOT = ROOT / "data" / "06_event_study"
LAB_ROOT = ROOT / "data" / "05_regime" / "regime_labels" / ("freq=" + FREQ)
FWD_ROOT = OUT_ROOT / "forward" / ("freq=" + FREQ)
EV_PATH = OUT_ROOT / "events" / ("events_" + FREQ + ".parquet")
TBL_DIR = OUT_ROOT / "tables" / ("freq=" + FREQ)
DOC_DIR = OUT_ROOT / "docs"
CHECKS_PATH = DOC_DIR / "step10_checks_baselines.txt"
THR_PATH = DOC_DIR / "winsor_thresholds.json"

T0 = pd.Timestamp("2021-12-01", tz="UTC")
"""小时编码的原点（SPEC §零）。两套编码混用会 0 行匹配且不报错，所以只算一次。"""

UNIT = "decimal_return"
M_CLUSTER = "symbol_cluster"
M_MEDIAN = "hour_bootstrap_" + str(EVENT.random_draws)
M_RANDOM = "random_contract_" + str(EVENT.random_draws) + "reps"

REG_MAP = {"R1": 0, "R2": 1, "R3": 2, "R4": 3, "undefined": 4}
VS_MAP = {"low": 0, "mid": 1, "high": 2, "unknown": 3}
STATE_GROUPS = ("R1", "R2", "R3", "R4")

FAMILIES = (
    # name, 互斥成员组, 合计组（或 None）, 中位数报在哪（members/aggregate/None）, 报 sig_mean
    ("price", ("price_up", "price_down"), "price_all", "aggregate", True),
    ("oi", ("oi_up", "oi_down"), "oi_all", "aggregate", True),
    ("funding", ("funding_low", "funding_mid", "funding_high"), None, "members", False),
    ("state", STATE_GROUPS, None, "members", False),
)
"""四个**回归族**。组名 → 掩码在 build_masks 里一处定义。

funding 的 funding_extreme（f > p90）不在成员里：它是 funding_high 的子集，
放进饱和回归会破坏"系数 = 格均值"，所以它自己单独跑一格。
"""

EXTRA_GROUPS = ("funding_extreme",)
"""与某个成员重叠、只能单独估的组（funding_extreme ⊂ funding_high）。"""

SPREADS = (
    ("price", "price_up", "price_down"),
    ("oi", "oi_up", "oi_down"),
    ("funding", "funding_high", "funding_low"),
    ("four_state", "R1", "R4"),
    ("random", "random_up", "random_down"),
)
"""note §9 的五组价差。random 走 1000 轮重抽，其余四组由饱和回归的线性组合给出。"""

GROUP_NOTE = {
    "price_up": "|price_change| > price_thr 且 price_change > 0（不管 OI）；方向 +1",
    "price_down": "|price_change| > price_thr 且 price_change < 0（不管 OI）；方向 −1",
    "price_all": "纯价格基线：价格超阈的全部 ok 行（事件行 + OI 安静的对照行都在内）",
    "oi_up": "|oi_change| > oi_thr 且 oi_change > 0（不管价格）；方向 +1",
    "oi_down": "|oi_change| > oi_thr 且 oi_change < 0（不管价格）；方向 −1",
    "oi_all": "纯 OI 基线：OI 超阈的全部 ok 行（不管价格）",
    "funding_low": "funding ≤ p25（标签列 funding_negative；note 写作低于 p25）",
    "funding_mid": "p25 < funding ≤ p75（funding_neutral）",
    "funding_high": "funding > p75（funding_high；**含** extreme，即 note 的高于 p75 档）",
    "funding_extreme": "funding > p90（funding_extreme；**是 funding_high 的子集**，重叠不是分区）",
    "R1": "价格涨 + OI 增（事件行）",
    "R2": "价格涨 + OI 减",
    "R3": "价格跌 + OI 增",
    "R4": "价格跌 + OI 减",
    "random_up": "同刻同波动状态下的另一个随机合约（事件为价格上涨时的样本）",
    "random_down": "同刻同波动状态下的另一个随机合约（事件为价格下跌时的样本）",
    "random_all": "同刻同波动状态下的另一个随机合约（全部事件）",
}

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


def _hour(ts: pd.Series) -> np.ndarray:
    """ts_end → 整小时编码（SPEC §零；与 build_event_table.py 逐位同一个式子）。"""
    return ((ts - T0).dt.total_seconds() // 3600).to_numpy("int64")


def _lin(b: np.ndarray, V: np.ndarray, w) -> tuple[float, float]:
    """线性组合 w'b 的点估计与 SE（协方差取自同一组 cluster_se，D14.5）。"""
    w = np.asarray(w, dtype="float64").ravel()
    est = float(w @ b)
    return est, math.sqrt(max(float(w @ V @ w), 0.0))


# ============================================================ 0. 标签表 → 全池
LABEL_COLS = ["symbol", "ts_end", "excl_reason", "price_change", "oi_change",
              "price_thr", "oi_thr", "in_universe", "regime", "mkt_vol_state",
              "funding_negative", "funding_neutral", "funding_high", "funding_extreme"]


def read_labels() -> tuple[dict[str, int], pd.DataFrame, np.ndarray, dict]:
    """标签表一遍：符号表、label-ok 全池的全局键与建模要用的列。

    为什么要全局键（`hour * n_sym + symbol_code`）而不是逐分区 join：标签表与前向
    面板的**分区键不是同一个**（月界那一行落在不同 chunk），逐分区 merge 会静默丢掉
    9,446 个 fwd 值（D18 的坑）。两边都按全局键对，(hour, symbol) 唯一性由闸门 §0 检查。
    """
    lab_files = sorted(LAB_ROOT.rglob("*.parquet"))
    syms: set[str] = set()
    for p in lab_files:
        syms.update(pd.read_parquet(p, columns=["symbol"])["symbol"].unique().tolist())
    sym_index = {s: i for i, s in enumerate(sorted(syms))}
    n_sym = len(sym_index)

    keys, parts = [], []
    n_label = n_lab_ok = n_vs_conflict = 0
    for p in lab_files:
        L = pd.read_parquet(p, columns=LABEL_COLS)
        n_label += len(L)
        L = L.loc[L["excl_reason"].to_numpy() == "ok"]
        n_lab_ok += len(L)
        hour = _hour(L["ts_end"])
        code = L["symbol"].map(sym_index).to_numpy("int64")
        keys.append(hour * n_sym + code)
        reg = L["regime"].map(REG_MAP)
        vs = L["mkt_vol_state"].map(VS_MAP)
        if reg.isna().any() or vs.isna().any():
            raise SystemExit("regime / mkt_vol_state 出现了 REG_MAP / VS_MAP 里没有的取值，停")
        # 随机层的闸门要用：同一小时里 mkt_vol_state 必须唯一
        vs_h = pd.DataFrame({"hour": hour, "vs": vs.to_numpy("int8")})
        n_vs_conflict += int((vs_h.groupby("hour")["vs"].nunique() > 1).sum())
        pc = L["price_change"].to_numpy("float64")
        oc = L["oi_change"].to_numpy("float64")
        parts.append(pd.DataFrame({
            "hour": hour,
            "sym": code.astype("int32"),
            "pc": pc,
            "oc": oc,
            "uni": L["in_universe"].to_numpy(dtype=bool),
            "reg": reg.to_numpy("int8"),
            "neg": L["funding_negative"].to_numpy(dtype=bool),
            "neu": L["funding_neutral"].to_numpy(dtype=bool),
            "hig": L["funding_high"].to_numpy(dtype=bool),
            "ext": L["funding_extreme"].to_numpy(dtype=bool),
            # 两个掩码在这里定死，后面不再碰 price_thr / oi_thr
            "pm": np.abs(pc) > L["price_thr"].to_numpy("float64"),
            "om": np.abs(oc) > L["oi_thr"].to_numpy("float64"),
        }))
    pool_keys = np.concatenate(keys)
    P = pd.concat(parts, ignore_index=True)
    del parts
    order = np.argsort(pool_keys, kind="stable")
    P = P.iloc[order].reset_index(drop=True)
    pool_keys = pool_keys[order]
    meta = {"n_lab_files": len(lab_files), "n_label": n_label, "n_lab_ok": n_lab_ok,
            "n_pool": int(pool_keys.size), "n_sym": n_sym,
            "n_pool_uniq": int(np.unique(pool_keys).size),
            "n_vs_conflict_hours": n_vs_conflict}
    log(f"标签表 {len(lab_files)} 个分区 / {n_label:,} 行 → label-ok {n_lab_ok:,} 行"
        f"（{n_sym} 个合约）；vol_state 在同一小时内不唯一的小时 {n_vs_conflict}")
    return sym_index, P, pool_keys, meta


# ============================================================ 1. 前向面板
def read_forward(sym_index: dict[str, int]) -> dict:
    """前向面板一遍：全局键 + 四个 h 的 fwd_h（float64）与 ok_h。"""
    n_sym = len(sym_index)
    fwd_files = sorted(FWD_ROOT.rglob("*.parquet"))
    cols = ["symbol", "ts_end"] + [m + "_" + str(h) + "h" for h in HS for m in ("fwd", "ok")]
    keys = []
    vals = {h: [] for h in HS}
    oks = {h: [] for h in HS}
    for p in fwd_files:
        F = pd.read_parquet(p, columns=cols)
        hour = _hour(F["ts_end"])
        keys.append(hour * n_sym + F["symbol"].map(sym_index).to_numpy("int64"))
        for h in HS:
            # float32 → float64：不先转会让去均值残差留在 2e-8 量级（SPEC §五.4）
            vals[h].append(pd.to_numeric(F["fwd_" + str(h) + "h"],
                                         errors="coerce").to_numpy("float64"))
            oks[h].append(np.asarray(pd.to_numeric(F["ok_" + str(h) + "h"], errors="coerce")
                                     .fillna(0).to_numpy("float64") > 0.5))
    out = {"keys": np.concatenate(keys),
           "fwd": {h: np.concatenate(vals[h]) for h in HS},
           "ok": {h: np.concatenate(oks[h]) for h in HS},
           "n_files": len(fwd_files)}
    log(f"前向面板 {len(fwd_files)} 个分区 / {out['keys'].size:,} 行")
    return out


# ============================================================ 2. 池子（去均值 + 截尾）
def build_pool(P: pd.DataFrame, pool_keys: np.ndarray, fwd: dict) -> dict:
    """label-ok 全池上逐 h 做市场中性 + 全池截尾。

    去均值基 = label-ok 的全部 7,010,789 行（SPEC §零）。ok_h == False 的行 fwd 是 NaN，
    cross_sectional_demean 与 winsorize 都跳过 NaN，所以这批行对均值与分位毫无影响。
    """
    order = np.argsort(fwd["keys"], kind="stable")
    sk = fwd["keys"][order]
    pos = np.searchsorted(sk, pool_keys)
    if not bool((sk[pos] == pool_keys).all()):
        raise SystemExit("池子键在前向面板里找不到：label-ok 全集应被前向面板覆盖，口径已坏，停")
    hour = P["hour"].to_numpy()
    out = {"win": {}, "exc": {}, "ok": {}, "lo": {}, "hi": {},
           "n_per_hour": {}, "share_clip": {}, "n_ok_true": {},
           "n_fwd_rows": int(fwd["keys"].size),
           "n_fwd_outside": int(fwd["keys"].size - pool_keys.size)}
    for h in HS:
        f = fwd["fwd"][h][order][pos]
        okh = fwd["ok"][h][order][pos]
        df, nph = sc.cross_sectional_demean(
            pd.DataFrame({"hour": hour, "fwd": f}), "fwd", out_col="excess")
        exc = df["excess"].to_numpy("float64")
        win, (lo, hi) = sc.winsorize(exc, lower=EVENT.winsor_lower, upper=EVENT.winsor_upper)
        out["exc"][h] = exc
        out["win"][h] = win
        out["ok"][h] = okh
        out["lo"][h] = lo
        out["hi"][h] = hi
        out["n_per_hour"][h] = nph
        out["share_clip"][h] = float(np.mean((win != exc)[np.isfinite(exc)]))
        out["n_ok_true"][h] = int(okh.sum())
        log(f"  h={h:2d} 去均值 + 截尾：n_per_hour 中位数 {nph.median():.0f}；"
            f"阈值 [{lo:+.10f}, {hi:+.10f}]；池上被压 {out['share_clip'][h]:.4%}")
    return out


# ============================================================ 3. 与事件表逐行对拍
def align_events(P: pd.DataFrame, pool: dict, pool_keys: np.ndarray,
                 sym_index: dict[str, int], M: dict) -> dict:
    """★ 核心闸门：现算的 winsor / excess 取到事件行上必须与事件表**逐行相等**。

    事件表是**冻结产物**，只读不写；读它是为了验口径，并把事件行的因变量**原样取过来**
    （"事件行直接读事件表"）。四个 h 都要对：h=1/4/8 的截尾阈值没有落盘 JSON，
    只能靠这条证明"同一条管线"。
    """
    cols = ["symbol", "hour", "regime"] + \
           [m + "_" + str(h) + "h" for h in HS for m in ("winsor_fwd", "excess_fwd", "ok")]
    ev = pd.read_parquet(EV_PATH, columns=cols)
    nsym = len(sym_index)
    evkey = ev["hour"].to_numpy("int64") * nsym + ev["symbol"].map(sym_index).to_numpy("int64")
    pos = np.searchsorted(pool_keys, evkey)
    found = (pos < pool_keys.size) & (pool_keys[np.minimum(pos, pool_keys.size - 1)] == evkey)
    n_dup = int(pos.size - np.unique(pos).size)
    same_set = bool(found.all() and n_dup == 0
                    and np.array_equal(np.sort(pos), np.flatnonzero(M["event"])))
    d_reg = int(np.count_nonzero(ev["regime"].map(REG_MAP).to_numpy("int8")
                                 != P["reg"].to_numpy("int8")[pos]))

    res = {"n_ev": int(len(ev)), "n_found": int(found.sum()), "n_dup_pos": n_dup,
           "same_set": same_set, "n_reg_mismatch": d_reg, "per_h": {}}
    for h in HS:
        ev_win = pd.to_numeric(ev["winsor_fwd_" + str(h) + "h"],
                               errors="coerce").to_numpy("float64")
        ev_exc = pd.to_numeric(ev["excess_fwd_" + str(h) + "h"],
                               errors="coerce").to_numpy("float64")
        ev_ok = pd.to_numeric(ev["ok_" + str(h) + "h"], errors="coerce") \
            .fillna(0).to_numpy("float64") > 0.5
        mine_win = pool["win"][h][pos]
        mine_exc = pool["exc"][h][pos]
        cmp = ev_ok & np.isfinite(ev_win)
        d_win = float(np.abs(mine_win[cmp] - ev_win[cmp]).max())
        d_exc = float(np.abs(mine_exc[cmp] - ev_exc[cmp]).max())
        res["per_h"][h] = {"n_cmp": int(cmp.sum()), "d_win": d_win, "d_exc": d_exc,
                           "ok_eq": bool(np.array_equal(pool["ok"][h][pos], ev_ok)),
                           "n_exact": int(np.count_nonzero(mine_win[cmp] == ev_win[cmp]))}
        # 事件行的因变量**原样取事件表的值**（同一批数字，但来源是冻结产物）
        pool["win"][h][pos] = ev_win
        log(f"  h={h:2d} 与事件表对拍 {cmp.sum():,} 行：winsor max|Δ| {d_win:.3e}"
            f"（{res['per_h'][h]['n_exact']:,} 行逐位相同）；excess max|Δ| {d_exc:.3e}；"
            f"ok_h 逐行相同 {res['per_h'][h]['ok_eq']}")
    return res


# ============================================================ 4. 组定义
def build_masks(P: pd.DataFrame) -> dict[str, np.ndarray]:
    """一处定义全部组掩码（h 无关；ok_h 的过滤在估计时叠加）。"""
    pc = P["pc"].to_numpy("float64")
    oc = P["oc"].to_numpy("float64")
    pm = P["pm"].to_numpy(dtype=bool)
    om = P["om"].to_numpy(dtype=bool)
    reg = P["reg"].to_numpy("int8")
    M = {
        "headline": P["uni"].to_numpy(dtype=bool),
        "event": pm & om,
        "price_all": pm,
        "price_up": pm & (pc > 0),
        "price_down": pm & (pc < 0),
        "oi_all": om,
        "oi_up": om & (oc > 0),
        "oi_down": om & (oc < 0),
        "funding_low": P["neg"].to_numpy(dtype=bool),
        "funding_mid": P["neu"].to_numpy(dtype=bool),
        "funding_high": P["hig"].to_numpy(dtype=bool),
        "funding_extreme": P["ext"].to_numpy(dtype=bool),
    }
    for c in STATE_GROUPS:
        M[c] = reg == REG_MAP[c]
    return M


# ============================================================ 5. 估计
def _cell(y: np.ndarray, keep: np.ndarray, masks, sym: np.ndarray):
    """互斥组的饱和回归：b = 各组均值，V = 按合约聚类的协方差。"""
    X = np.column_stack([m[keep].astype("float64") for m in masks])
    return sc.cluster_se(X, y[keep], sym[keep])


def _median_cell(y: np.ndarray, keep: np.ndarray, labels: np.ndarray,
                 hour: np.ndarray, n_groups: int) -> dict:
    """按小时重抽的中位数分布（cell_medians_boot）：点估计、sd、2.5/97.5 分位。

    labels 是 keep 行上的组号（0..n_groups−1），一次给出所有组。
    """
    yk = y[keep]
    df = pd.DataFrame({"g": labels.astype("int8"), "hour": hour[keep], "y": yk})
    B = sc.cell_medians_boot(df, "y", "g", "hour",
                             reps=EVENT.random_draws, seed=EVENT.random_seed)
    point = np.array([float(np.median(yk[labels == j])) for j in range(n_groups)])
    return {"point": point, "se": B.std(axis=0, ddof=1),
            "lo": np.percentile(B, 2.5, axis=0), "hi": np.percentile(B, 97.5, axis=0)}


def random_block(P: pd.DataFrame, pool: dict, h: int, smask: np.ndarray,
                 ev: np.ndarray, hours_n: int, hcode: np.ndarray) -> dict:
    """随机时点基线：每个事件换成**同一时刻、同一波动状态**下的另一个随机合约。

    层 = (hour, mkt_vol_state)。实测 mkt_vol_state 是市场级变量（同一小时所有合约取值
    相同），所以这一层等价于"同一小时"；闸门 §0 专门验这条，否则分层就是错的。

    抽样：候选集 = 该小时内、同一样本、ok_h 为真、y 有限的**全部**合约（含事件自己）。
    对每个事件在"块内除自己以外的 c−1 个"里**均匀**抽一个 —— 用块内循环移位实现：
    候选块 [start, start+c)，自己的位置 p，移位 s ~ U{1..c−1}，取 (p + s) mod c。
    不用拒绝法，也不会抽到自己。c = 1 的小时没有"另一个合约"可换，该事件丢掉
    （数量在闸门 §4 报出来）。
    """
    y = pool["win"][h]
    cand = smask & np.isfinite(y)
    ci = np.flatnonzero(cand)
    cw = y[ci]
    cnt = np.bincount(hcode[ci], minlength=hours_n)
    cstart = np.concatenate(([0], np.cumsum(cnt)[:-1])).astype("int64")

    ei = np.flatnonzero(ev & cand)
    eh = hcode[ei]
    inblock = (np.searchsorted(ci, ei) - cstart[eh]).astype("int64")
    good = cnt[eh] >= 2
    n_drop = int((~good).sum())
    ei, eh, inblock = ei[good], eh[good], inblock[good]
    c_blk = cnt[eh]
    d = np.sign(P["pc"].to_numpy("float64")[ei])
    up = d > 0
    n_ev = int(ei.size)

    rng = np.random.default_rng(EVENT.random_seed)
    reps = EVENT.random_draws
    dist = np.empty((reps, 5))
    for r in range(reps):
        shift = 1 + (rng.random(n_ev) * (c_blk - 1)).astype("int64")
        j = cstart[eh] + ((inblock + shift) % c_blk)
        yr = cw[j]
        lu = float(yr[up].mean())
        ld = float(yr[~up].mean())
        dist[r] = (float(yr.mean()), float((d * yr).mean()), lu, ld, lu - ld)

    names = ("random_all_level", "random_all_sig", "random_up_level",
             "random_down_level", "random_spread")
    out = {"n": n_ev, "n_drop": n_drop, "n_pop": int((ev & smask).sum()),
           "n_clusters": int(np.unique(P["sym"].to_numpy("int32")[ei]).size)}
    for i, nm in enumerate(names):
        s = dist[:, i]
        out[nm] = {"estimate": float(np.median(s)), "se": float(s.std(ddof=1)),
                   "p5": float(np.percentile(s, 5)), "p95": float(np.percentile(s, 95))}
    return out


def _row(sample: str, h: int, family: str, group: str, statistic: str,
         est: float, se: float, n: int, n_pop: int, n_clusters: int,
         method: str, ci_lo: float = np.nan, ci_hi: float = np.nan,
         p5: float = np.nan, p95: float = np.nan, note: str = "",
         t_nan: bool = False) -> dict:
    # 随机基线的 se 是 Monte-Carlo sd，不构成抽样 t 统计量 → 该行 t 置空（表注写明）
    t = np.nan if t_nan else (est / se if (math.isfinite(se) and se > 0) else np.nan)
    return {"sample": sample, "h": h, "family": family, "group": group,
            "statistic": statistic, "estimate": est, "se": se, "t": t,
            "ci_lo": ci_lo, "ci_hi": ci_hi, "p5": p5, "p95": p95,
            "n": n, "n_pop": n_pop, "n_clusters": n_clusters,
            "method": method, "unit": UNIT, "note": note}


def _row_cluster(sample, h, family, group, statistic, est, se, n, n_pop, ncls,
                 note="") -> dict:
    """按合约聚类的一行（t / 区间都由同一个 SE 推出）。"""
    return _row(sample, h, family, group, statistic, est, se, n, n_pop, ncls,
                M_CLUSTER, ci_lo=est - Z95 * se, ci_hi=est + Z95 * se, note=note)


def _spread(sample, h, group, leg_long, leg_short, ml, ms, est, se, n_l, n_s,
            method, note, t=np.nan, ci_lo=np.nan, ci_hi=np.nan,
            p5=np.nan, p95=np.nan) -> dict:
    return {"sample": sample, "h": h, "group": group,
            "leg_long": leg_long, "leg_short": leg_short,
            "mean_long": ml, "mean_short": ms,
            "estimate": est, "se": se, "t": t,
            "ci_lo": ci_lo, "ci_hi": ci_hi, "p5": p5, "p95": p95,
            "n_long": n_l, "n_short": n_s,
            "method": method, "unit": UNIT, "note": note}


def estimate_all(P: pd.DataFrame, pool: dict, M: dict,
                 hours_n: int, hcode: np.ndarray) -> dict:
    """两个样本 × 四个 h × 四条基线 + 五组价差。"""
    sym = P["sym"].to_numpy("int32")
    hour = P["hour"].to_numpy()
    rows, spreads, rnd, sat = [], [], {}, []
    did = {}
    for sample in SAMPLES:
        smask = M["headline"] if sample == "headline" else np.ones(len(P), dtype=bool)
        for h in HS:
            y = pool["win"][h]
            base = smask & np.isfinite(y)
            for family, members, agg, med_on, has_sig in FAMILIES:
                gmasks = [M[g] & base for g in members]
                keep = gmasks[0].copy()
                for m in gmasks[1:]:
                    keep |= m
                b, V = _cell(y, keep, gmasks, sym)
                n_g = [int(m.sum()) for m in gmasks]
                n_pop_g = [int((M[g] & smask).sum()) for g in members]
                ncls = int(np.unique(sym[keep]).size)
                means = []
                for j, g in enumerate(members):
                    w = np.zeros(len(members))
                    w[j] = 1.0
                    est, se = _lin(b, V, w)
                    sat.append((sample, h, g, est, float(y[gmasks[j]].mean())))
                    means.append(est)
                    rows.append(_row_cluster(sample, h, family, g, "level_mean",
                                             est, se, n_g[j], n_pop_g[j], ncls,
                                             GROUP_NOTE[g]))
                n_all = float(sum(n_g))
                n_pop_all = int(sum(n_pop_g))
                if agg is not None:
                    w_lv = np.array(n_g, dtype="float64") / n_all
                    est, se = _lin(b, V, w_lv)
                    rows.append(_row_cluster(sample, h, family, agg, "level_mean", est, se,
                                             int(n_all), n_pop_all, ncls,
                                             GROUP_NOTE[agg]))
                    if has_sig:
                        # mean(d·y)：d = +1 在第一组成员、−1 在第二组
                        w_sg = w_lv.copy()
                        w_sg[1] *= -1.0
                        est_s, se_s = _lin(b, V, w_sg)
                        rows.append(_row_cluster(
                            sample, h, family, agg, "sig_mean", est_s, se_s,
                            int(n_all), n_pop_all, ncls,
                            "mean(d·y)，d = sign(方向变量)；由同一饱和回归的线性组合给出"
                            "（w = (n_up, −n_dn)/n_all）。与 level_mean 是不同的估计量"))
                if med_on is not None and sample == "headline":
                    if med_on == "members":
                        keep_m = keep
                        labels = np.zeros(int(keep_m.sum()), dtype="int8")
                        for j, m in enumerate(gmasks):
                            labels[m[keep_m]] = j
                        ng = len(members)
                        gnames = list(members)
                        n_list = n_g
                        np_list = n_pop_g
                    else:
                        keep_m = M[agg] & base
                        labels = np.zeros(int(keep_m.sum()), dtype="int8")
                        ng = 1
                        gnames = [agg]
                        n_list = [int(keep_m.sum())]
                        np_list = [int((M[agg] & smask).sum())]
                    mc = _median_cell(y, keep_m, labels, hour, ng)
                    for j, g in enumerate(gnames):
                        rows.append(_row(
                            sample, h, family, g, "level_median",
                            float(mc["point"][j]), float(mc["se"][j]),
                            n_list[j], np_list[j], ncls, M_MEDIAN,
                            ci_lo=float(mc["lo"][j]), ci_hi=float(mc["hi"][j]),
                            note=GROUP_NOTE[g] + "；中位数无解析 SE，按小时有放回重抽 "
                                 + str(EVENT.random_draws) + " 轮（整小时带走）"))
                if agg is not None:
                    # 价差：多头 − 空头（成员顺序 0 = 多、1 = 空）
                    w = np.zeros(len(members))
                    w[0], w[1] = 1.0, -1.0
                    est, se = _lin(b, V, w)
                    spreads.append(_spread(
                        sample, h, family, members[0], members[1], means[0], means[1],
                        est, se, n_g[0], n_g[1], M_CLUSTER,
                        "水平差 mean(多头) − mean(空头)；w'b 与 sqrt(w'Vw) 取自同一饱和回归",
                        t=est / se, ci_lo=est - Z95 * se, ci_hi=est + Z95 * se))
                if family == "state" and sample == "headline" and h == H_MAIN:
                    w = np.array([1.0, -1.0, -1.0, 1.0])
                    est, se = _lin(b, V, w)
                    did = {"estimate": est, "se": se}
                if family == "funding":
                    # high 已经含 extreme（三格是分区）；extreme 单独一格
                    m_ext = M["funding_extreme"]
                    keep_x = m_ext & base
                    bx, Vx = _cell(y, keep_x, [np.ones(len(P), dtype=bool)], sym)
                    n_x = int(keep_x.sum())
                    ncls_x = int(np.unique(sym[keep_x]).size)
                    rows.append(_row_cluster(
                        sample, h, family, "funding_extreme", "level_mean",
                        float(bx[0]), math.sqrt(float(Vx[0, 0])), n_x,
                        int((m_ext & smask).sum()), ncls_x,
                        GROUP_NOTE["funding_extreme"] + "；单独一格（它是 funding_high 的"
                        "子集，放进重叠哑变量会把 high 的系数变成 high 去掉 extreme 那一格）"))
                    sat.append((sample, h, "funding_extreme", float(bx[0]),
                                float(y[keep_x].mean())))
                    if sample == "headline":
                        mc = _median_cell(y, keep_x, np.zeros(n_x, "int8"), hour, 1)
                        rows.append(_row(
                            sample, h, family, "funding_extreme", "level_median",
                            float(mc["point"][0]), float(mc["se"][0]), n_x,
                            int((m_ext & smask).sum()), ncls_x, M_MEDIAN,
                            ci_lo=float(mc["lo"][0]), ci_hi=float(mc["hi"][0]),
                            note=GROUP_NOTE["funding_extreme"] + "；按小时有放回重抽 "
                                 + str(EVENT.random_draws) + " 轮"))
                    i_hi, i_lo = members.index("funding_high"), members.index("funding_low")
                    w = np.zeros(len(members))
                    w[i_hi], w[i_lo] = 1.0, -1.0
                    est, se = _lin(b, V, w)
                    spreads.append(_spread(
                        sample, h, "funding", "funding_high", "funding_low",
                        means[i_hi], means[i_lo], est, se, n_g[i_hi], n_g[i_lo],
                        M_CLUSTER, "水平差 mean(>p75) − mean(≤p25)；high 含 extreme"
                        "（重叠不是分区，high 的均值由三格分区直接给出）",
                        t=est / se, ci_lo=est - Z95 * se, ci_hi=est + Z95 * se))
                if family == "state":
                    i1, i4 = members.index("R1"), members.index("R4")
                    w = np.zeros(len(members))
                    w[i1], w[i4] = 1.0, -1.0
                    est, se = _lin(b, V, w)
                    spreads.append(_spread(
                        sample, h, "four_state", "R1", "R4", means[i1], means[i4],
                        est, se, n_g[i1], n_g[i4], M_CLUSTER,
                        "水平差 mean(R1) − mean(R4)",
                        t=est / se, ci_lo=est - Z95 * se, ci_hi=est + Z95 * se))
            # ---- 随机时点：每个 h 一次，1000 轮
            rb = random_block(P, pool, h, smask, M["event"], hours_n, hcode)
            rnd[(sample, h)] = rb
            for g, key, stat, note in (
                    ("random_all", "random_all_level", "level_mean",
                     GROUP_NOTE["random_all"] + "；报重抽分布的中位数与 [p5, p95]"),
                    ("random_all", "random_all_sig", "sig_mean",
                     "mean(d·y)：事件的方向 d 作用在**随机合约**的收益上"),
                    ("random_up", "random_up_level", "level_mean", GROUP_NOTE["random_up"]),
                    ("random_down", "random_down_level", "level_mean",
                     GROUP_NOTE["random_down"])):
                r = rb[key]
                rows.append(_row(sample, h, "random", g, stat, r["estimate"], r["se"],
                                 rb["n"], rb["n_pop"], rb["n_clusters"], M_RANDOM,
                                 ci_lo=r["p5"], ci_hi=r["p95"],
                                 p5=r["p5"], p95=r["p95"], t_nan=True,
                                 note=note + "；" + str(EVENT.random_draws)
                                 + " 轮，se = 重抽 sd（Monte-Carlo，不是按合约聚类，"
                                   "不可与事件 SE 直接比）"))
            sp = rb["random_spread"]
            spreads.append(_spread(
                sample, h, "random", "random_up", "random_down",
                rb["random_up_level"]["estimate"], rb["random_down_level"]["estimate"],
                sp["estimate"], sp["se"], rb["n"], rb["n"], M_RANDOM,
                "同方向：上涨事件换成随机合约作多头、下跌事件换成随机合约作空头；"
                "中位数与 [p5, p95] 取自重抽分布",
                ci_lo=sp["p5"], ci_hi=sp["p95"], p5=sp["p5"], p95=sp["p95"]))
            log(f"  {sample} h={h:2d} 完成（随机基线 {rb['n']:,} 个事件，"
                f"c=1 的小时丢掉 {rb['n_drop']} 个）")
    return {"rows": rows, "spreads": spreads, "random": rnd, "sat": sat, "did": did}


# ============================================================ 6. 表
BASE_COLS = ["sample", "h", "family", "group", "statistic", "estimate", "se", "t",
             "ci_lo", "ci_hi", "p5", "p95", "n", "n_pop", "n_clusters",
             "method", "unit", "note"]
SPREAD_COLS = ["sample", "h", "group", "leg_long", "leg_short", "mean_long", "mean_short",
               "estimate", "se", "t", "ci_lo", "ci_hi", "p5", "p95",
               "n_long", "n_short", "method", "unit", "note"]


def write_table(df: pd.DataFrame, name: str) -> None:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TBL_DIR / (name + ".parquet"), index=False)
    df.to_csv(TBL_DIR / (name + ".csv"), index=False, encoding="utf-8")
    log(f"写盘 {name}.parquet / .csv  （{len(df)} 行 × {df.shape[1]} 列）")


# ============================================================ 7. 闸门
class Gate:
    """逐项记录 PASS/FAIL；任一 FAIL → 退出码 1。"""

    def __init__(self, header: str) -> None:
        self.lines = [header]
        self.n_pass = 0
        self.n_fail = 0

    def _emit(self, ok: bool, body: str) -> None:
        self.n_pass += int(ok)
        self.n_fail += int(not ok)
        self.lines.append(f"  [{'PASS' if ok else 'FAIL'}] {body}")

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(title)

    def note(self, body: str) -> None:
        self.lines.append(f"        └ {body}")

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self._emit(bool(ok), label + (f"  [{detail}]" if detail else ""))

    def near(self, label: str, got: float, exp: float, tol: float = 1e-10,
             fmt: str = "%+.10f") -> None:
        dev = abs(float(got) - float(exp))
        self._emit(dev <= tol,
                   f"{label} = {fmt % float(got)}   期望 {fmt % float(exp)}   |Δ| {dev:.1e}")

    def count(self, label: str, got: int, exp: int) -> None:
        self._emit(int(got) == int(exp), f"{label} = {int(got):,}   期望 {exp:,}")

    def text(self, footer: str) -> str:
        total = self.n_pass + self.n_fail
        return ("\n".join(self.lines) + "\n\n"
                + f"闸门汇总：PASS {self.n_pass} / FAIL {self.n_fail}（共 {total} 项）\n"
                + footer + "\n")


def gate_pool(g: Gate, meta: dict, pool: dict) -> None:
    g.section("0. 数据源、池子与随机分层（SPEC §零 / §四；D14.3 的截尾口径）")
    g.count("标签表分区数", meta["n_lab_files"], 57)
    g.count("前向面板分区数", meta["n_fwd_files"], 58)
    g.count("标签表总行数", meta["n_label"], 7252717)
    g.count("label-ok 行数 = 去均值基", meta["n_lab_ok"], 7010789)
    g.count("池子行数", meta["n_pool"], 7010789)
    g.check("(hour, symbol) 唯一（全局键无重复）", meta["n_pool_uniq"] == meta["n_pool"],
            f"唯一键 {meta['n_pool_uniq']:,} / 行 {meta['n_pool']:,}")
    g.count("前向面板总行数", pool["n_fwd_rows"], 7252717)
    g.count("前向面板里落在池子外的行（excl_reason != ok）", pool["n_fwd_outside"], 241928)
    g.check("★ 随机分层：mkt_vol_state 在同一小时上唯一（层 = (hour, vol_state) ≡ hour）",
            meta["n_vs_conflict_hours"] == 0,
            f"同一小时内 vol_state 不唯一的小时 {meta['n_vs_conflict_hours']} 个")
    for h in HS:
        med = float(pool["n_per_hour"][h].median())
        nph = pool["n_per_hour"][h]
        g.check(f"★ h={h:2d} 去均值基：n_per_hour 中位数 ∈ [150, 200]（全市场每小时合约数）",
                150.0 <= med <= 200.0,
                f"中位数 {med:.0f}（min {int(nph.min())} / max {int(nph.max())} / "
                f"{nph.size:,} 个小时）；用事件子样本会得到 7")
        g.check(f"h={h:2d} ok_h 为真 ⟺ fwd 有限（去均值后 excess 有限）",
                bool(np.array_equal(np.isfinite(pool["exc"][h]), pool["ok"][h])),
                f"ok 真 {pool['n_ok_true'][h]:,} 行")
        g.check(f"h={h:2d} 截尾：阈值取自全池一次，池上被压 ≈ 名义 2%（±0.5pp）",
                abs(pool["share_clip"][h] - (EVENT.winsor_lower + 1.0 - EVENT.winsor_upper))
                < 0.005,
                f"被压 {pool['share_clip'][h]:.4%}；阈值 [{pool['lo'][h]:+.10f}, "
                f"{pool['hi'][h]:+.10f}]")
    back = json.loads(THR_PATH.read_text(encoding="utf-8"))
    g.near("h=24 的截尾下界与 winsor_thresholds.json 逐位相等", pool["lo"][H_MAIN],
           back["lo"], tol=0.0)
    g.near("h=24 的截尾上界与 winsor_thresholds.json 逐位相等", pool["hi"][H_MAIN],
           back["hi"], tol=0.0)
    g.count("json 的 n_pool 与本文件池子一致", back["n_pool"], meta["n_pool"])


def gate_align(g: Gate, align: dict, M: dict) -> None:
    g.section("1. ★★ 口径对齐 —— 现算的非事件行与事件表必须逐行相同")
    g.count("事件表行数", align["n_ev"], 923235)
    g.count("池里'双超阈'的行数（|price| > thr 且 |oi| > thr）",
            int(M["event"].sum()), 923235)
    g.count("事件表的行全部落在池子里", align["n_found"], 923235)
    g.check("事件位置无重复（事件表 (hour, symbol) 唯一）", align["n_dup_pos"] == 0,
            f"重复 {align['n_dup_pos']}")
    g.check("★ 池里'双超阈'的行 = 事件表的行（同一集合，按全局键逐个相等）",
            align["same_set"],
            f"交集 {align['n_found']:,} 行；集合相同 {align['same_set']}")
    g.count("事件行 regime 与标签表相同（0 处不一致）", align["n_reg_mismatch"], 0)
    exp_cmp = {1: 923210, 4: 923130, 8: 922995, 24: 921972}
    for h in HS:
        r = align["per_h"][h]
        g.near(f"★★ h={h:2d} winsor_fwd_{h}h 逐行相等（max|Δ| 必须为 0）", r["d_win"], 0.0,
               tol=0.0, fmt="%.3e")
        g.near(f"★  h={h:2d} excess_fwd_{h}h 逐行相等", r["d_exc"], 0.0, tol=0.0, fmt="%.3e")
        g.check(f"h={h:2d} ok_{h}h 逐行相同", r["ok_eq"], f"可比 {r['n_cmp']:,} 行")
        g.count(f"h={h:2d} 可比行数", r["n_cmp"], exp_cmp[h])
    g.note("对齐后事件行的因变量**原样取事件表的值**（来源是冻结产物）；"
           "max|Δ| = 0 说明现拼的非事件行与事件行在同一尺度上，"
           "四条基线与四状态事件才可比")


def gate_sample(g: Gate, meta: dict, M: dict, P: pd.DataFrame,
                tbl: pd.DataFrame) -> None:
    g.section("2. 样本量与 n_pop 锚点（v1 的实测底数 + config.py 的注释底数）")
    g.count("label-ok 全池", meta["n_pool"], 7010789)
    g.count("headline 的 ok 行数（config.py: 1,966,729 行 / 39,459 个时刻）",
            int(M["headline"].sum()), 1966729)
    g.count("事件行（双超阈）full", int(M["event"].sum()), 923235)
    g.count("事件行（双超阈）headline", int((M["event"] & M["headline"]).sum()), 256079)
    for sample, exp_p, exp_o in (("full", 2041947, 2001052),
                                 ("headline", 555012, 546440)):
        n_p = int(tbl[(tbl["sample"] == sample) & (tbl["group"] == "price_all")
                      & (tbl["statistic"] == "level_mean")]["n_pop"].iloc[0])
        n_o = int(tbl[(tbl["sample"] == sample) & (tbl["group"] == "oi_all")
                      & (tbl["statistic"] == "level_mean")]["n_pop"].iloc[0])
        g.count(f"{sample} 纯价格 n_pop（|price_change| > price_thr 的全部 ok 行）", n_p, exp_p)
        g.count(f"{sample} 纯 OI n_pop（|oi_change| > oi_thr 的全部 ok 行）", n_o, exp_o)
        g.check(f"{sample} 纯价格 n_pop = 向上 + 向下（每行恰好落一侧）",
                n_p == int(M["price_up"].sum() if sample == "full"
                           else (M["price_up"] & M["headline"]).sum())
                + int(M["price_down"].sum() if sample == "full"
                      else (M["price_down"] & M["headline"]).sum()),
                f"{n_p:,}")
    g.check("n_pop 与 h 无关（同一组在四个前向期上是同一批行）",
            bool((tbl.groupby(["sample", "group", "statistic"])["n_pop"].nunique() == 1).all()),
            "各组 n_pop 的 h 维度唯一值均为 1")
    ev = M["event"]
    n_pc0 = int(np.count_nonzero(P["pc"].to_numpy("float64")[ev] == 0.0))
    n_oc0 = int(np.count_nonzero(P["oc"].to_numpy("float64")[ev] == 0.0))
    g.check("事件行的 price_change / oi_change 都不为 0（方向符号没有 0 档）",
            n_pc0 == 0 and n_oc0 == 0,
            f"pc 为 0 的 {n_pc0} 行 / oc 为 0 的 {n_oc0} 行（事件行 {int(ev.sum()):,}）")
    sel = tbl[(tbl["sample"] == "headline") & (tbl["h"] == H_MAIN)]
    exp_n = {"price_all": 554489, "oi_all": 545915, "R1": 74875, "R2": 50519,
             "R3": 44585, "R4": 85828, "funding_low": 704775, "funding_mid": 1016987,
             "funding_high": 241621, "funding_extreme": 101932}
    for grp, want in exp_n.items():
        got = int(sel[(sel["group"] == grp) & (sel["statistic"] == "level_mean")]["n"].iloc[0])
        g.count(f"headline h=24 的 n：{grp}", got, want)
    ncls = int(sel[(sel["group"] == "R1") & (sel["statistic"] == "level_mean")]
               ["n_clusters"].iloc[0])
    g.count("headline h=24 事件行的聚类簇数（合约数）", ncls, 249)


def gate_funding(g: Gate, M: dict) -> None:
    g.section("3. funding 四档的 n 与覆盖（D12；extreme ⊂ high 是重叠不是分区）")
    exp = {"funding_low": (3217131, 705117), "funding_mid": (3104847, 1018121),
           "funding_high": (678187, 241821), "funding_extreme": (324054, 102018)}
    for grp, (n_full, n_head) in exp.items():
        m = M[grp]
        g.count(f"{grp} 的 n（full）", int(m.sum()), n_full)
        g.count(f"{grp} 的 n（headline）", int((m & M["headline"]).sum()), n_head)
    three = M["funding_low"] | M["funding_mid"] | M["funding_high"]
    g.count("三档合计（full）", int(three.sum()), 7000165)
    g.count("三档合计（headline）", int((three & M["headline"]).sum()), 1965059)
    cov = float(three.mean())
    g.check("★ 三档覆盖率 ≈ 99.85%（余 10,624 行无状态，D12 不补行）",
            abs(cov - 0.998485) < 1e-5,
            f"{cov:.4%}（ok 全集 7,010,789 行）；无状态行 {int((~three).sum()):,}")
    g.check("三档互斥（每行最多落一档）",
            int((M["funding_low"] & M["funding_mid"]).sum()) == 0
            and int((M["funding_low"] & M["funding_high"]).sum()) == 0
            and int((M["funding_mid"] & M["funding_high"]).sum()) == 0,
            "两两交集都是 0")
    ext, hig = M["funding_extreme"], M["funding_high"]
    g.check("★ extreme ⊂ high：extreme 里没有一行不在 high 里",
            int((ext & ~hig).sum()) == 0,
            f"extreme 与 high 的重叠 {int((ext & hig).sum()):,} 行"
            f"（= extreme 的全部；占 high 的 {float((ext & hig).sum()) / float(hig.sum()):.2%}）")
    g.check("high = (high 去掉 extreme) + extreme（high 的均值必须由三格分区给出）",
            int(hig.sum()) == int((hig & ~ext).sum()) + int(ext.sum()),
            f"{int(hig.sum()):,} = {int((hig & ~ext).sum()):,} + {int(ext.sum()):,}；"
            "用四个重叠哑变量做饱和回归会把 high 的系数变成 "
            f"{int((hig & ~ext).sum()):,} 那一格")


def gate_anchor(g: Gate, tbl: pd.DataFrame, res: dict) -> None:
    g.section("4. 锚点：与 confirmatory / descriptive_four_cell 逐位对齐 + 饱和回归自检")
    did = res["did"]
    g.near("四格 DiD = (R1−R2)−(R3−R4)（headline, h=24）", did["estimate"], 0.0006233910)
    g.near("DiD 的按合约 SE（confirmatory 的唯一 SE 锚点）", did["se"], 0.0004656142)
    g.near("b_Pq = DiD / 4", did["estimate"] / 4.0, 0.0001558478)
    exp_mean = {"R1": -0.0010994518, "R2": -0.0012829596,
                "R3": -0.0012693662, "R4": -0.0008294829}
    sel = tbl[(tbl["sample"] == "headline") & (tbl["h"] == H_MAIN)
              & (tbl["statistic"] == "level_mean")]
    for c, want in exp_mean.items():
        got = float(sel[sel["group"] == c]["estimate"].iloc[0])
        g.near(f"格均值 {c}（headline, h=24）与 descriptive_four_cell 相同", got, want)
    dev = max(abs(e - r) for _s, _h, _g, e, r in res["sat"])
    g.check("★ 饱和回归自检：每个系数 = 该组原始均值（差 < 1e-12）", dev < 1e-12,
            f"max|Δ| {dev:.1e}（{len(res['sat'])} 个 (样本, h, 组)）")
    g.count("饱和自检的个数 = 2 样本 × 4 h × 12 组（price 2 + oi 2 + funding 3 + "
            "extreme 1 + state 4）", len(res["sat"]), 96)


def gate_se(g: Gate, tbl: pd.DataFrame, spd: pd.DataFrame) -> None:
    g.section("5. ★★ SE 闸门 —— 每个估计量都有 SE，且 SE > 0（v1 的 NaN 不许重现）")
    est = tbl["estimate"].to_numpy("float64")
    se = tbl["se"].to_numpy("float64")
    n_bad_est = int(np.count_nonzero(~np.isfinite(est)))
    n_bad_se = int(np.count_nonzero(~(se > 0)))
    g.check("全表 estimate 有限", n_bad_est == 0, f"非有限 {n_bad_est} 行 / 共 {len(tbl)} 行")
    g.check("★★ 全表 se 有限且 > 0", n_bad_se == 0,
            f"se ≤ 0 或 NaN 的 {n_bad_se} 行；min se {float(np.min(se)):.3e}，"
            f"max se {float(np.max(se)):.3e}")
    fnd = tbl[tbl["family"] == "funding"]
    for stat in ("level_mean", "level_median"):
        sub = fnd[fnd["statistic"] == stat]
        bad = int(np.count_nonzero(~(sub["se"].to_numpy("float64") > 0)))
        g.check(f"funding 的 {stat}：每一档都有 SE 且 > 0（v1 三行 NaN 的那处）",
                bad == 0 and len(sub) > 0,
                f"{len(sub)} 行；min se {float(sub['se'].min()):.3e}；四档 = "
                + ", ".join(sorted(set(sub["group"].tolist()))))
    nan_t = tbl["t"].isna().to_numpy()
    is_rand = (tbl["family"] == "random").to_numpy()
    g.check("t 的 NaN 只出现在随机基线的行（4 行 × 8 个 (样本, h) = 32 行）",
            bool(np.array_equal(nan_t, is_rand)),
            f"t 为 NaN {int(nan_t.sum())} 行；随机行 {int(is_rand.sum())} 行")
    nan_pp = tbl["p5"].isna().to_numpy()
    g.check("p5/p95 的 NaN 只出现在非随机行（随机行必须给出 [p5, p95]）",
            bool(np.array_equal(nan_pp, ~is_rand)),
            f"p5 为 NaN {int(nan_pp.sum())} 行")
    rr = tbl[is_rand]
    inside = bool(((rr["p5"] <= rr["estimate"]) & (rr["estimate"] <= rr["p95"])).all())
    g.check("随机基线：p5 ≤ 估计量 ≤ p95（重抽区间含中位数）", inside,
            f"{len(rr)} 行全部满足")
    cnt = tbl.groupby(["sample", "h"]).size()
    exp = {(s, h): (30 if s == "headline" else 20) for s in SAMPLES for h in HS}
    g.check("★ 表行数 = 4 h × (headline 30 + full 20) = 200", len(tbl) == 200,
            " / ".join(f"{k[0]} h={k[1]}: {int(v)}" for k, v in cnt.items()))
    g.check("每个 (样本, h) 的格数符合预期（headline 30 / full 20）",
            all(int(cnt[(s, h)]) == exp[(s, h)] for s in SAMPLES for h in HS),
            f"共 {int(cnt.sum())} 行")
    miss = tbl[(tbl["sample"] == "full") & (tbl["statistic"] == "level_median")]
    head_med = tbl[(tbl["sample"] == "headline") & (tbl["statistic"] == "level_median")]
    g.check("中位数只在 headline 报：缺失集合恰好 = {sample=full} × {statistic=level_median}",
            len(miss) == 0 and len(head_med) == 40,
            f"full 的中位数 {len(miss)} 行（应为 0）/ headline 的 {len(head_med)} 行"
            f"（10 格 × 4 h）；full 的 funding 中位数要 477 秒/期，见文件头")
    n_bad_ci = int(np.count_nonzero(~np.isfinite(tbl["ci_lo"].to_numpy("float64"))))
    g.check("全表 ci_lo / ci_hi 有限（随机行给 [p5, p95]，其余给 ±1.96·SE）",
            n_bad_ci == 0, f"非有限 {n_bad_ci} 行 / 共 {len(tbl)} 行")
    sp_se = spd["se"].to_numpy("float64")
    g.check("★ 价差表 se 全部有限且 > 0", int(np.count_nonzero(~(sp_se > 0))) == 0,
            f"{len(spd)} 行；min se {float(np.min(sp_se)):.3e}")
    g.check("价差表 estimate 全部有限",
            int(np.count_nonzero(~np.isfinite(spd["estimate"].to_numpy("float64")))) == 0,
            f"{len(spd)} 行")


def gate_spread(g: Gate, spd: pd.DataFrame, tbl: pd.DataFrame) -> None:
    g.section("6. 五个价差（note §9）：行数、内部一致、与 level_mean 对齐")
    g.count("★ 价差行数 = 5 组 × 4 h × 2 样本", len(spd), 40)
    for grp in [s[0] for s in SPREADS]:
        n = len(spd[spd["group"] == grp])
        g.count(f"价差组 {grp} 的行数（4 h × 2 样本）", n, 8)
    dev, dev_rnd = 0.0, 0.0
    for _i, r in spd.iterrows():
        d = abs(float(r["estimate"]) - (float(r["mean_long"]) - float(r["mean_short"])))
        if r["group"] == "random":
            dev_rnd = max(dev_rnd, d)
        else:
            dev = max(dev, d)
    g.check("四个回归组的价差 = 多头均值 − 空头均值（差 < 1e-12）", dev < 1e-12,
            f"max|Δ| {dev:.1e}")
    g.note("随机组的价差是「每次重抽内先作差、再取中位数」，与「两个中位数之差」"
           "不是同一个数"
           f"（实测 |Δ| = {1e4 * dev_rnd:.4f}bp，这是中位数的非线性，不是 bug）")
    dev2 = 0.0
    for _i, r in spd.iterrows():
        for gname, col in ((r["leg_long"], "mean_long"), (r["leg_short"], "mean_short")):
            q = tbl[(tbl["sample"] == r["sample"]) & (tbl["h"] == r["h"])
                    & (tbl["group"] == gname) & (tbl["statistic"] == "level_mean")]
            dev2 = max(dev2, abs(float(r[col]) - float(q["estimate"].iloc[0])))
    g.check("价差两端 = 同一个 level_mean 行的估计量（差 < 1e-12）", dev2 < 1e-12,
            f"max|Δ| {dev2:.1e}")
    g.check("五组价差在两样本四个前向期上都齐全（无缺格）",
            set(spd["group"].unique()) == {s[0] for s in SPREADS}
            and set(spd["h"].unique()) == set(HS)
            and set(spd["sample"].unique()) == set(SAMPLES),
            f"组 {sorted(spd['group'].unique())}")


def gate_side_by_side(g: Gate, tbl: pd.DataFrame, spd: pd.DataFrame) -> None:
    g.section("7. 并排结果（只报数，不判定；bp = 1e-4，小数口径 ×1e4）")
    order = [s[0] for s in SPREADS]
    for sample in SAMPLES:
        for h in HS:
            g.lines.append(f"        [{sample} · h={h}] 五组多空价差（水平差，按合约聚类 SE）")
            for grp in order:
                r = spd[(spd["sample"] == sample) & (spd["h"] == h)
                        & (spd["group"] == grp)].iloc[0]
                tag = " (重抽中位数, 区间 = [p5,p95])" if grp == "random" else ""
                g.lines.append(
                    f"          {grp:<10s} {1e4 * r['estimate']:+8.3f}bp  "
                    f"se {1e4 * r['se']:7.3f}bp  "
                    f"区间 [{1e4 * r['ci_lo']:+8.3f}, {1e4 * r['ci_hi']:+8.3f}]bp  "
                    f"n {int(r['n_long']):>9,} / {int(r['n_short']):>9,}"
                    f"  ({r['leg_long']} − {r['leg_short']}){tag}")
    for sample in SAMPLES:
        g.lines.append(f"        [{sample} · h={H_MAIN}] 四条基线的水平（bp；均值 = "
                       f"按合约聚类 SE，中位数 = 按小时重抽 SD）")
        for grp in ("price_up", "price_down", "price_all", "oi_up", "oi_down", "oi_all",
                    "funding_low", "funding_mid", "funding_high", "funding_extreme",
                    "R1", "R2", "R3", "R4", "random_up", "random_down", "random_all"):
            q = tbl[(tbl["sample"] == sample) & (tbl["h"] == H_MAIN) & (tbl["group"] == grp)]
            m = q[q["statistic"] == "level_mean"].iloc[0]
            line = (f"          {grp:<17s} mean {1e4 * m['estimate']:+8.3f}  "
                    f"se {1e4 * m['se']:6.3f}  n {int(m['n']):>9,}  "
                    f"n_pop {int(m['n_pop']):>9,}")
            md = q[q["statistic"] == "level_median"]
            if len(md):
                md = md.iloc[0]
                line += f"   |  median {1e4 * md['estimate']:+8.3f}  se {1e4 * md['se']:6.3f}"
            sg = q[q["statistic"] == "sig_mean"]
            if len(sg):
                sg = sg.iloc[0]
                line += f"   |  sig(d·y) {1e4 * sg['estimate']:+8.3f}  se {1e4 * sg['se']:6.3f}"
            g.lines.append(line)


def gate_notes(g: Gate) -> None:
    g.section("8. 必须写进报告的边界（本表只报数，不做判定）")
    g.lines.append("        1. 本表是 note §13（四条基准并排）与 §9 的五组价差，属 "
                   "PHASE3_GUIDANCE 第二章的只报数表：**表里没有 p 值**；"
                   "t 列 = estimate / se，只是把 SE 换算成同一尺度，不构成判定。")
    g.lines.append("        2. 四状态能不能胜过 funding，是 Phase 4 的 4×4 网格要回答的；"
                   "本文件只能并排报数，答不了这个问题。")
    g.lines.append("        3. 随机基线的 se 是 1000 轮重抽的 sd（Monte-Carlo），不是按合约"
                   "聚类 SE —— 它衡量的是这一批随机合约的波动，不能与事件行的聚类 SE "
                   "直接比大小，要看中位数与 [p5, p95]。")
    g.lines.append("        4. funding 的 high（> p75）与 extreme（> p90）**重叠**：extreme "
                   "全部落在 high 里（324,054 行），四档不是分区。表里 high 的均值来自互斥"
                   "三格（low / mid / high），extreme 单独一格。")
    g.lines.append("        5. full 只作稳健性，且**不报中位数**（按小时重抽 7,000,165 行 × "
                   "1000 轮 = 477 秒/期，四个 h 是 32 分钟）；headline 的统计量齐全。")
    g.lines.append("        6. 单位：内部一律小数（D14.2）。表里 estimate 是小数"
                   "（如 −0.001011 = −10.11bp = −0.1011%）。")


# ============================================================ 9. main
def main() -> int:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    sym_index, P, pool_keys, meta = read_labels()
    fwd = read_forward(sym_index)
    meta["n_fwd_files"] = fwd["n_files"]
    pool = build_pool(P, pool_keys, fwd)
    del fwd
    M = build_masks(P)
    hours_uniq, hcode = np.unique(P["hour"].to_numpy(), return_inverse=True)
    log(f"池子的时间维度：{hours_uniq.size:,} 个小时（随机分层用）")
    align = align_events(P, pool, pool_keys, sym_index, M)

    gate = Gate("baselines_v2 · 实验 13（四条基准并排）+ 实验 8（五组价差）· "
                + time.strftime("%Y-%m-%d %H:%M:%S"))
    gate.lines.append("样本：label-ok 全池 7,010,789 行；headline = in_universe，"
                      "full = 全部 285 个合约（只作稳健性）。freq=" + FREQ + "，h = "
                      + str(HS) + "（主 " + str(H_MAIN) + "）")
    gate.lines.append("因变量：winsor_fwd_h（市场中性 + 全池 1%/99% 截尾，D13/D14.3；"
                      "事件行取自事件表，非事件行同一管线现拼）")
    gate.lines.append("推断：stats_core.cluster_se，**只按合约 symbol 聚类**（D17，"
                      "无小样本校正）；均值与 OLS 不重抽；中位数按小时有放回重抽 "
                      + str(EVENT.random_draws) + " 次（seed=" + str(EVENT.random_seed) + "）")
    gate.lines.append("单位：内部小数（D14.2）；×100 = 百分数、×1e4 = bp")

    gate_pool(gate, meta, pool)
    gate_align(gate, align, M)
    if gate.n_fail:
        txt = gate.text("口径与池子闸门未过 → 按纪律立刻停止，不产出表"
                        "（口径没对齐时往下算出来的任何数都是垃圾）")
        CHECKS_PATH.write_text(txt, encoding="utf-8")
        print(txt)
        log(f"闸门写盘 {CHECKS_PATH}（FAIL {gate.n_fail} 项，停止）")
        return 1

    res = estimate_all(P, pool, M, hours_uniq.size, hcode)
    tbl = pd.DataFrame(res["rows"])[BASE_COLS]
    spd = pd.DataFrame(res["spreads"])[SPREAD_COLS]
    # 表里 sample 的顺序 = SAMPLES（headline 在前），不按字母序（full 会跑到前面）
    rank = {s: i for i, s in enumerate(SAMPLES)}
    tbl = tbl.assign(_r=tbl["sample"].map(rank)) \
        .sort_values(["_r", "h", "family", "group", "statistic"], kind="stable") \
        .drop(columns="_r").reset_index(drop=True)
    spd = spd.assign(_r=spd["sample"].map(rank)) \
        .sort_values(["_r", "h", "group"], kind="stable") \
        .drop(columns="_r").reset_index(drop=True)

    gate_sample(gate, meta, M, P, tbl)
    gate_funding(gate, M)
    gate_anchor(gate, tbl, res)
    gate_se(gate, tbl, spd)
    gate_spread(gate, spd, tbl)
    write_table(tbl, "baselines_v2")
    write_table(spd, "baselines_spread")
    gate_side_by_side(gate, tbl, spd)
    gate_notes(gate)

    footer = (
        "口径出处：D13（市场中性 + 全池 1%/99% 截尾；headline 主样本）/ D14.2（小数）/ "
        "D14.3（截尾阈值取全市场 pool）/ D17（只按合约聚类）/ D12（funding 覆盖不满不补行）。\n"
        "与 v1 的差异：因变量换成 winsor（v1 是原始 fwd）、推断换成按合约（v1 双向）、"
        "funding 四档且带 SE（v1 三档、se_sig 全 NaN）、随机对照换成同刻随机合约"
        "（v1 是同合约随机时刻）；n_pop 锚点沿用 v1。\n"
        "本文件属 PHASE3_GUIDANCE 第二章的只报数七张表（§13 + §9）：表里不放 p 值，"
        "也不对四状态 vs funding 下任何结论（那是 Phase 4 的 4×4 网格）。")
    txt = gate.text(footer)
    CHECKS_PATH.write_text(txt, encoding="utf-8")
    print(txt)
    log(f"闸门写盘 {CHECKS_PATH}；耗时 {time.time() - T_START:.0f}s")
    return 0 if gate.n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
