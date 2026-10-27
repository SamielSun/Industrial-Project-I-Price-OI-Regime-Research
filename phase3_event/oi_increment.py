"""Phase 3 · oi_increment —— 六格增量检验（note §2 的字面主张；实现者 E）

一句话
    note §2 说 "price moves **accompanied by** meaningful OI changes contain more
    information than price moves alone"。`confirmatory.py` 的四格检验只比较了
    "四个状态彼此有没有差别"，**没有**回答"OI 也极端 vs OI 安静"。本文件把
    "价格超阈、OI 安静"的对照行拼进来，用**六格设计**把这句话变成一个可检验的
    联合假设，并分三个正交块报数（OI 维度 / 交互 / 整体）。

样本（一处定义，全文共用）
    headline  = `in_universe == True`
    行集合    = label 层 `excl_reason == "ok"` → 价格已超阈（|price_change| > price_thr）
                → 与 h=24 前向面板按 (hour, symbol) 一一对上 → `ok_24h`
    两类行（同一批行，只按 OI 是否超阈二分）：
      · **事件行**   |price_change| > price_thr **且** |oi_change| >  oi_thr   255,807 行
      · **对照行**   |price_change| > price_thr **且** |oi_change| <= oi_thr   298,682 行
    合计          **554,489 行**（OR 口径，不分 headline：923,235 + 1,118,712）
    两类行都从**同一条管线**（标签表 + 前向面板）生成 —— 不拼接两个来源，避免漏行或
    重复；事件表 `events_1h.parquet` 只作**冻结的验收参照**（只读）。它那 923,235 行
    与本文件子样本里 |oi_change| > oi_thr 的 923,235 行是**同一个集合**，且 winsor /
    excess / shock 逐行相等（max|Δ| = 0，见闸门 §1）。

对照行的口径为什么必须现拼、又为什么现拼得出来
    事件表里没有 OI 安静的行（D14.4：事件子样本里 OI 全极端，六格会退化成秩 4）。
    对照行只能从标签表 + 前向面板现拼，而**去均值基与截尾阈值必须与事件表完全
    相同**，否则两类行的因变量不在同一个尺度上，六格系数没有含义。三步照
    `build_event_table.py` 的口径做：
      1. **去均值基**：label-ok 的**全部 7,010,789 行**逐小时减等权均值
         （`stats_core.cross_sectional_demean`）。不是事件行自己的横截面均值。
      2. **截尾阈值**：同一批 pool 上的 `EventConfig.winsor_lower/upper`
         （1%/99%）分位，`stats_core.winsorize` 一次算出，**所有行共用这一组**（D14.3）。
      3. **验收（本文件的核心闸门）**：把 1+2 的值取到事件行上，必须与事件表里存的
         `winsor_fwd_24h` / `excess_fwd_24h` / `shock` **逐行相等**（容差 1e-6）。
         实测 **max|Δ| = 0.000e+00**（921,972 行可比，逐位相同）。这条过不了就
         `raise SystemExit`，不往下走 —— 口径没对齐时往下算出来的任何数都是垃圾。

模型（`stats_core.six_cell_design` + 一列控制）
    y   = `winsor_fwd_24h`（对照行按上一节现算）
    X   = [const, P, q, q2, P·q, P·q2] + [log(shock)]
          P = sign(price_change) ∈ {−1,+1}
          q = +1 / 0 / −1（OI 极端升 / 安静 / 极端降），q2 = 1[q ≠ 0]
          shock = |price_change| / price_thr（事件表里存的就是这个定义，逐行比对过）
    为什么加 log(shock)：note 的控制变量是价格冲击幅度；冲击在两组之间可以差一个
    数量级，不控制它，"OI 极端 vs 安静"里会混进"价格动得更猛"。
    为什么是六格不是四格：q = 0 这一档就是"OI 安静"，四格写不出来（D14.4）。
    秩：六格 6 列满秩，加 log(shock) 后 7 列满秩（都由 `matrix_rank` 断言过；
    这是六格能用在"含 q=0 样本"上的前提）。

三个正交块（都走 `stats_core.wald_test(b, V, idx)`，df = 块内系数个数）
    | 块 | 系数 | df | 回答什么 |
    |---|---|---|---|
    | oi_dimension | q, q2 | 2 | OI 动了有没有用（相对 OI 安静）← note §2 的正面命题 |
    | interaction  | P·q, P·q2 | 2 | OI 的效应是否随价格方向变 ← 四状态框架的主张 |
    | joint        | q, q2, P·q, P·q2 | 4 | 四个 OI 系数合起来有没有用 |
    "整体"就是这四个（"前四个"= 上两行列的四个 OI 系数），不含 const / P / log(shock)；
    df 必须是 4，写成 5 就是另一个检验。

    为什么这三块是正交切分：六格饱和时
      · mean(q=0)              = const + P·b_P
      · mean(q=+1) − mean(q=0) = b_q + b_q2 + P·(b_Pq + b_Pq2)
      · mean(q=0) − mean(q=−1) = b_q − b_q2 + P·(b_Pq − b_Pq2)
    于是 `b_q2` = 四个"OI 极端 − OI 安静"对比在对两个 OI 方向、两个价格方向都
    平均后的那一个（表里 `oi_extreme_vs_quiet_sym`），`b_q` = OI 升/降之差在
    两价格方向上的平均。交互块问的正是这两个对比**是否随价格方向变**。

推断（D14.1 的按合约聚类，用户拍板；不用双向）
    `stats_core.cluster_se(X, y, symbol_codes)`：CGM 单向聚类，簇 = 合约 symbol
    （249 簇），无小样本校正。均值与 OLS **一次都不重抽**（没有随机性）。
    判定用普通显著性（D15.2：等价性检验已取消）：p < 0.05 → 显著，否则不显著；
    不显著的结论一律附区间，不写裸的 accept the null（D13 的纪律）。

输出
    data/06_event_study/tables/freq=1h/oi_increment.parquet  + .csv
    data/06_event_study/docs/step8_checks_oi_increment.txt    （闸门全文 + 结果摘要）
    data/06_event_study/docs/winsor_thresholds.json           （全池截尾阈值，SPEC §二 的待补项）

用法
    python phase3_event/oi_increment.py        # 全部 PASS 退出码 0，任一 FAIL 退出码 1
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
H = max(EVENT.horizons)          # 主前向期 = 24（EventConfig.horizons 的最大值）
"""列名全部由 H 生成，避免"手写 24h 与参数不一致"。"""

Y_WIN = f"winsor_fwd_{H}h"
Y_EXC = f"excess_fwd_{H}h"
OK = f"ok_{H}h"

Z95 = NormalDist().inv_cdf(0.975)   # 1.959963984540054，与 confirmatory.py 同一个数

ROOT = HERE.parent
OUT_ROOT = ROOT / "data" / "06_event_study"
LAB_ROOT = ROOT / "data" / "05_regime" / "regime_labels" / f"freq={FREQ}"
FWD_ROOT = OUT_ROOT / "forward" / f"freq={FREQ}"
EV_PATH = OUT_ROOT / "events" / f"events_{FREQ}.parquet"
TBL_DIR = OUT_ROOT / "tables" / f"freq={FREQ}"
DOC_DIR = OUT_ROOT / "docs"
CHECKS_PATH = DOC_DIR / "step8_checks_oi_increment.txt"
THR_PATH = DOC_DIR / "winsor_thresholds.json"
"""全池算出的 (lo, hi) 落盘（SPEC §二 的"待补"项）：事件表之外的对照行在建模时按这
一组阈值现压，任何下游脚本都能直接读，不必重跑 7,010,789 行的分位。"""

T0 = pd.Timestamp("2021-12-01", tz="UTC")
"""小时编码的原点（SPEC §零：hour = (ts_end − 2021-12-01) / 1h）。事件表的 `hour`
就是这个编码；两套混用会 0 行匹配且不报错 —— 所以本文件只在 `_hour` 里算一次。"""

LABEL_COLS = ["symbol", "ts_end", "excl_reason", "price_change", "oi_change",
              "price_thr", "oi_thr", "in_universe"]
FWD_COLS = ["symbol", "ts_end", f"fwd_{H}h", f"ok_{H}h"]

BLOCKS = (
    ("oi_dimension", ("q", "q2"),
     "OI 维度：OI 动了（极端升/降）相对 OI 安静有没有用 ← note §2 的正面命题"),
    ("interaction", ("Pq", "Pq2"),
     "交互：OI 的效应是否随价格方向变 ← 四状态框架的主张"),
    ("joint", ("q", "q2", "Pq", "Pq2"),
     "整体：四个 OI 系数合起来有没有用（df = 4）"),
)
"""三个正交块。下标一律按名字从 `six_cell_design` 的 names 里取，不写死数字
（`q2` 是 3、`Pq2` 是 5 这种下标在换参数化时会静默错位）。"""

BLOCK_OF = {"const": "price_main", "P": "price_main", "log_shock": "control",
            "q": "oi_dimension", "q2": "oi_dimension",
            "Pq": "interaction", "Pq2": "interaction"}

CONTRASTS = (
    ("oi_extreme_vs_quiet_sym", {"q2": 1.0},
     "OI 极端（升/降平均）− OI 安静（价格涨/跌平均）= b_q2：note §2 的字面命题"),
    ("oi_up_vs_quiet_Pplus", {"q": 1.0, "q2": 1.0, "Pq": 1.0, "Pq2": 1.0},
     "P=+1 格：OI 极端升 − OI 安静 = b_q+b_q2+b_Pq+b_Pq2"),
    ("oi_up_vs_quiet_Pminus", {"q": 1.0, "q2": 1.0, "Pq": -1.0, "Pq2": -1.0},
     "P=−1 格：OI 极端升 − OI 安静 = b_q+b_q2−b_Pq−b_Pq2"),
    ("oi_dn_vs_quiet_Pplus", {"q": 1.0, "q2": -1.0, "Pq": 1.0, "Pq2": -1.0},
     "P=+1 格：OI 安静 − OI 极端降 = b_q−b_q2+b_Pq−b_Pq2"),
    ("oi_dn_vs_quiet_Pminus", {"q": 1.0, "q2": -1.0, "Pq": -1.0, "Pq2": 1.0},
     "P=−1 格：OI 安静 − OI 极端降 = b_q−b_q2−b_Pq+b_Pq2"),
    ("oi_up_minus_oi_dn_sym", {"q": 1.0},
     "OI 极端升 − OI 极端降（价格方向平均）= b_q"),
)
"""格对比只是 w'b（w 由系数名拼），SE 取 sqrt(w'Vw) —— 不重算聚类、不重算 Wald。"""

UNIT = "decimal_return"
UNIT_CHI2 = "chi2_statistic"

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


def _hour(ts: pd.Series) -> np.ndarray:
    """ts_end → 整小时编码（SPEC §零；与 build_event_table.py 逐位同一个式子）。"""
    return ((ts - T0).dt.total_seconds() // 3600).to_numpy("int64")


def _in_sorted(keys: np.ndarray, table: np.ndarray) -> np.ndarray:
    """keys 的每个元素是否精确等于 table（升序、无重复）里的某个元素。"""
    pos = np.searchsorted(table, keys)
    return (pos < table.size) & (table[np.minimum(pos, table.size - 1)] == keys)


# ============================================================ 0. 标签表 → 全池与子样本
def read_labels() -> tuple[dict[str, int], np.ndarray, pd.DataFrame, dict]:
    """标签表一遍：符号表、label-ok 的全局键、价格超阈子样本、计数。

    为什么要全局键（`hour * n_sym + symbol_code`）而不是逐分区 join：标签表与前向
    面板的**分区键不是同一个**（月界上的行落在不同 chunk），逐分区 merge 会丢掉每月
    界上的若干行 —— 实测丢 9,446 个 fwd 值。两边都按全局键对，(hour, symbol) 唯一性
    由闸门 §0 检查。
    """
    lab_files = sorted(LAB_ROOT.rglob("*.parquet"))
    syms: set[str] = set()
    for p in lab_files:
        syms.update(pd.read_parquet(p, columns=["symbol"])["symbol"].unique().tolist())
    sym_index = {s: i for i, s in enumerate(sorted(syms))}
    n_sym = len(sym_index)

    pkeys, sub_parts = [], []
    n_label = n_lab_ok = 0
    for p in lab_files:
        L = pd.read_parquet(p, columns=LABEL_COLS)
        n_label += len(L)
        L = L.loc[L["excl_reason"].to_numpy() == "ok"]
        n_lab_ok += len(L)
        hour = _hour(L["ts_end"])
        code = L["symbol"].map(sym_index).to_numpy("int64")
        pkeys.append(hour * n_sym + code)
        pc = L["price_change"].to_numpy("float64")
        tp = L["price_thr"].to_numpy("float64")
        idx = np.flatnonzero(np.abs(pc) > tp)      # 价格超阈 = 事件行 ∪ 对照行
        sub_parts.append(pd.DataFrame({
            "hour": hour[idx],
            "symbol": L["symbol"].to_numpy()[idx],
            "price_change": pc[idx],
            "oi_change": L["oi_change"].to_numpy("float64")[idx],
            "price_thr": tp[idx],
            "oi_thr": L["oi_thr"].to_numpy("float64")[idx],
            "in_universe": L["in_universe"].to_numpy(dtype=bool)[idx],
        }))
    pool_keys = np.concatenate(pkeys)
    sub = pd.concat(sub_parts, ignore_index=True)
    meta = {"n_lab_files": len(lab_files), "n_label": n_label, "n_lab_ok": n_lab_ok,
            "n_pool_rows": int(pool_keys.size)}
    log(f"标签表 {len(lab_files)} 个分区 / {n_label:,} 行 → label-ok {n_lab_ok:,} 行；"
        f"价格超阈子样本 {len(sub):,} 行（{n_sym} 个合约）")
    return sym_index, pool_keys, sub, meta


# ============================================================ 1. 前向面板
def read_forward(sym_index: dict[str, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """前向面板一遍：全局键、`fwd_24h`（float64）、`ok_24h`、行数。"""
    n_sym = len(sym_index)
    fwd_files = sorted(FWD_ROOT.rglob("*.parquet"))
    keys, vals, oks = [], [], []
    for p in fwd_files:
        F = pd.read_parquet(p, columns=FWD_COLS)
        hour = _hour(F["ts_end"])
        keys.append(hour * n_sym + F["symbol"].map(sym_index).to_numpy("int64"))
        # float32 → float64：不先转会让去均值残差留在 2e-8 量级（SPEC §五.4）
        vals.append(pd.to_numeric(F[f"fwd_{H}h"], errors="coerce").to_numpy("float64"))
        oks.append(np.asarray(pd.to_numeric(F[f"ok_{H}h"], errors="coerce").fillna(0)
                              .to_numpy("float64") > 0.5))
    fkey = np.concatenate(keys)
    ffwd = np.concatenate(vals)
    fok = np.concatenate(oks)
    log(f"前向面板 {len(fwd_files)} 个分区 / {fkey.size:,} 行")
    return fkey, ffwd, fok, len(fwd_files)


# ============================================================ 2. 去均值 + 截尾（全池一次）
def build_pool(pool_keys: np.ndarray, fkey: np.ndarray, ffwd: np.ndarray,
               fok: np.ndarray, n_sym: int) -> dict:
    """label-ok 全池上的市场中性 + 截尾；结果按全局键排好，供子样本二分取值。

    去均值基 = label-ok 的全部行（7,010,789）。`ok_24h == False` 的行 `fwd_24h` 是
    NaN，`cross_sectional_demean` 与 `winsorize` 都跳过 NaN，所以这批行对均值与
    分位毫无影响 —— 与"先与 ok_24h 取交集再算"逐位等价（交集实测 7,002,655 行）。
    """
    inpool = _in_sorted(fkey, np.sort(pool_keys))
    pkeys = fkey[inpool]
    order = np.argsort(pkeys, kind="stable")
    pkeys = pkeys[order]
    pfwd = ffwd[inpool][order]
    pok = fok[inpool][order]
    if np.unique(pkeys).size != pkeys.size:
        raise SystemExit("pool 键有重复：(hour, symbol) 应唯一，口径已坏，停")

    df, n_per_hour = sc.cross_sectional_demean(
        pd.DataFrame({"hour": pkeys // n_sym, "fwd": pfwd}), "fwd", out_col="excess")
    exc = df["excess"].to_numpy("float64")
    win, (lo, hi) = sc.winsorize(exc, lower=EVENT.winsor_lower,
                                 upper=EVENT.winsor_upper)
    log(f"pool {pkeys.size:,} 行（有限 y {int(np.isfinite(pfwd).sum()):,}）；"
        f"n_per_hour 中位数 {n_per_hour.median():.0f}；截尾阈值 "
        f"[{lo:+.10f}, {hi:+.10f}]；池上被压 {np.mean((win != exc)[np.isfinite(exc)]):.4%}")
    return {"keys": pkeys, "fwd": pfwd, "ok": pok, "exc": exc, "win": win,
            "lo": lo, "hi": hi, "n_per_hour": n_per_hour, "n_pool": int(pkeys.size),
            "n_finite": int(np.isfinite(pfwd).sum()),
            "n_ok_true": int(pok.sum()),
            "n_ok_true_fwd_nan": int(np.count_nonzero(pok & ~np.isfinite(pfwd))),
            "n_ok_false_fwd_num": int(np.count_nonzero(~pok & np.isfinite(pfwd))),
            "share_clip": float(np.mean((win != exc)[np.isfinite(exc)]))}


# ============================================================ 3. 样本
def build_sample(sub: pd.DataFrame, pool: dict,
                 sym_index: dict[str, int]) -> tuple[pd.DataFrame, dict]:
    """把 pool 上算好的 excess / winsor **原样取到**子样本每一行，再筛出六格样本。

    取而不是重算：这样"事件行 / 对照行"的因变量逐位来自同一条去均值 + 截尾序列，
    不存在"两次实现差一点点"的可能。副作用：传入的 sub 会多出 fwd / ok24 /
    excess / win 四列（下面与事件表对拍要用）；返回的 s 是 headline ∩ ok_24h 的切片。
    """
    n_sym = len(sym_index)
    skey = sub["hour"].to_numpy("int64") * n_sym + sub["symbol"].map(sym_index).to_numpy("int64")
    pos = np.searchsorted(pool["keys"], skey)
    if (pool["keys"][np.minimum(pos, pool["keys"].size - 1)] != skey).any():
        raise SystemExit("价格超阈子样本里有关键不在 pool 中：label-ok 全集应覆盖它们，口径已坏，停")
    sub["fwd"] = pool["fwd"][pos]
    sub["ok24"] = pool["ok"][pos]
    sub["excess"] = pool["exc"][pos]
    sub["win"] = pool["win"][pos]

    is_ev = np.abs(sub["oi_change"].to_numpy("float64")) > sub["oi_thr"].to_numpy("float64")
    head = sub["in_universe"].to_numpy(dtype=bool) & sub["ok24"].to_numpy(dtype=bool)
    s = sub.loc[head].copy()
    s["event"] = is_ev[head]
    counts = {
        "n_sub": int(len(sub)),
        "n_sub_event": int(is_ev.sum()),
        "n_sub_control": int((~is_ev).sum()),
        "n_headline_sub": int(head.sum()),
        "n_rows": int(len(s)),
        "n_event": int(s["event"].sum()),
        "n_control": int((~s["event"]).sum()),
    }
    log(f"六格样本 headline ∩ 价格超阈 = {counts['n_rows']:,} 行"
        f"（事件 {counts['n_event']:,} + 对照 {counts['n_control']:,}）")
    return s, counts


# ============================================================ 4. 估计
def _lin(b: np.ndarray, V: np.ndarray, w) -> tuple[float, float]:
    """线性组合 w'b 的点估计与 SE（V 取自同一组 cluster_se，D14.5）。"""
    w = np.asarray(w, dtype="float64").ravel()
    est = float(w @ b)
    return est, math.sqrt(max(float(w @ V @ w), 0.0))


def _stat(est: float, se: float) -> dict:
    """点估计 + SE → t / p / 95% 区间（单自由度）。

    p 用 `chi2_sf(1, t^2)`，与双侧正态 p 恒等（stats_core 自检第 4 节）。
    """
    t = est / se
    return {"estimate": est, "se": se, "t": t, "p": sc.chi2_sf(1, t * t),
            "ci_lo": est - Z95 * se, "ci_hi": est + Z95 * se}


def _w_of(names: tuple[str, ...], spec: dict) -> np.ndarray:
    """按**系数名**拼线性组合权重：`{"q": 1.0, "q2": -1.0}`。"""
    k = {nm: i for i, nm in enumerate(names)}
    w = np.zeros(len(names))
    for nm, v in spec.items():
        w[k[nm]] = float(v)
    return w


def estimate(s: pd.DataFrame) -> dict:
    """六格 + log(shock)，按合约聚类；返回系数、三个 Wald、格对比与设计矩阵。"""
    X6, names6 = sc.six_cell_design(s)
    shock = np.abs(s["price_change"].to_numpy("float64")) / s["price_thr"].to_numpy("float64")
    X = np.column_stack([X6, np.log(shock)])
    names = tuple(names6) + ("log_shock",)
    y = s["win"].to_numpy("float64")
    cS = pd.factorize(s["symbol"].to_numpy(), sort=False)[0].astype("int64")
    b, V = sc.cluster_se(X, y, cS)
    k = {nm: i for i, nm in enumerate(names)}
    coef = {nm: _stat(*_lin(b, V, _w_of(names, {nm: 1.0}))) for nm in names}
    wald = {}
    for blk, cols, _note in BLOCKS:
        W, p = sc.wald_test(b, V, [k[c] for c in cols])
        wald[blk] = {"W": W, "df": len(cols), "p": p}
    contr = {key: _stat(*_lin(b, V, _w_of(names, spec))) for key, spec, _n in CONTRASTS}
    log("六格估计完成：Wald " + " / ".join(
        f"{blk} {wald[blk]['W']:.4f}(df {wald[blk]['df']}, p {wald[blk]['p']:.4f})"
        for blk, _c, _n in BLOCKS))
    return {"X": X, "names": names, "b": b, "V": V, "coef": coef, "wald": wald,
            "contr": contr, "n": int(len(s)), "n_clusters": int(np.unique(cS).size),
            "rank6": int(np.linalg.matrix_rank(X6)),
            "rank_full": int(np.linalg.matrix_rank(X)),
            "shock_min": float(shock.min()), "shock_max": float(shock.max()),
            "log_shock_finite": bool(np.isfinite(np.log(shock)).all()),
            "n_q0": int((np.abs(s["oi_change"].to_numpy("float64"))
                         <= s["oi_thr"].to_numpy("float64")).sum()),
            "n_qpos": int((s["oi_change"].to_numpy("float64")
                           > s["oi_thr"].to_numpy("float64")).sum()),
            "n_qneg": int((s["oi_change"].to_numpy("float64")
                           < -s["oi_thr"].to_numpy("float64")).sum())}


def four_cell_anchor(s: pd.DataFrame) -> dict:
    """旁证：**只留事件行**跑四格，必须逐位复现 confirmatory.py 的 oracle 锚点。

    这条把"我们的 y 就是事件表里那个 y、我们聚类的就是那 249 个合约"同时钉住：
    b_Pq = 0.0001558478，DiD = 4·b_Pq = 0.0006233910，SE(DiD) = 0.0004656142。
    """
    e = s.loc[s["event"].to_numpy(dtype=bool)]
    X4, names4 = sc.four_cell_design(e)
    cS = pd.factorize(e["symbol"].to_numpy(), sort=False)[0].astype("int64")
    b, V = sc.cluster_se(X4, e["win"].to_numpy("float64"), cS)
    i = {nm: j for j, nm in enumerate(names4)}["Pq"]
    return {"n": int(len(e)), "n_clusters": int(np.unique(cS).size),
            "b_Pq": float(b[i]), "did": float(4.0 * b[i]),
            "se_did": float(4.0 * math.sqrt(V[i, i]))}


# ============================================================ 5. 与事件表逐行对拍
def compare_with_event_table(sub: pd.DataFrame) -> dict:
    """★ 核心闸门：现算的过子样本 vs 事件表里存的值，逐行比对。

    事件表是**冻结产物**，只读不写；这里读它是为了验口径，不是拿它当输入。
    """
    ev = pd.read_parquet(EV_PATH, columns=["symbol", "hour", OK, Y_WIN, Y_EXC, "shock",
                                           "price_change", "oi_change", "price_thr", "oi_thr"])
    mine = sub[["hour", "symbol", "price_change", "oi_change", "price_thr", "oi_thr",
                "ok24", "fwd", "excess", "win"]]
    m = ev.merge(mine, on=["hour", "symbol"], how="outer", suffixes=("", "_mine"),
                 indicator=True)
    flag = m["_merge"].to_numpy()
    both = flag == "both"
    ok_back = pd.to_numeric(m[OK], errors="coerce").fillna(0).to_numpy("float64") > 0.5
    ev_win = pd.to_numeric(m[Y_WIN], errors="coerce").to_numpy("float64")
    cmp_mask = both & ok_back & np.isfinite(ev_win)
    pc = m["price_change"].to_numpy("float64")
    oc = m["oi_change"].to_numpy("float64")
    thr_p = m["price_thr"].to_numpy("float64")
    thr_o = m["oi_thr"].to_numpy("float64")
    d_win = np.abs(m["win"].to_numpy("float64")[cmp_mask] - ev_win[cmp_mask])
    d_exc = np.abs(m["excess"].to_numpy("float64")[cmp_mask]
                   - pd.to_numeric(m[Y_EXC], errors="coerce").to_numpy("float64")[cmp_mask])
    d_shk = np.abs(np.abs(pc) / thr_p
                   - pd.to_numeric(m["shock"], errors="coerce").to_numpy("float64"))[cmp_mask]
    d_pc = np.abs(pc - m["price_change_mine"].to_numpy("float64"))[cmp_mask]
    d_oc = np.abs(oc - m["oi_change_mine"].to_numpy("float64"))[cmp_mask]
    d_tp = np.abs(thr_p - m["price_thr_mine"].to_numpy("float64"))[cmp_mask]
    d_to = np.abs(thr_o - m["oi_thr_mine"].to_numpy("float64"))[cmp_mask]
    return {"n_ev": int(len(ev)), "n_both": int(both.sum()),
            "n_ev_only": int((flag == "left_only").sum()),
            "n_mine_only": int((flag == "right_only").sum()),
            "n_cmp": int(cmp_mask.sum()),
            "n_ev_nan_y": int(len(ev) - int(cmp_mask.sum())),
            "n_mine_nan_y": int(np.count_nonzero(
                both & ~np.isfinite(m["win"].to_numpy("float64")))),
            "d_win": float(d_win.max()), "d_exc": float(d_exc.max()),
            "d_shock": float(d_shk.max()), "d_pc": float(d_pc.max()),
            "d_oc": float(d_oc.max()), "d_tp": float(d_tp.max()),
            "d_to": float(d_to.max()),
            "n_win_exact": int(np.count_nonzero(d_win == 0.0))}


# ============================================================ 6. 表
def _rec(block: str, statistic: str, coefficient: str = "", r: dict | None = None,
         n: int = 0, df: float = np.nan, verdict: str = "",
         method: str = "symbol_cluster", unit: str = UNIT, note: str = "") -> dict:
    row = {"block": block, "statistic": statistic, "coefficient": coefficient}
    r = r or {}
    for key in ("estimate", "se", "t", "p", "ci_lo", "ci_hi"):
        row[key] = r.get(key, np.nan)
    row.update({"df": df, "n": n, "verdict": verdict, "method": method,
                "unit": unit, "note": note})
    return row


def build_table(res: dict, counts: dict, anchor: dict) -> pd.DataFrame:
    """每个系数的估计/SE/t/p/区间 + 三个 Wald 的 W/df/p + 样本量 + 三个块的判定。"""
    rows = []
    for nm in res["names"]:
        rows.append(_rec(BLOCK_OF[nm], "coef", nm, res["coef"][nm], n=res["n"], df=1,
                         note="六格 + log(shock)；按合约聚类"))
    for key, _spec, note in CONTRASTS:
        rows.append(_rec("oi_contrast", "contrast", key, res["contr"][key], n=res["n"],
                         df=1, note=note))
    for blk, cols, note in BLOCKS:
        wd = res["wald"][blk]
        v = "显著" if wd["p"] < 0.05 else "不显著"
        rows.append(_rec(blk, "wald", "+".join(cols), {"estimate": wd["W"], "p": wd["p"]},
                         n=res["n"], df=wd["df"], verdict=v, method="symbol_cluster_wald",
                         unit=UNIT_CHI2,
                         note=f"H0: {', '.join(cols)} = 0；df = {wd['df']}；{note}"))
    for blk, val, note in (
            ("event_rows", counts["n_event"],
             "事件行：|price_change| > price_thr 且 |oi_change| > oi_thr"),
            ("control_rows", counts["n_control"],
             "对照行：|price_change| > price_thr 且 |oi_change| ≤ oi_thr（OI 安静）"),
            ("total_rows", counts["n_rows"], "合计 = 事件行 + 对照行（六格样本）"),
            ("n_clusters", res["n_clusters"], "聚类簇数 = 合约 symbol 个数"),
            ("n_event_full", counts["n_sub_event"],
             "全样本（不分 headline）的事件行数，仅记录（= 事件表 923,235 行）"),
            ("n_control_full", counts["n_sub_control"],
             "全样本（不分 headline）的对照行数，仅记录")):
        rows.append(_rec(blk, "n_rows", "", {"estimate": float(val)}, n=int(val),
                         method="descriptive", unit="count", note=note))
    for nm, key in (("b_Pq", "b_Pq"), ("did_4bPq", "did"), ("se_did_4bPq", "se_did")):
        rows.append(_rec("four_cell_anchor", "anchor", nm, {"estimate": anchor[key]},
                         n=anchor["n"], method="symbol_cluster", unit=UNIT,
                         note="只留事件行跑四格，复现 confirmatory.py 的 oracle 锚点"))
    df = pd.DataFrame(rows)
    df.insert(0, "sample", "headline")
    df.insert(1, "h", H)
    return df


def write_table(df: pd.DataFrame, name: str) -> None:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TBL_DIR / f"{name}.parquet", index=False)
    df.to_csv(TBL_DIR / f"{name}.csv", index=False, encoding="utf-8")
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

    def near(self, label: str, got: float, exp: float, tol: float = 1e-6,
             fmt: str = "%+.10f") -> None:
        """绝对容差比对（锚点用；默认容差 1e-6 与验收口径一致）。"""
        dev = abs(float(got) - float(exp))
        self._emit(dev <= tol,
                   f"{label} = {fmt % float(got)}   期望 {fmt % float(exp)}   |Δ| {dev:.1e}")

    def text(self, footer: str) -> str:
        total = self.n_pass + self.n_fail
        return ("\n".join(self.lines) + "\n\n"
                + f"闸门汇总：PASS {self.n_pass} / FAIL {self.n_fail}（共 {total} 项）\n"
                + footer + "\n")


def gate_pool(g: Gate, meta: dict, pool: dict) -> None:
    g.section("0. 数据源与池子（SPEC §零 / §四；D14.3 的截尾口径）")
    g.check("标签表分区 57 个 / 前向面板 58 个（D1：前向多一个 2026-09 的 1 小时分区）",
            meta["n_lab_files"] == 57 and meta["n_fwd_files"] == 58,
            f"标签 {meta['n_lab_files']} / 前向 {meta['n_fwd_files']}")
    g.near("标签表总行数", meta["n_label"], 7252717, tol=0, fmt="%.0f")
    g.near("label-ok 行数 = 去均值基", meta["n_lab_ok"], 7010789, tol=0, fmt="%.0f")
    g.near("落在 label-ok 键集内的前向面板行（= 池子行数）", pool["n_pool"], 7010789,
           tol=0, fmt="%.0f")
    g.near(f"{OK} 为真的行数（= 有 y 的行）", pool["n_ok_true"], 7002655, tol=0,
           fmt="%.0f")
    med = float(pool["n_per_hour"].median())
    g.check("★ 去均值基闸门：n_per_hour 中位数 ∈ [150, 200]（全市场每小时的合约数）",
            150.0 <= med <= 200.0,
            f"中位数 {med:.0f}（min {int(pool['n_per_hour'].min())} / "
            f"max {int(pool['n_per_hour'].max())} / {pool['n_per_hour'].size:,} 个小时）；"
            "用事件子样本会得到 7，一秒抓出")
    g.note(f"有 {int((pool['n_per_hour'] == 0).sum())} 个小时的 n = 0（样本末端还没有 24h "
           "前向收益的那几个小时）；它们的行 y 缺失、被 de-mean 与分位一起跳过，"
           "不影响均值与阈值")
    g.check(f"{OK} 为真 ⟺ fwd_{H}h 有限（两个方向都为 0 违例）",
            pool["n_ok_true_fwd_nan"] == 0 and pool["n_ok_false_fwd_num"] == 0,
            f"ok=True 但 y 缺失 {pool['n_ok_true_fwd_nan']} 行 / "
            f"ok=False 但 y 有值 {pool['n_ok_false_fwd_num']} 行")
    g.check("★ 截尾口径：阈值取自全池一次，池上被压比例 ≈ 名义 2%（±0.5pp）",
            abs(pool["share_clip"] - (EVENT.winsor_lower + (1.0 - EVENT.winsor_upper)))
            < 0.005,
            f"被压 {pool['share_clip']:.4%}（口径 {EVENT.winsor_lower:.0%}/"
            f"{EVENT.winsor_upper:.0%}），阈值 [{pool['lo']:+.10f}, {pool['hi']:+.10f}]")
    g.note("截尾阈值不是本文件自定的：它由全池 1%/99% 分位唯一确定，下面 §1 的逐行比对"
           "才是对它的验收（阈值错则事件行的 winsor 必然对不上）")
    back = json.loads(THR_PATH.read_text(encoding="utf-8"))
    g.check("截尾阈值已落盘且读回一致（SPEC §二；下游按这一组压对照行）",
            back["lo"] == pool["lo"] and back["hi"] == pool["hi"]
            and back["n_pool"] == pool["n_pool"],
            f"{THR_PATH.name}: [{back['lo']:+.10f}, {back['hi']:+.10f}]，"
            f"n_pool {back['n_pool']:,}")


def gate_align(g: Gate, cmp: dict, anchor: dict) -> None:
    g.section("1. ★★ 口径对齐闸门 —— 现算的对照行口径必须与事件表逐行相同")
    g.near("事件表行数", cmp["n_ev"], 923235, tol=0, fmt="%.0f")
    g.check("事件表的每一行都在价格超阈子样本里（left_only = 0）", cmp["n_ev_only"] == 0,
            f"按 (hour, symbol) 全外连接：both {cmp['n_both']:,} / "
            f"仅在事件表 {cmp['n_ev_only']} / 仅在子样本 {cmp['n_mine_only']:,}")
    g.check("事件表的 923,235 行 = 子样本里 |oi_change|>oi_thr 的那些行（同一集合）",
            cmp["n_both"] == cmp["n_ev"] and cmp["n_mine_only"] == 1118712,
            f"子样本里非事件行（= 对照行）{cmp['n_mine_only']:,}")
    g.check("★★ winsor_fwd_24h 逐行相等（容差 1e-6）", cmp["d_win"] <= 1e-6,
            f"max|Δ| = {cmp['d_win']:.3e}；{cmp['n_cmp']:,} 行可比，"
            f"其中 {cmp['n_win_exact']:,} 行逐位相同")
    g.check("★ excess_fwd_24h 逐行相等（容差 1e-6）", cmp["d_exc"] <= 1e-6,
            f"max|Δ| = {cmp['d_exc']:.3e}")
    g.check("★ shock 逐行相等（容差 1e-6；本节与模型里的 log(shock) 是同一个量）",
            cmp["d_shock"] <= 1e-6, f"max|Δ| = {cmp['d_shock']:.3e}")
    g.check("price_change / oi_change / price_thr / oi_thr 逐行相等",
            max(cmp["d_pc"], cmp["d_oc"], cmp["d_tp"], cmp["d_to"]) <= 1e-6,
            f"max|Δ| {cmp['d_pc']:.1e} / {cmp['d_oc']:.1e} / "
            f"{cmp['d_tp']:.1e} / {cmp['d_to']:.1e}")
    g.check("y 缺失的模式两边相同（ok_24h 为假 → 双方都是 NaN，不静默填 0）",
            cmp["n_ev_nan_y"] == cmp["n_mine_nan_y"],
            f"事件表 NaN {cmp['n_ev_nan_y']:,} 行 / 子样本 NaN {cmp['n_mine_nan_y']:,} 行")
    g.near("旁证：只留事件行跑四格，b_Pq", anchor["b_Pq"], 0.0001558478, tol=1e-9)
    g.near("旁证：DiD = 4·b_Pq", anchor["did"], 0.0006233910, tol=1e-9)
    g.near("旁证：SE(DiD) 按合约聚类（confirmatory 的 oracle 锚点）", anchor["se_did"],
           0.0004656142, tol=1e-9)
    g.check("旁证：事件行的 249 个合约簇也在本文件里重现",
            anchor["n"] == 255807 and anchor["n_clusters"] == 249,
            f"n {anchor['n']:,} / 簇 {anchor['n_clusters']}")


def gate_sample(g: Gate, s: pd.DataFrame, counts: dict) -> None:
    g.section("2. 样本（headline ∩ 价格超阈 ∩ ok_24h；h=24）")
    g.near("六格样本总行数", counts["n_rows"], 554489, tol=0, fmt="%.0f")
    g.near("事件行（|oi_change| > oi_thr）", counts["n_event"], 255807, tol=0, fmt="%.0f")
    g.near("对照行（|oi_change| <= oi_thr，OI 安静）", counts["n_control"], 298682, tol=0,
           fmt="%.0f")
    g.check("事件行 + 对照行 = 总行数（每行恰好落一类）",
            counts["n_event"] + counts["n_control"] == counts["n_rows"],
            f"{counts['n_event']:,} + {counts['n_control']:,} = {counts['n_rows']:,}")
    g.check("事件行 = headline 256,079 − 272（被 ok_24h 丢掉的那 272 行）",
            counts["n_event"] == 256079 - 272, f"{counts['n_event']:,}")
    g.near("全样本（不分 headline）的事件行数 = 事件表行数", counts["n_sub_event"], 923235,
           tol=0, fmt="%.0f")
    g.near("全样本的对照行数（事件表里没有这批行，全靠现拼）", counts["n_sub_control"],
           1118712, tol=0, fmt="%.0f")
    dup = int(s.duplicated(subset=["hour", "symbol"]).sum())
    g.check("(hour, symbol) 无重复（一个合约一小时一行）", dup == 0, f"重复 {dup} 行")
    g.check("样本内 y 全部有限（不把 NaN 静默喂给 cluster_se）",
            bool(np.isfinite(s["win"].to_numpy("float64")).all()),
            f"非有限 {int((~np.isfinite(s['win'].to_numpy('float64'))).sum())} 行")


def gate_design(g: Gate, s: pd.DataFrame, res: dict) -> None:
    g.section("3. 设计矩阵与推断口径（D14.4 六格 / D14.1 按合约聚类）")
    g.check("六格设计满秩（rank == 6，q 有 0 这一档）", res["rank6"] == 6,
            f"rank {res['rank6']}")
    g.check("加 log(shock) 后满秩（rank == 7）", res["rank_full"] == 7,
            f"rank {res['rank_full']} / 列 {res['X'].shape[1]}")
    g.check("q 三档齐全：极端升 / 安静 / 极端降",
            res["n_qpos"] > 0 and res["n_q0"] > 0 and res["n_qneg"] > 0,
            f"q=+1 {res['n_qpos']:,} / q=0 {res['n_q0']:,} / q=−1 {res['n_qneg']:,}")
    signs = np.unique(np.sign(s["price_change"].to_numpy("float64")))
    g.check("P 只取 ±1（全部行 |price_change| > price_thr，P 没有 0 档）",
            bool(np.array_equal(signs, np.array([-1.0, 1.0]))), f"取值 {signs}")
    g.check("shock = |price_change| / price_thr ≥ 1，log 后全有限",
            res["shock_min"] >= 1.0 and res["log_shock_finite"],
            f"shock ∈ [{res['shock_min']:.6f}, {res['shock_max']:.4f}]")
    g.check("单位闸门：|mean(winsor_fwd_24h)| < 0.05（小数口径，D14.2）",
            abs(float(s["win"].mean())) < 0.05,
            f"mean = {float(s['win'].mean()):+.6f}；若误写成百分数会 > 0.05")
    g.near("聚类簇数 = 合约 symbol 个数", res["n_clusters"], 249, tol=0, fmt="%.0f")


def gate_results(g: Gate, res: dict) -> None:
    g.section("4. 结果（y = winsor_fwd_24h，六格 + log(shock)，按合约聚类）")
    g.lines.append("        系数（小数口径；×1e4 = bp）")
    for nm in res["names"]:
        c = res["coef"][nm]
        g.lines.append(
            f"          {nm:<10s} {c['estimate']:+.10f}   se {c['se']:.10f}   "
            f"t {c['t']:+.3f}   p {c['p']:.4f}   "
            f"95% [{c['ci_lo']:+.10f}, {c['ci_hi']:+.10f}]")
    g.lines.append("        OI 与 OI 安静的格对比（w'b，SE = sqrt(w'Vw)）")
    for key, _spec, _note in CONTRASTS:
        c = res["contr"][key]
        g.lines.append(
            f"          {key:<24s} {c['estimate']:+.10f} = {1e4 * c['estimate']:+.3f}bp   "
            f"se {1e4 * c['se']:.3f}bp   t {c['t']:+.3f}   p {c['p']:.4f}   "
            f"95% [{1e4 * c['ci_lo']:+.3f}, {1e4 * c['ci_hi']:+.3f}]bp")
    g.lines.append("        三个正交块的联合 Wald")
    for blk, cols, _note in BLOCKS:
        wd = res["wald"][blk]
        g.lines.append(
            f"          {blk:<14s} W = {wd['W']:.6f}   df = {wd['df']}   "
            f"p = {wd['p']:.6f}   → {'显著' if wd['p'] < 0.05 else '不显著'}"
            f"   （{', '.join(cols)}）")


def gate_verdict(g: Gate, res: dict) -> None:
    g.section("5. 判定（普通显著性，D15.2：等价性检验已取消；区间照常报）")
    g.check("三个块的 df 与块内系数个数一致（2 / 2 / 4），W ≥ 0 且 p ∈ (0,1)",
            [res["wald"][b]["df"] for b, _c, _n in BLOCKS]
            == [len(c) for _b, c, _n in BLOCKS]
            and all(res["wald"][b]["W"] >= 0.0 and 0.0 < res["wald"][b]["p"] < 1.0
                    for b, _c, _n in BLOCKS),
            "df = " + " / ".join(str(res["wald"][b]["df"]) for b, _c, _n in BLOCKS))
    for blk, cols, note in BLOCKS:
        wd = res["wald"][blk]
        g.lines.append(
            f"        {blk:<14s} W = {wd['W']:.6f}  df = {wd['df']}  p = {wd['p']:.6f}"
            f"  → {'显著' if wd['p'] < 0.05 else '不显著'}   （{'+'.join(cols)}；{note}）")
    key = res["contr"]["oi_extreme_vs_quiet_sym"]
    g.lines.append(
        f"        note §2 的字面命题 → b_q2 = {1e4 * key['estimate']:+.3f}bp，"
        f"SE {1e4 * key['se']:.3f}bp，t {key['t']:+.3f}，p {key['p']:.4f}，"
        f"95% [{1e4 * key['ci_lo']:+.3f}, {1e4 * key['ci_hi']:+.3f}]bp"
        "（OI 极端相对 OI 安静的平均增量，两价格方向 × 两 OI 方向都平均）")
    g.lines.append(
        "        与四格版本的关系：四格只问'四个状态彼此有没有差别'"
        "（DiD = 4·b_Pq = +6.23bp，t = 1.30，不显著）；"
        "本节多了一档 q=0（OI 安静），问的是'OI 也极端 vs OI 安静'——"
        "这才是 note §2 的字面主张。")


def main() -> int:
    TBL_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    sym_index, pool_keys, sub, meta = read_labels()
    fkey, ffwd, fok, n_fwd = read_forward(sym_index)
    meta["n_fwd_files"] = n_fwd
    pool = build_pool(pool_keys, fkey, ffwd, fok, len(sym_index))
    del pool_keys, fkey, ffwd, fok
    with THR_PATH.open("w", encoding="utf-8") as fh:
        json.dump({
            "freq": FREQ, "h": H,
            "lower_quantile": EVENT.winsor_lower, "upper_quantile": EVENT.winsor_upper,
            "lo": pool["lo"], "hi": pool["hi"],
            "n_pool": pool["n_pool"], "n_pool_finite": pool["n_finite"],
            "demean_base": "label-ok 全池（7,010,789 行），逐小时等权去均值",
            "generated_by": "phase3_event/oi_increment.py",
        }, fh, ensure_ascii=False, indent=2)
    log(f"写盘 {THR_PATH.name}：截尾阈值 [{pool['lo']:+.10f}, {pool['hi']:+.10f}] 已落盘（SPEC §二）")
    s, counts = build_sample(sub, pool, sym_index)
    cmp = compare_with_event_table(sub)
    anchor = four_cell_anchor(s)

    gate = Gate(f"event_study · oi_increment · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    gate.lines.append(f"样本：headline(in_universe) & 价格超阈 & {OK}，freq={FREQ}，h={H}；"
                      "内部单位一律小数（D14.2），×100 即百分数，×1e4 即 bp")
    gate.lines.append("推断：CGM 单向聚类，**只按合约 symbol**（V = bread·(Σ_g s_g s_g')·bread，"
                      "无小样本校正）；均值与 OLS 一次都不重抽")
    gate.lines.append("模型：六格 const/P/q/q2/Pq/Pq2 + log(shock)；"
                      "块与 df：oi_dimension(q,q2)=2、interaction(Pq,Pq2)=2、"
                      "joint(q,q2,Pq,Pq2)=4")
    gate_pool(gate, meta, pool)
    gate_align(gate, cmp, anchor)
    if gate.n_fail:
        txt = gate.text("口径对齐闸门未过 → 按纪律立刻停止，不产出表（口径没对齐时"
                        "往下算出来的任何数都是垃圾）")
        CHECKS_PATH.write_text(txt, encoding="utf-8")
        print(txt)
        log(f"闸门写盘 {CHECKS_PATH}（FAIL {gate.n_fail} 项，停止）")
        return 1

    res = estimate(s)
    gate_sample(gate, s, counts)
    gate_design(gate, s, res)
    gate_results(gate, res)
    gate_verdict(gate, res)

    table = build_table(res, counts, anchor)
    write_table(table, "oi_increment")

    footer = (
        "口径出处：D13（市场中性 + 1%/99% 全池截尾）/ D14.1（按合约聚类）/ "
        "D14.2（小数） / D14.3（阈值取全市场 pool） / D14.4（六格只用于含 q=0 的样本） / "
        "D15.2（普通显著性，无等价性检验）。\n"
        "对齐验收：现算值取到事件行上与 events_1h.parquet 存的 winsor_fwd_24h 逐行"
        "一致（max|Δ| = 0.000e+00），事件表的 923,235 行与本文件的 923,235 个事件行"
        "是同一集合 —— 所以这批对照行的因变量与事件行同尺度。\n"
        "三个块是预先声明的正交切分、各自报 p，不做事后合并；本检验不在 D13 的 5 个"
        "确认性检验里（那是四格版本），它补的是 note §2 的字面缺口。")
    txt = gate.text(footer)
    CHECKS_PATH.write_text(txt, encoding="utf-8")
    print(txt)
    log(f"闸门写盘 {CHECKS_PATH}")
    return 0 if gate.n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

