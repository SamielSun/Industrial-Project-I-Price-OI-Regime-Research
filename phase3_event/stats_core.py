"""Phase 3 重建 · stats_core —— 统计基元（v3：解析聚类，只按合约）

`phase3_event/_rebuild/SPEC.md` 第一节定义的接口。v2 的全部确认性检验
（C1–C5、R2 匹配、R4 安慰剂）都建在它们上面，所以本文件只放**基元**：
不做实验、不读数据、不画图、不写盘。

| # | 函数 | 用在哪 |
|---|---|---|
| 1 | `cross_sectional_demean` | 市场中性（D13 第 1 条）＋"去均值基"闸门 |
| 2 | `winsorize` | 1%/99% 截尾（D13 第 2 条），阈值由全 pool 传入（D14.3） |
| 3 | `chi2_sf` | χ² 生存函数（环境没有 scipy） |
| 4 | `wald_test` | 联合 Wald（实验 1/3/4 的 χ²） |
| 5 | `cluster_se` | CGM 单向聚类协方差（**按合约 symbol**，主推断） |
| 6 | `four_cell_design` | 四格设计（实验 3/4，D14.4） |
| 7 | `six_cell_design` | 六格设计（实验 1，含 OI 安静对照） |
| 8 | `cell_medians_boot` | 格中位数的重抽分布（实验 2，D14.1 的中位数例外） |
| 9 | `overreaction_slope` | 逐格 log(shock) 斜率（实验 4 的描述层） |

另有一个**辅助**函数 `kurtosis`（不属于接口）：截尾闸门与自检都要用。

v3 删掉了 v2 的双向聚类（用户拍板，取代 D14.1 的推断基准）
----------------------------------------------------------
主结果**只按合约（symbol）聚类**，`two_way_se` 连同 `_one_way_vcov` /
`_pair_codes` 和它们那一节自检一起删掉，换成单维的 `cluster_se`。

理由（DiD 的 SE 分解实测）：iid **3.4368bp** / 按合约 **4.6561bp** / 双向
**4.8137bp** —— **按合约的 SE 已经是双向的 96.7%**：iid→双向 那 1.3769bp 的修正
里，1.2193bp（约 89%）来自合约维度，时刻维度只剩 0.1576bp（约 11%，把 SE 从
4.6561 抬到 4.8137，+3.4%）。而"同一个币的相邻事件前向窗口重叠"这句话答辩时能
直接讲，双向聚类（V_hour + V_symbol − V_交集）讲不清。

代价必须写进报告：**时刻维度的相关不再进入协方差**。中性化之后小时维度 lag24
自相关只剩 0.001（D14.1 实测），所以代价很小 —— 但**报告里不许再写"双向"**。

v2 删掉了 v1 的四个重抽函数（继续不回来）
----------------------------------------
`block_weights` / `boot_se` / `ols_boot` / `boot_median_se`（连同自检
`_t_block_weights` / `_t_boot_se` / `_t_ols_boot` / `_t_boot_median`）。
理由（D14.1）：市场中性化之后小时维度的 lag24 自相关只剩 **0.001**，48h block
bootstrap 只把 SE 放大 **1.04×**；真正剩下的是**合约维度 1.35×**，而 block
bootstrap 抓不到它。改成解析聚类之后，均值与 OLS 一次都不用重抽（连随机性都
没有），只有中位数还重抽（它没有解析标准误；按小时有放回、整小时带走）。

⚠️ 与 v1 的两处**破坏性签名变更**（调用方要跟着改）
---------------------------------------------------
* `cross_sectional_demean` 现在返回 `(df, n_per_hour)`（SPEC §1.1，去均值基
  闸门要用 `n_per_hour`）。旧写法
  `cross_sectional_demean(df, "fwd")["excess"]` 会抛 TypeError，
  改成 `cross_sectional_demean(df, "fwd")[0]["excess"]`。
  （`phase3_event/build_event_table.py:102` 就是这种旧写法。）
* `winsorize` 现在返回 `(压平后的数组, (lo, hi))`，且**没有** `by` 参数。
  SPEC §1.1 明令删除 `by`：按格内压会让 DiD 变成截尾规则的函数
  （实测 DiD 会变号：+2.30 → −1.74 → +0.78bp）。

单位（D14.2）
-------------
内部一律**小数**：`fwd_24h = 0.002235`，等价界限 10bp = **0.0010**（`EQUIV_BOUND`）。
表格输出才转百分数。自检第一节断言"点估计量级 `abs(mean) < 0.05`（小数）"，
并同时跑一遍百分之口径，证明这条闸门不是恒真。

对拍（不在自检里，需要真实数据）
-------------------------------
独立复算脚本 `phase3_event/_rebuild/_oracle_four_cell.py`（SE 分解）与
`_oracle_oneway.py`（按合约那一列）都不 import 本文件，在 headline / h=24 上
给出四格 DiD 的**按合约** SE = **4.656142e−4**（iid 的 1.3548×）。用本文件的
`four_cell_design + cluster_se + wald_test` 走同一口径能逐位复现 —— 这是"公式
没写错"的唯一硬证据（`confirmatory.py` 的闸门就钉这一个 SE 锚点）。

旧口径的双向 SE = 4.813743e−4、波动方程 χ²(3) = 137.321246 都是**双向**聚类
的产物，2026-10-27 起只作历史记录，不再是锚点。

自检：
    python phase3_event/stats_core.py
全部 PASS 退出码 0，任一 FAIL 退出码 1。自检只用合成数据，不读真实面板。
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # 断言失败的中文消息要能读

import config as cfg_mod  # noqa: E402

EVENT = cfg_mod.EVENT

# ---------------------------------------------------------------- 冻结常数
WINSOR_LOWER: float = EVENT.winsor_lower
WINSOR_UPPER: float = EVENT.winsor_upper
"""截尾分位（D13 冻结 1%/99%）。从 `EventConfig` 读，不在本文件写常数；
`build_event_table.py` 也是从这里 import 的，改了 config 两处同时变。"""

EQUIV_BOUND: float = 0.0010
"""等价界限 10bp，**小数**口径（D14.2 冻结）。任何拿它和百分数比的写法都是 bug，
而且不会报错——所以自检第一节专门验量级。"""

FOUR_CELL_NAMES: tuple[str, ...] = ("const", "P", "q", "Pq")
"""四格设计矩阵的列名（q ∈ {−1,+1}），顺序即列序（SPEC §1.3）。"""

SIX_CELL_NAMES: tuple[str, ...] = ("const", "P", "q", "q2", "Pq", "Pq2")
"""六格设计矩阵的列名（q ∈ {−1,0,+1}），顺序即列序（SPEC §1.3）。"""


# ============================================================ 1. 市场中性
def cross_sectional_demean(
    df: pd.DataFrame,
    value_col: str,
    hour_col: str = "hour",
    out_col: str = "excess",
) -> tuple[pd.DataFrame, pd.Series]:
    """逐小时横截面去均值（市场中性），并报告该 pool 每小时的合约数。

    语义
        对每一行，减去**该行所属小时**里 `value_col` 的等权均值。"等权" = 该小时
        的每个非缺失行各一票（不按成交额或 OI 加权）。共同因子占 24h 收益方差 35%，
        不去掉它，R4 的 +0.298% 里只有 +0.022% 是它自己的（D13 第 1 条）。

    ⚠️ 去均值的基必须是**全市场 pool**（7,010,789 行 / 每小时约 174 个合约），
    不是事件子样本（每小时 7.1 个）。两种做法的 DiD 差 44%。本函数不检查传进来的
    是谁——所以它把 `n_per_hour` 一起返回，让调用方和闸门都能立刻看出基数。

    参数
        df        含 `value_col` 与 `hour_col` 的 DataFrame。
        value_col 被去均值的列（收益 / 波动等，float）。
        hour_col  小时标识列。任意可比较的标量（本仓库里是 `hour`：
                  自 2021-12-01 起的整小时数）。
        out_col   结果列名。已存在则覆盖。

    返回
        `(df, n_per_hour)`：
        * `df` 是**同一个对象**（原地写入，不复制：事件表 923,235 × 73 列复制
          一次约 0.5 GB，而本函数只加一列），便于链式调用。
        * `n_per_hour` 是 `pd.Series`，索引 = 升序去重后的小时值，值 = 该小时
          参与去均值的**有效观测数**（NaN 不计）。全市场 pool 上其中位数 ≈ 174；
          拿事件子样本算会得到 7.1 —— `n_per_hour.median()` 就是那条闸门。

    缺失值
        `value_col` 是 NaN 的行：该行结果也是 NaN，且**不计入**该小时的均值
        （pandas `skipna=True` 语义）。整小时全缺失时该小时结果全 NaN，
        `n_per_hour` 在这一小时是 0。

    精度
        float64、单遍求和。收益量级（~1e-2）下组内均值残差约 1e-17。

    验收（SPEC §1.1 / §四）
        * `n_per_hour` 的中位数 ∈ [150, 200]（真实 pool 是 174）★★
        * 组均值为 0 是**定义**，不是验收项（v1 把它当验收，被接口评审判为恒真）。
    """
    x = df[value_col].to_numpy(dtype="float64")
    hours, code, n_grp = np.unique(
        df[hour_col].to_numpy(), return_inverse=True, return_counts=True
    )
    finite = np.isfinite(x)
    cnt = np.bincount(code, weights=finite.astype("float64"), minlength=n_grp.size)
    tot = np.bincount(code, weights=np.where(finite, x, 0.0), minlength=n_grp.size)
    mu = np.divide(tot, cnt, out=np.zeros(n_grp.size), where=cnt > 0)
    df[out_col] = x - mu[code]
    n_per_hour = pd.Series(
        cnt.astype("int64"), index=pd.Index(hours, name=hour_col), name="n"
    )
    return df, n_per_hour


# ============================================================ 2. 截尾
def winsorize(
    values,
    lower: float = WINSOR_LOWER,
    upper: float = WINSOR_UPPER,
    thresholds: tuple[float, float] | None = None,
) -> tuple[np.ndarray, tuple[float, float]]:
    """按分位截尾（winsorize）：把越界的值压到边界上，不删除观测。

    语义
        超出 `[lo, hi]` 的值被替换成相应的分位点，其余原样保留。**不剔除**行：
        改变样本量会把"极端小时"这个信息从分母里抹掉，而 D13 要的正是"保留极端
        小时、但不让它主导均值"。峰度 R1 111 / R4 503，不截尾时剔掉 1% 的小时就能
        让 R1 从 +0.2235 翻到 −0.1668（D13 第 2 条）。

    阈值（D14.3，这是本函数最重要的参数）
        `thresholds=None` 时按本次传入的 `values` 现算 1%/99% 分位；
        给定时**原样使用，不重算**。
        真实流程必须由调用方把**全市场 pool**（7,010,789 行）算出的那一组
        `(lo, hi)` 传进来，所有格、所有对照行共用同一组。理由：按格内截尾会让
        R1−R4 的 DiD **变号**（不压 +2.30bp / 全 pool 压 −1.74bp / 格内压 +0.78bp，
        跨方案差 4bp = 等价界限的 40%）。本函数**没有** `by` 参数，就是为了让
        "按格内压"这件事在签名上就写不出来。

    参数
        values      一维待截尾序列（list / ndarray / Series），转 float64。
        lower/upper 分位，默认 D13 的 1%/99%（从 `EventConfig` 读）。
        thresholds  外部传入的 `(lo, hi)`。给定时 `lower`/`upper` 被忽略。

    返回
        `(压平后的新数组, (lo, hi))`，与 `values` 等长；NaN 原样保留
        （不参与分位）。返回值里的阈值就是**实际用的那一组**，调用方要落盘到
        `data/06_event_study/docs/winsor_thresholds.json`（SPEC §二）。

    验收（SPEC §1.1 / §四）
        * 阈值由外部传入时逐元素等于 `np.clip(values, lo, hi)`，且不重算分位。
        * 换一组阈值（pool 的 0.5/99.5、1.5/98.5）→ DiD 变化 ≤ 0.5bp。★
        * 换成按格内压 → DiD 变化 > 0.5bp，且 > 上面那组的两倍。★（自检实测）
    """
    x = np.array(values, dtype="float64", copy=True)
    if thresholds is None:
        lo, hi = (float(v) for v in np.nanquantile(x, [lower, upper]))
    else:
        lo, hi = (float(thresholds[0]), float(thresholds[1]))
    return np.clip(x, lo, hi), (lo, hi)


# ============================================================ 3. χ² 生存函数
_ITMAX = 1000
_EPS = 1e-16
_FPMIN = 1e-300


def _gammainc_q(a: float, x: float) -> float:
    """正则化上不完全伽马 Q(a, x) = 1/Γ(a)·∫_x^∞ t^(a−1)e^(−t)dt。

    实现按 Numerical Recipes 6.2：`x < a+1` 走级数（算 P 再取 1−P），否则走
    连分式（直接算 Q）。两条分支在 `x = a+1` 附近重合（自检验证连续性）。
    a ≤ 0 或 x < 0 抛 ValueError；x = 0 返回 1.0。
    """
    if a <= 0.0:
        raise ValueError("不完全伽马的 a 必须 > 0（拿到 %r）" % (a,))
    if x < 0.0:
        raise ValueError(
            "不完全伽马的 x 必须 ≥ 0（拿到 %r）：χ² 统计量不可能为负；"
            "若来自 wald_test，说明 V 不是半正定（单向聚类的 CGM sandwich 本身"
            "半正定，负的 W 只可能来自别的口径的 V）" % (x,)
        )
    if x == 0.0:
        return 1.0
    lgn = math.lgamma(a)
    if x < a + 1.0:
        # 级数算 P(a,x)，再 Q = 1 − P
        ap, s = a, 1.0 / a
        d = s
        for _ in range(_ITMAX):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * _EPS:
                return 1.0 - s * math.exp(-x + a * math.log(x) - lgn)
        raise RuntimeError(
            "下不完全伽马的级数在 %d 次内没收敛（a=%r, x=%r）" % (_ITMAX, a, x)
        )
    # 连分式算 Q(a,x)
    b = x + 1.0 - a
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _ITMAX + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            return h * math.exp(-x + a * math.log(x) - lgn)
    raise RuntimeError(
        "上不完全伽马的连分式在 %d 次内没收敛（a=%r, x=%r）" % (_ITMAX, a, x)
    )


def chi2_sf(dof: float, x: float) -> float:
    """χ² 分布的生存函数 P(χ²_dof > x)，即右尾 p 值。

    环境里**没有 scipy**，所以自己实现：`chi2_sf(dof, x) = Q(dof/2, x/2)`，
    Q 是正则化上不完全伽马（见 `_gammainc_q`）。

    参数
        dof  自由度（> 0，可以是小数：Welch 型检验会用到）。
        x    统计量（≥ 0）。x < 0 抛 ValueError —— χ² 统计量不可能为负，而双向
             聚类的 CGM 协方差不是半正定，所以"负的 W"是真问题，不能静默给 p=1。

    返回
        float，∈ [0, 1]。x = 0 时恰好 1.0；x 极大时下溢到 0.0（不返回 NaN）。

    验收（SPEC §五，全部是解析可核的硬数字）
        * `chi2_sf(2, x) == exp(−x/2)` 到 1e-12（自由度 2 时 Q(1, x/2) = e^(−x/2)）
        * `chi2_sf(4, 9.488) ≈ 0.05` 到 1e-4
        * `chi2_sf(3, 7.815) ≈ 0.05`
        * x = a+1 两侧连续（级数 / 连分式切换处）
        * x < 0、dof ≤ 0 抛 ValueError
    """
    return _gammainc_q(float(dof) / 2.0, float(x) / 2.0)


# ============================================================ 4. 联合 Wald
def wald_test(b, V, idx) -> tuple[float, float]:
    """只挑 `idx` 指定系数做联合 Wald：`W = b_i' V_ii⁻¹ b_i`，`p = chi2_sf(len(idx), W)`。

    语义
        `W` 是"这组系数全为 0"的二次型统计量，自由度数 = **进入检验的系数个数**
        （= `len(idx)`，即约束数），不是模型的总系数个数。
        `V_ii` 取 `V` 的对应子块，用 `np.linalg.solve` 求逆二次型（不求显式逆）。

    ⚠️ **严禁把两个 t² 相加**（SPEC §三）：那样等于假设两个系数的协方差为 0。
    自检里的解析例 `b=(1,1)`、`V=[[1,.5],[.5,1]]` 给出 `W = 4/3`，而
    `t1²+t2² = 2` —— 差 50%，方向还是偏保守。

    参数
        b    系数向量，形状 `(k,)`（如 `four_cell_design` + `cluster_se` 的输出）。
        V    完整协方差矩阵，形状 `(k, k)`（聚类协方差是**矩阵**，不是标量 SE，
             所以 4 维联合区间、χ²(3) 才算得出来 —— D14.5）。
        idx  要检验的系数下标（int 序列）。按名字取系数由调用方负责：`names` 里
             找到名字再取下标，不要写死数字。

    返回
        `(W, p)`，两个 float。

    边界（会抛 ValueError，都是真问题而不是数值噪声）
        * `V_ii` 奇异（约束之间线性相关 → 自由度虚高）。
        * `W < 0`：负的二次型说明这个协方差块不能用（单向聚类的 V 半正定，
          出现负值就说明传进来的 V 不是同一口径的 CGM sandwich），必须报出来，
          不能给 p = 1 了事。

    验收（SPEC §三）
        单系数时与 `(b/se)²` 及其正态 p 值逐位一致；两维解析例 4/3；df = len(idx)。
    """
    b = np.asarray(b, dtype="float64").ravel()
    V = np.asarray(V, dtype="float64")
    idx = np.asarray(idx, dtype=np.intp).ravel()
    if V.shape != (b.size, b.size):
        raise ValueError("V 形状 %s 与 b 长度 %d 不匹配" % (V.shape, b.size))
    bs = b[idx]
    Vs = V[np.ix_(idx, idx)]
    rank_v = int(np.linalg.matrix_rank(Vs))
    if rank_v < idx.size:
        raise ValueError(
            "V_ii 秩亏（rank %d < %d）：这些约束线性相关，联合 Wald 的自由度会虚高"
            % (rank_v, idx.size)
        )
    W = float(bs @ np.linalg.solve(Vs, bs))
    if W < 0.0:
        raise ValueError(
            "W = %.6e < 0：单向聚类的 CGM sandwich 半正定，负的二次型说明传进来"
            "的 V 不是同一口径（或已破坏半正定），这个系数块的联合检验没有意义。"
            "先检查 V 的最小特征值 %.3e"
            % (W, float(np.linalg.eigvalsh(Vs).min()))
        )
    return W, chi2_sf(idx.size, W)


# ============================================================ 5. 聚类（按合约）
def cluster_se(X, y, cluster_codes) -> tuple[np.ndarray, np.ndarray]:
    """CGM 单向聚类（按合约 symbol）：返回点估计与**完整协方差矩阵**。

    公式
        `b = (X'X)⁻¹X'y`，残差 `u = y − Xb`，面包 `bread = (X'X)⁻¹`，
        簇得分和 `s_g = Σ_{i∈g} x_i u_i`，肉 `meat = Σ_g s_g s_g'`：

            V = (X'X)⁻¹ [Σ_g (X_g'e_g)(X_g'e_g)'] (X'X)⁻¹

    为什么只按合约聚类（用户拍板，取代 D14.1 的双向基准）
        DiD 的 SE 实测：iid **3.4368bp**、按合约 **4.6561bp**、双向 **4.8137bp**。
        按合约已经是双向的 **96.7%**；时刻维度只把 SE 抬 0.16bp（4.6561 → 4.8137，
        +3.4%），占 iid→双向 全部修正的 11%。而"同一个币的相邻事件前向窗口重叠"
        这句话答辩时能直接讲，双向聚类（V_hour + V_symbol − V_交集）讲不清。
        所以主结果只用这一维；v3 把双向聚类连同它的分量自检整个删掉。

        ⚠️ 代价：**时刻维度的相关不再进入协方差**。中性化之后小时维度的 lag24
        自相关只剩 0.001（D14.1 实测），所以代价很小 —— 但报告里只能写
        "按合约聚类"，不许再写"双向"。

    **没有小样本校正**（SPEC §1.2 的 CGM 形式；与 `_rebuild/_oracle_oneway.py`
    同一公式）。最大的修正是 symbol 维度的 G/(G−1) = 249/248，即 SE 差 0.20%。

    参数
        X             `(n, k)` 设计矩阵。**必须满秩**（四格/六格构造函数已断言），
                      否则 (X'X)⁻¹ 不存在 —— 这里直接抛 ValueError，不用 pinv 给
                      最小范数解（D14.4 的教训：lstsq 静默返回最小范数解）。
                      只适合**稠密的小 k**（四格/六格 + 几个控制变量）；上万列的
                      FE 哑变量不要塞进来（秩检查与求逆都是稠密的）。
        y             `(n,)` 因变量。
        cluster_codes `(n,)` 每行所属簇（本仓库里就是合约 `symbol`）。不必有序、
                      不必连续，可以是字符串。**至少 2 簇**：只有一簇时肉是一个
                      秩 1 矩阵，"簇内随便相关、簇间独立"这个假设没法检验，所以
                      直接抛 ValueError，而不是静默返回一个偏小的 SE。

    返回
        `(b, V)`：`b` 形状 `(k,)`，`V` 形状 `(k, k)`。单维聚类的肉是簇外积和，
        所以 `V` 对称且**半正定** —— 双向聚类那种"不保证半正定、W 可能为负"的
        病态在这里不存在。

    ⚠️ 与固定效应同用时的坑
        把 symbol 哑变量放进 `X` 再按 symbol 聚类，等于用一阶条件把簇内的得分
        和按构造清零，`V` 会退化成 0。正确做法是先做 within 变换再聚类，且检验
        只落在四格系数上。实验 3 的冻结口径是**不加任何固定效应**（D15.1），本
        函数不做 FE，也不做这个判断。

    验收（SPEC §1.2 / §四，自检第 6 节）
        * 点估计 = `np.linalg.lstsq`（1e-10）；`V` 形状 (k,k)、对称。
        * 与逐簇循环的独立实现逐元素一致（1e-12）。★
        * 簇内相关时 SE 明显大于 iid 的 HC0（≥ 1.2×，自检实测约 3.5×）。★
        * ★★ 给同一簇内所有行加公共冲击，`V` 必须随之变大（这才是"簇内相关被
          算进去"的直接证据；按行算的 SE 对这件事没有反应）。
        * 字符串簇标识与整数簇标识给出完全相同的 `b` 与 `V`。
        * X 秩亏、簇数 < 2 时抛 ValueError（不静默返回 0）。
    """
    X = np.asarray(X, dtype="float64")
    y = np.asarray(y, dtype="float64").ravel()
    n, k = X.shape
    if y.size != n:
        raise ValueError("y 长度 %d != X 行数 %d" % (y.size, n))
    rank = int(np.linalg.matrix_rank(X))
    if rank != k:
        raise ValueError(
            "X 秩亏：rank(X) = %d < %d 列，(X'X) 不可逆。设计矩阵的秩要由 "
            "four_cell_design / six_cell_design 的断言保证；真要用秩亏设计，"
            "系数的含义已经不唯一，联合 Wald 也没有意义" % (rank, k)
        )
    _, inv, cnt = np.unique(
        np.asarray(cluster_codes), return_inverse=True, return_counts=True
    )
    n_g = int(cnt.size)
    if n_g < 2:
        raise ValueError(
            "簇数 = %d < 2：单向聚类在一簇时肉是秩 1 矩阵，"
            "'簇内随便相关、簇间独立'这个假设没法检验。"
            "检查 cluster_codes 是不是传成了常数（真实数据里 symbol 应给出 249 簇）"
            % n_g
        )
    bread = np.linalg.inv(X.T @ X)
    b = bread @ (X.T @ y)
    u = y - X @ b
    meat = np.empty((n_g, k))
    for j in range(k):
        meat[:, j] = np.bincount(inv, weights=X[:, j] * u, minlength=n_g)
    V = bread @ (meat.T @ meat) @ bread
    return b, V


# ============================================================ 6-7. 设计矩阵
def _as_vector(df: pd.DataFrame, spec, n: int, label: str) -> np.ndarray:
    """列名 → 取列；标量 / 数组 → 广播。返回 float64 向量。"""
    if isinstance(spec, str):
        return np.asarray(df[spec], dtype="float64")
    v = np.asarray(spec, dtype="float64")
    if v.ndim == 0:
        return np.full(n, float(v))
    if v.size != n:
        raise ValueError("%s 给的是数组（长度 %d），与 df 的 %d 行不一致"
                         % (label, v.size, n))
    return v


def _price_oi_codes(
    df: pd.DataFrame, price_col: str, oi_col: str, thr_p, thr_o
) -> tuple[np.ndarray, np.ndarray]:
    """P = sign(price_change)，q = OI 三态（+1 / 0 / −1）。两个设计矩阵共用。"""
    n = len(df)
    pc = np.asarray(df[price_col], dtype="float64")
    tp = _as_vector(df, thr_p, n, "thr_p")
    oc = np.asarray(df[oi_col], dtype="float64")
    to = _as_vector(df, thr_o, n, "thr_o")
    n_bad = int(np.count_nonzero(np.abs(pc) <= tp))
    if n_bad:
        raise ValueError(
            "%d 行的 |%s| <= 门槛：设计矩阵只定义在'价格已超阈'的子样本上"
            "（否则 P 会多出 0 这个取值，四格变八格、六格变十格）。"
            "请先用门槛筛子样本" % (n_bad, price_col)
        )
    p = np.sign(pc)
    q = np.where(oc > to, 1.0, np.where(oc < -to, -1.0, 0.0))
    return p, q


def _assert_full_rank(X: np.ndarray, names: tuple[str, ...]) -> None:
    rank = int(np.linalg.matrix_rank(X))
    if rank != X.shape[1]:
        raise ValueError(
            "设计矩阵秩亏：rank(X) = %d != %d 列（%s）。秩亏时 lstsq 会静默返回"
            "最小范数解，系数不再是对应格子的对比 —— 这正是 D14.4 要求四格/六格"
            "分开、并且必须显式报错的原因" % (rank, X.shape[1], ", ".join(names))
        )


def four_cell_design(
    df: pd.DataFrame,
    price_col: str = "price_change",
    oi_col: str = "oi_change",
    thr_p="price_thr",
    thr_o="oi_thr",
) -> tuple[np.ndarray, tuple[str, ...]]:
    """四格设计矩阵：`const, P, q, P·q`，`q ∈ {−1,+1}`。

    语义
        P = sign(price_change) ∈ {−1,+1}；q = sign(oi_change) ∈ {−1,+1}。
        四格 = 2 × 2（价格符号 × OI 符号），设计满秩 4，所以 4 个格子的均值可以
        完全由系数还原。实验 3（波动）与实验 4（反转斜率）**只能**用这一版。

    为什么不能用六格
        事件子样本里 OI 全部"极端"，没有 q = 0 这一档，于是 `q² ≡ 1`、
        `P·q² ≡ P`，六格矩阵**秩只有 4**：六列的秩亏设计会让 lstsq 静默返回
        最小范数解，q2 的系数变成一个没有含义的数（D14.4）。所以这里既断言域
        （每行必须 |oi| > 门槛，即 q 真的只有 ±1），也断言 `matrix_rank == 4`。

    参数
        df        headline 事件行（价格、OI 都超阈）。
        price_col / oi_col  价格、OI 的变化量列。
        thr_p / thr_o       两条门槛：可以给**列名**（`price_thr` / `oi_thr`，
                    每行一个）、也可以给标量或等长数组。

    返回
        `(X, names)`：`X` 形状 `(n, 4)` float64，`names = FOUR_CELL_NAMES`。
        `X @ b` 给出四个格子的均值；调用方**按名字**取系数，不按下标。

    前置条件（会抛 ValueError）
        * 存在 `|price_change| <= price_thr` 的行（P 会多出 0 这一档）。
        * 存在 `|oi_change| <= oi_thr` 的行（q 会多出 0 这一档，说明这是"含 OI
          安静对照"的样本，该用 `six_cell_design`）。
        * 某一格没有观测（秩 < 4）。

    验收（SPEC §1.3）
        列名 `const,P,q,Pq`；`rank(X) == 4`；q ∈ {−1,+1}；每行恰好落在 1 格。
    """
    p, q = _price_oi_codes(df, price_col, oi_col, thr_p, thr_o)
    n_zero = int(np.count_nonzero(q == 0.0))
    if n_zero:
        raise ValueError(
            "%d 行的 |%s| <= %s：四格只定义在'OI 也超阈'的事件子样本上。含 OI 安静"
            "对照行的样本（实验 1）请用 six_cell_design" % (n_zero, oi_col, thr_o)
        )
    X = np.column_stack([np.ones(p.size), p, q, p * q])
    _assert_full_rank(X, FOUR_CELL_NAMES)
    return X, FOUR_CELL_NAMES


def six_cell_design(
    df: pd.DataFrame,
    price_col: str = "price_change",
    oi_col: str = "oi_change",
    thr_p="price_thr",
    thr_o="oi_thr",
) -> tuple[np.ndarray, tuple[str, ...]]:
    """六格设计矩阵：`const, P, q, q², P·q, P·q²`，`q ∈ {−1,0,+1}`。

    语义
        六格 = 价格符号(2) × OI 三态（极端降 / 安静 / 极端升）。
          q  = +1 若 oi_change >  +oi_thr    OI 极端升
               −1 若 oi_change <  −oi_thr    OI 极端降
                0 若 |oi_change| ≤ oi_thr     OI 安静
          q² = 1[q ≠ 0]
        实验 1 要看"OI 维度和交互"的 4 个系数，恰好就是 `q, q², P·q, P·q²`；
        `const` 与 `P` 是价格侧的主项，不进入 OI 的检验（取下标时用 names 找）。

        "任一行必须且只能落在一格里"由 q 的编码保证：`|oi_change| ≤ oi_thr` 一律
        记 0（只有一个安静格），严格大于/小于才记 ±1。价格恰好等于门槛也算
        "没超过"，与事件定义（"超过第 70 分位"）一致。

    参数 / 返回
        同 `four_cell_design`；`names = SIX_CELL_NAMES`。

    前置条件（会抛 ValueError）
        * 存在 `|price_change| <= price_thr` 的行（P 会多出 0 这一档 → 变成十格）。
        * **q 没有同时取到 −1 / 0 / +1**。最常见的触发方式是把事件子样本（OI 全
          极端）喂进来：那里秩只有 4，必须报错而不是静默退化（SPEC §1.3）。
        * 某一格没有观测（秩 < 6）。

    验收（SPEC §1.3）
        列名与 v1 一致（`const,P,q,q2,Pq,Pq2`，下游按名字取系数）；
        `rank(X) == 6`；q ∈ {−1,0,+1}；六格哑变量的张成空间 == X 的列空间。
    """
    p, q = _price_oi_codes(df, price_col, oi_col, thr_p, thr_o)
    if not np.any(q == 0.0):
        raise ValueError(
            "六格要求 q 同时取到 −1/0/+1，但 %d 行里没有一格 q = 0（OI 全部极端）。"
            "这就是事件子样本：六格在这里 q² ≡ 1、P·q² ≡ P，设计矩阵**秩只有 4**，"
            "lstsq 会静默返回最小范数解。实验 3/4 请用 four_cell_design；"
            "实验 1 要把'价格超阈、OI 安静'的对照行一起放进来" % len(df)
        )
    if not (np.any(q == 1.0) and np.any(q == -1.0)):
        raise ValueError(
            "六格要求 q 同时取到 −1/0/+1，当前只有 %s"
            % sorted(set(q.tolist()))
        )
    q2 = (q != 0.0).astype("float64")
    X = np.column_stack([np.ones(p.size), p, q, q2, p * q, p * q2])
    _assert_full_rank(X, SIX_CELL_NAMES)
    return X, SIX_CELL_NAMES


# ============================================================ 8. 中位数重抽
def cell_medians_boot(
    df: pd.DataFrame,
    value_col: str,
    group_col: str,
    hour_col: str,
    reps: int = EVENT.random_draws,
    seed: int = EVENT.random_seed,
) -> np.ndarray:
    """每个格子中位数的重抽分布：**按小时有放回重抽，整小时带走，不切块**。

    语义
        一次重抽 = 从 `n_hours` 个小时里有放回地抽 `n_hours` 个（i.i.d. 小时），
        把被抽中小时的**全部行整体**带走，再在每个格子里重算中位数。
        重复 `reps` 次 → 返回 `(reps, 格数)` 的分布。

        为什么按小时、不按行：同一小时的合约共享市场因子，按行重抽会把 n 个
        相关行当成 n 个独立观测，SE 会被低估（自检实测：整小时带走的 sd 是按行
        重抽的 2.6 倍）。
        为什么不切块（48h）：市场中性化之后小时维度的 lag24 自相关只剩 0.001
        （D14.1），块只会白白减少有效簇。

        为什么中位数还要重抽：它没有解析标准误，三明治公式给不出来（D14.1 的
        "中位数例外"）。

    ⚠️ 重抽共享（SPEC §零）
        `(reps, seed)` 只在这里抽一次，返回的 `(reps, 格数)` 矩阵里**所有格子
        共用同一组小时抽样**——所以格子之间的差、DiD 的分布都自带配对，不会把
        抽样噪声混进"均值与中位数的符号矛盾"里。不同调用之间只要 `seed` 与小时
        集合相同，抽到的小时序列也完全相同（`np.random.default_rng(seed)` 的
        确定性），所以多列因变量可以共享同一组重抽。

    参数
        df         含三列的数据框。
        value_col  因变量（如 `winsor_fwd_24h`），**必须全部有限**（NaN 会被排到
                   该格末尾、静默污染中位数，所以这里直接抛 ValueError）。
        group_col  格子标识列。返回的列序 = `np.unique(group_col)` 的升序。
        hour_col   小时标识列（重抽的单位）。
        reps       重抽次数，默认 `EventConfig.random_draws`（1000）。
        seed       随机种子，默认 `EventConfig.random_seed`。

    返回
        `(reps, n_groups)` 的 float64 数组。某次重抽若某格一行都没抽中
        （小样本才会发生），该次该格是 NaN —— 调用方要自己看见它，不要填 0。

    实现（为什么要写成这样）
        值先按 (格, 值) 排好序，于是每一格在数组里是连续一段、内部按值升序。
        一次重抽只需要：每行权重 `w`（= 它所属小时被抽中的次数）→ 全局累计
        `c = cumsum(w)` → 格内累计 = `c − 该格起点前的累计` → 在格内二分找
        第 ⌈T/2⌉ 与 ⌊T/2⌋+1 个次序统计量（加权中位数 = 这两个的平均）。
        单次重抽 O(n) 且只有一次 cumsum 加一次二分，**不是** `reps × n` 次中位数
        调用。实测 923,235 行 × 1000 次 ≈ **2 秒**（SPEC §六 的上限 10 秒）。

    验收（SPEC §1.2 / §四）
        * 形状 `(reps, 格数)`；同 seed 可复现；换 seed 会变。
        * 全量 923k 行 × 1000 次 ≤ 10 秒。★★
        * 给所有值加一个常数 → 分布方差**不变**（1e-12，中位数平移不变性）。
        * 给同一小时所有合约加公共冲击 → 分布方差**变**（≠1e-12）：这正是"整小时
          带走"与"按行重抽"的分界。★★
        * 整小时带走的 sd ≥ 2× 按行重抽的 sd（自检实测 2.6×）。
    """
    v = df[value_col].to_numpy(dtype="float64")
    n_bad = int(np.count_nonzero(~np.isfinite(v)))
    if n_bad:
        raise ValueError(
            "%s 有 %d 个非有限值：中位数重抽不做缺失处理（NaN 会被排到该格末尾并"
            "污染中位数）。调用方先按 ok 掩码筛子样本" % (value_col, n_bad)
        )
    g_lab, g = np.unique(df[group_col].to_numpy(), return_inverse=True)
    h_lab, h = np.unique(df[hour_col].to_numpy(), return_inverse=True)
    n_g, n_h = int(g_lab.size), int(h_lab.size)

    order = np.lexsort((v, g))  # 先按格、再按值升序：每格是连续一段且内部有序
    vs = v[order]
    hs = h[order].astype(np.intp)
    cnt = np.bincount(g[order], minlength=n_g)
    starts = np.concatenate(([0], np.cumsum(cnt)[:-1])).astype(np.intp)
    ends = (starts + cnt - 1).astype(np.intp)

    out = np.empty((reps, n_g))
    cbuf = np.empty(v.size, dtype="int32")  # 全局累计权重，逐次重抽复用
    rng = np.random.default_rng(seed)
    for r in range(reps):
        w_hour = np.bincount(rng.integers(0, n_h, n_h), minlength=n_h).astype("int32")
        wr = w_hour[hs]  # 每行权重 = 它那小时被抽中的次数
        np.cumsum(wr, dtype="int32", out=cbuf)
        for gi in range(n_g):
            s, e = int(starts[gi]), int(ends[gi])
            base = int(cbuf[s]) - int(wr[s])  # 该格第一行之前的累计
            tot = int(cbuf[e]) - base  # 该格的加权观测数
            if tot == 0:
                out[r, gi] = np.nan
                continue
            k1 = (tot + 1) // 2
            k2 = tot // 2 + 1
            # 手动指定 int32 针：int64 针会让 numpy 把整个 int32 切片先拷成 int64
            # （单次 searchsorted 从 6 微秒变 500 微秒，1000 次就是 4 毫秒对 2 秒）。
            j1 = s + int(np.searchsorted(cbuf[s:e + 1], np.int32(base + k1), side="left"))
            j2 = s + int(np.searchsorted(cbuf[s:e + 1], np.int32(base + k2), side="left"))
            out[r, gi] = 0.5 * (vs[j1] + vs[j2])
    return out


# ============================================================ 9. 过反应斜率
def overreaction_slope(
    df: pd.DataFrame,
    y_col: str,
    shock_col: str,
    group_col: str,
) -> tuple[np.ndarray, np.ndarray]:
    """每个格子估一条 `y = mu_c + theta_c · log(shock)`，返回各格斜率与标准误。

    语义
        实验 4 要问的是"价格冲击越大，之后回吐得越多吗？这个斜率随 OI 变不变"。
        对每个格子单独跑一次二变量 OLS（截距 + 斜率），`theta_c` 就是该格的
        "冲击幅度 → 收益"斜率。

        冲击用 log 而不是水平值：`shock = |price_change| / price_thr`，事件行的
        shock ≥ 1，跨格子差一个数量级；取对数让"冲击翻倍"在不同量级上可比，也压住
        右尾。

    ⚠️ 本函数只给**描述层**的经典同方差标准误
        签名里没有 cluster 参数，所以这里不做聚类、不做重抽。实验 4 的
        **推断**（四个斜率是否相等）必须走另一条路：用四格的虚拟变量 ×
        `[1, log(shock)]` 拼 8 列设计矩阵，`cluster_se`（按合约）拿协方差，再用
        `wald_test` 检验"斜率差全为 0"。注意约束数是 **4 个斜率相等 → 3 个约束
        → χ²(3)**，不是 χ²(5)（那是六格的自由度）。

    参数
        df         含三列的数据框（事件行，或事件行 + 对照行）。
        y_col      因变量列（如 `winsor_fwd_24h`）。
        shock_col  冲击幅度列（如 `shock`），**必须 > 0**（要取 log）。
        group_col  分组列（如四格格号、或 regime）。

    返回
        `(theta, se)`，两个形状 `(n_groups,)` 的数组，**顺序 =
        `np.unique(group_col)` 的升序**（数字按大小、字符串按字典序）。调用方要
        对应回组名就自己调一次 `np.unique(df[group_col])`。

    边界
        * 每组至少 3 行：`n ≤ 2` 时残差自由度 ≤ 0，`se` 会是 inf/nan（不掩盖）。
        * 不做缺失值处理：`y_col` 与 `shock_col` 必须有限。
        * `shock_col <= 0` 时 log 得到 −inf/nan，斜率随之失效。
    """
    y = np.asarray(df[y_col], dtype="float64")
    ls = np.log(np.asarray(df[shock_col], dtype="float64"))
    _, inv, cnt = np.unique(np.asarray(df[group_col]), return_inverse=True,
                            return_counts=True)
    theta = np.empty(cnt.size)
    se = np.empty(cnt.size)
    for gi in range(cnt.size):
        sel = inv == gi
        x = ls[sel]
        yy = y[sel]
        X = np.column_stack([np.ones(x.size), x])
        b = np.linalg.lstsq(X, yy, rcond=None)[0]
        resid = yy - X @ b
        s2 = float(resid @ resid) / (x.size - 2)
        theta[gi] = b[1]
        se[gi] = float(np.sqrt(np.linalg.pinv(X.T @ X)[1, 1] * s2))
    return theta, se


# ============================================================ 辅助：峰度
def kurtosis(values, excess: bool = False) -> float:
    """峰度（辅助函数，不属于 SPEC 第一节的接口）。

    `excess=False` 给 Pearson 峰度（正态 ≈ 3）；`excess=True` 给超额峰度
    （正态 ≈ 0）。用总体矩（除以 n，不扣自由度）。截尾闸门与自检都要用。

    参数
        values  一维序列，NaN 被忽略。
    返回
        float；有效观测少于 2 个或方差为 0 时为 NaN。
    """
    x = np.asarray(values, dtype="float64")
    x = x[np.isfinite(x)]
    if x.size < 2:
        return float("nan")
    d = x - x.mean()
    m2 = float(np.mean(d ** 2))
    if m2 == 0.0:
        return float("nan")
    k = float(np.mean(d ** 4)) / m2 ** 2
    return k - 3.0 if excess else k


# ============================================================ 自检
class _Report:
    """自检的小记账器：逐条打印 PASS/FAIL，末尾汇总。"""

    def __init__(self) -> None:
        self.bad = 0
        self.total = 0

    def section(self, title: str) -> None:
        print("\n--- " + title)

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.total += 1
        self.bad += 0 if ok else 1
        tail = ("  [" + detail + "]") if detail else ""
        print("  [" + ("PASS" if ok else "FAIL") + "] " + label + tail)


def _t_units(rep: _Report) -> None:
    rep.section("0. 单位闸门 —— 内部一律小数（D14.2）")
    rng = np.random.default_rng(10)
    y = 0.002 + 0.02 * rng.normal(size=200_000)
    m = float(y.mean())
    rep.check("★ 小数口径：点估计算术均值 |mean| < 0.05",
              abs(m) < 0.05, "mean = %.6f（目标 ≈ 0.002）" % m)
    pct = 100.0 * y
    rep.check("★ 同一批数据写成百分数必然违规（闸门能失败）",
              abs(float(pct.mean())) > 0.05,
              "mean(x100) = %.4f > 0.05" % float(pct.mean()))
    rep.check("等价界限 10bp = 0.0010（小数），比量级闸门 0.05 小两个数量级",
              EQUIV_BOUND == 0.0010 and EQUIV_BOUND < 0.05 / 10,
              "EQUIV_BOUND = %.4f" % EQUIV_BOUND)


def _t_demean(rep: _Report) -> None:
    rep.section("1. cross_sectional_demean —— 逐小时等权去均值 + n_per_hour")
    rng = np.random.default_rng(11)
    n_hours, per_hour = 2_000, 174  # 复刻全市场 pool 的形状：174 个合约/小时
    n = n_hours * per_hour
    df = pd.DataFrame({
        "hour": np.repeat(np.arange(n_hours), per_hour),
        "fwd": (0.002 + 0.02 * rng.normal(size=n)
                + np.repeat(0.01 * rng.normal(size=n_hours), per_hour)),
    })
    raw = df["fwd"].to_numpy().copy()
    out, n_per_hour = cross_sectional_demean(df, "fwd", out_col="excess")
    med = float(n_per_hour.median())
    rep.check("★★ n_per_hour 中位数 = 174（SPEC 第四节 闸门 [150,200]，不是 7）",
              150.0 <= med <= 200.0 and med == 174.0,
              "中位数 %.1f，区间 [%d, %d]，小时数 %d"
              % (med, int(n_per_hour.min()), int(n_per_hour.max()), n_per_hour.size))
    rep.check("n_per_hour 之和 = 参与去均值的行数",
              int(n_per_hour.sum()) == n, "%d / %d" % (int(n_per_hour.sum()), n))
    rep.check("返回的是同一个 df 对象（原地写一列，923,235 行也不复制）", out is df)
    rep.check("原列未被改写", bool(np.array_equal(df["fwd"].to_numpy(), raw)))
    g = float(out.groupby("hour", sort=False)["excess"].mean().abs().max())
    rep.check("按 hour 分组后 out_col 均值 = 0（定义，不是验收项）",
              g < 1e-12, "max|组均值| %.2e" % g)

    # 事件子样本：每小时只留 7 个合约（v1 的错误基数）
    keep = (np.arange(n_hours)[:, None] * per_hour + np.arange(7)[None, :]).ravel()
    _, n_ev = cross_sectional_demean(df.iloc[keep].copy(), "fwd", out_col="excess")
    med_ev = float(n_ev.median())
    rep.check("★ 换成'每小时 7 个合约'的事件子样本 → 中位数 7（闸门能失败）",
              med_ev == 7.0, "中位数 %.1f（全市场 pool 是 174）" % med_ev)

    hand = pd.DataFrame({"hour": [0, 0, 0], "fwd": [0.01, 0.01, 0.04]})
    h_out, _ = cross_sectional_demean(hand, "fwd", out_col="e")
    rep.check("等权均值：[0.01, 0.01, 0.04] → [−0.01, −0.01, +0.02]",
              bool(np.allclose(h_out["e"].to_numpy(), [-0.01, -0.01, 0.02],
                               atol=1e-15, rtol=0)),
              "max|偏差| %.1e" % float(np.abs(h_out["e"].to_numpy()
                                             - np.array([-0.01, -0.01, 0.02])).max()))

    df2 = pd.DataFrame({"hour": np.repeat(np.arange(40), 10), "v": rng.normal(size=400)})
    df2.loc[df2.index[::7], "v"] = np.nan
    out2, n2 = cross_sectional_demean(df2, "v", out_col="e")
    same_nan = bool((np.isnan(out2["e"].to_numpy()) == np.isnan(df2["v"].to_numpy())).all())
    g2 = float(out2.groupby("hour", sort=False)["e"].mean().abs().max())
    rep.check("NaN 行的结果仍是 NaN，且不进均值、不进 n_per_hour",
              same_nan and g2 < 1e-12 and int(n2.sum()) == int(np.isfinite(df2["v"]).sum()),
              "NaN 行 %d，max|组均值| %.1e，n 合计 %d"
              % (int(np.isnan(out2["e"].to_numpy()).sum()), g2, int(n2.sum())))

    df3 = pd.DataFrame({"t": np.repeat(np.arange(3), 4), "v": np.arange(12.0)})
    out3, n3 = cross_sectional_demean(df3, "v", hour_col="t", out_col="e")
    rep.check("hour_col / out_col 可改，n_per_hour 的索引就是小时值",
              "e" in out3.columns and n3.index.name == "t"
              and bool((out3.groupby("t")["e"].mean().abs() < 1e-12).all()),
              "索引名 %s" % n3.index.name)


def _t_winsorize(rep: _Report) -> None:
    rep.section("2. winsorize —— 阈值可由外部传入，没有 by")
    import inspect

    rng = np.random.default_rng(12)
    x = rng.standard_t(3, size=200_000) * 0.01
    y, (lo, hi) = winsorize(x)
    k0, k1 = kurtosis(x), kurtosis(y)
    share = float(np.mean(y != x))
    rep.check("★ 压平后峰度必须比原来小", k1 < k0, "峰度 %.2f → %.2f" % (k0, k1))
    rep.check("★ 被压的比例 ≈ lower+upper（±0.5pp）", abs(share - 0.02) < 0.005,
              "实测 %.4f / 期望 0.0200" % share)
    rep.check("压到分位点上、不删观测",
              y.size == x.size and bool(np.isclose(y.min(), lo))
              and bool(np.isclose(y.max(), hi)),
              "范围 [%.4f, %.4f]" % (y.min(), y.max()))
    rep.check("返回的阈值就是实际用的那一组（可分位落盘复用）",
              bool(np.isclose(lo, np.nanquantile(x, WINSOR_LOWER)))
              and bool(np.isclose(hi, np.nanquantile(x, WINSOR_UPPER))),
              "(%.6f, %.6f)" % (lo, hi))

    lo2, hi2 = -0.02, 0.03
    y2, (lo_b, hi_b) = winsorize(x, thresholds=(lo2, hi2))
    rep.check("★ 外部传入阈值时原样使用、不再重算分位",
              (lo_b, hi_b) == (lo2, hi2)
              and bool(np.array_equal(y2, np.clip(x, lo2, hi2))),
              "阈值 (%.3f, %.3f)，逐元素等于 np.clip" % (lo_b, hi_b))
    rep.check("外部阈值传进来后 lower/upper 被忽略（signature 语义）",
              bool(np.array_equal(winsorize(x, 0.4, 0.6, (lo2, hi2))[0], y2)))
    rep.check("NaN 原样保留", bool(np.isnan(winsorize(np.array([0.0, np.nan]))[0][-1])))
    rep.check("★ 没有 by 参数（签名上就写不出'按格内压'）",
              "by" not in inspect.signature(winsorize).parameters,
              "参数：%s" % ", ".join(inspect.signature(winsorize).parameters))


def _t_winsorize_did(rep: _Report) -> None:
    rep.section("3. 截尾口径闸门 —— 换阈值 DiD 稳、按格内压会动（SPEC 第四节）")
    rng = np.random.default_rng(31)
    bulk = -0.0005 + 0.010 * rng.normal(size=200_000)  # 全市场 pool 的主体
    mu = (-0.0011, -0.0013, -0.0013, -0.0008)
    sd = (0.015, 0.020, 0.035, 0.060)  # R4 的尾部最肥（真实数据峰度 503）
    nu = 3.0
    cells = [
        mu[i] + sd[i] * rng.standard_t(nu, 25_000) / math.sqrt(nu / (nu - 2.0))
        for i in range(4)
    ]
    pool = np.concatenate([bulk] + cells)

    def did(cl):
        m = [float(c.mean()) for c in cl]
        return (m[0] - m[1]) - (m[2] - m[3])

    lo, hi = winsorize(pool)[1]  # 全 pool 算一次
    d_pool = did([winsorize(c, thresholds=(lo, hi))[0] for c in cells])
    d_raw = did(cells)
    alt = []
    for q in ((0.005, 0.995), (0.015, 0.985)):
        lo_a, hi_a = (float(v) for v in np.quantile(pool, q))
        alt.append(
            abs(did([winsorize(c, thresholds=(lo_a, hi_a))[0] for c in cells]) - d_pool)
        )
    d_cell = did([winsorize(c)[0] for c in cells])
    share_cell = [float(np.mean(winsorize(c, thresholds=(lo, hi))[0] != c))
                  for c in cells]

    # ⚠️ 单位：闸门写的是 "0.5bp"，小数口径下就是 5e-5。拿 0.5 直接比小数是 D14.2
    # 点名的那个 bug（不报错、永远 PASS），所以这里先把一切换算成 bp 再比。
    BP = 1e-4
    alt_bp = [v / BP for v in alt]
    d_cell_bp = abs(d_cell - d_pool) / BP

    rep.check("★ 换一组 pool 阈值（0.5/99.5、1.5/98.5）→ DiD 变化 ≤ 0.5bp",
              max(alt_bp) <= 0.5,
              "变化 %.3f / %.3f bp（DiD 本体 %.2f bp，不压 %.2f bp）"
              % (alt_bp[0], alt_bp[1], 1e4 * d_pool, 1e4 * d_raw))
    rep.check("★ 换成按格内压 → DiD 变化 > 0.5bp，且 > 上面那组的两倍",
              d_cell_bp > 0.5 and d_cell_bp > 2.0 * max(alt_bp),
              "变化 %.3f bp（pool 阈值换组只动 %.3f bp）" % (d_cell_bp, max(alt_bp)))
    rep.check("★ 同一组 pool 阈值下各格被压的比例差一个量级（真实数据：事件行 4.53%）",
              share_cell[3] > 0.05 and share_cell[3] > 3.0 * max(share_cell[:2]),
              "逐格 %s" % ["%.4f" % s for s in share_cell])


def _t_chi2(rep: _Report) -> None:
    rep.section("4. chi2_sf —— 自己实现的卡方生存函数（环境没有 scipy）")
    xs = (0.01, 0.5, 1.0, 3.0, 5.0, 10.0, 40.0)
    d2 = max(abs(chi2_sf(2, x) - math.exp(-0.5 * x)) for x in xs)
    rep.check("★★ chi2_sf(2, x) == exp(-x/2) 到 1e-12", d2 < 1e-12, "max|差| %.2e" % d2)
    v4 = chi2_sf(4, 9.488)
    rep.check("★ chi2_sf(4, 9.488) ≈ 0.05 到 1e-4", abs(v4 - 0.05) < 1e-4, "%.10f" % v4)
    v3 = chi2_sf(3, 7.815)
    rep.check("★ chi2_sf(3, 7.815) ≈ 0.05 到 1e-4", abs(v3 - 0.05) < 1e-4, "%.10f" % v3)
    tbl = ((1, 3.84146, 0.05), (5, 11.0705, 0.05), (10, 18.3070, 0.05),
           (24, 36.4150, 0.05), (100, 124.342, 0.05), (1, 1.0, 0.31731050786291415))
    worst = max(abs(chi2_sf(k, x) - p) for k, x, p in tbl)
    rep.check("标准表临界值（dof=1/5/10/24/100，以及卡方(1) 在 1 处的 p）",
              worst < 2e-5, "max|差| %.2e" % worst)
    cont = 0.0
    for dof in (2, 3, 4, 7, 20):
        a = dof / 2.0
        cont = max(cont, abs(chi2_sf(dof, 2 * a - 1e-9) - chi2_sf(dof, 2 * a + 1e-9)))
    rep.check("★ 级数/连分式切换处连续（x = 2a 两侧）", cont < 1e-6, "最大跳变 %.2e" % cont)
    rep.check("x = 0 时恰好 1.0；x 极大时下溢成 0.0 而不是 NaN",
              chi2_sf(4, 0.0) == 1.0 and chi2_sf(4, 200.0) < 1e-40
              and math.isfinite(chi2_sf(4, 200.0)),
              "chi2_sf(4, 200) = %.3e" % chi2_sf(4, 200.0))
    raised = []
    for args in ((-1.0, 1.0), (4.0, -0.001), (0.0, 1.0)):
        try:
            chi2_sf(*args)
            raised.append(False)
        except ValueError:
            raised.append(True)
    rep.check("★ x < 0 / dof <= 0 抛 ValueError（不静默给 p = 1）", all(raised), str(raised))
    rep.check("单调递减（p 值随统计量增大而变小）",
              all(chi2_sf(6, x1) > chi2_sf(6, x2)
                  for x1, x2 in ((0.5, 1.0), (1.0, 5.0), (5.0, 20.0))))


def _t_wald(rep: _Report) -> None:
    rep.section("5. wald_test —— 只挑 idx 的联合 Wald")
    b1 = np.array([0.001])
    V1 = np.array([[4e-8]])
    W1, p1 = wald_test(b1, V1, [0])
    t = 0.001 / 2e-4
    rep.check("★ 单系数：W = (b/se)^2", abs(W1 - t * t) < 1e-12,
              "W = %.6f / t^2 = %.6f" % (W1, t * t))
    rep.check("★ 单系数：p = 2Phi(-|t|)（用 math.erfc 独立算）",
              abs(p1 - math.erfc(abs(t) / math.sqrt(2.0))) < 1e-12,
              "p = %.12e" % p1)

    b2 = np.array([1.0, 1.0])
    V2 = np.array([[1.0, 0.5], [0.5, 1.0]])
    W2, p2 = wald_test(b2, V2, [0, 1])
    rep.check("★★ 两维解析例：W = b'V^-1 b = 4/3（手算），不等于 t1^2+t2^2 = 2",
              abs(W2 - 4.0 / 3.0) < 1e-12 and abs(W2 - 2.0) > 0.5,
              "W = %.12f，t1^2+t2^2 = 2（差 %.1f%%）" % (W2, 100 * (2.0 / W2 - 1.0)))
    rep.check("自由度 = len(idx)：p = chi2_sf(2, W)", abs(p2 - chi2_sf(2, W2)) < 1e-15,
              "p = %.12e" % p2)
    W_sub, _ = wald_test(b2, V2, [1])
    rep.check("只挑 idx 指定的系数（idx=[1] → W = 1）", abs(W_sub - 1.0) < 1e-12,
              "W = %.12f" % W_sub)
    W_big, p_big = wald_test(np.array([0.5, -0.2, 0.9]),
                             np.array([[1.0, 0.2, 0.1], [0.2, 1.0, 0.3], [0.1, 0.3, 1.0]]),
                             [0, 2])
    Vs = np.array([[1.0, 0.1], [0.1, 1.0]])
    W_ref = float(np.array([0.5, 0.9]) @ np.linalg.solve(Vs, np.array([0.5, 0.9])))
    rep.check("★ 子块取法（不连续下标）与手算一致",
              abs(W_big - W_ref) < 1e-12 and abs(p_big - chi2_sf(2, W_ref)) < 1e-15,
              "W = %.12f" % W_big)

    raised = 0
    try:  # 奇异子阵
        wald_test(np.array([1.0, 1.0]), np.array([[1.0, 1.0], [1.0, 1.0]]), [0, 1])
    except ValueError:
        raised += 1
    try:  # 非半正定 → 负的 W
        wald_test(np.array([1.0, 0.0]), np.array([[1.0, 2.0], [2.0, 1.0]]), [0, 1])
    except ValueError:
        raised += 1
    rep.check("★ V_ii 奇异、以及 CGM 不半正定导致 W < 0 时都抛 ValueError", raised == 2,
              "两种情况都报错（不静默给 p = 1）")


def _cluster_fixture(n_clusters=200, per=30, seed=15):
    """合约层面的回归元（簇内不变）+ b_true。真实数据的形状：格别/regime 在一个
    合约内高度持续，所以簇内相关会同时抬高所有系数的 SE。"""
    rng = np.random.default_rng(seed)
    n = n_clusters * per
    cc = np.repeat(np.arange(n_clusters), per)
    x1 = np.repeat(rng.normal(size=n_clusters), per)
    x2 = np.repeat(rng.integers(0, 2, n_clusters).astype("float64"), per)
    X = np.column_stack([np.ones(n), x1, x2])
    b_true = np.array([0.002, 0.001, -0.0005])
    return rng, X, b_true, cc, n, n_clusters, per


def _t_cluster(rep: _Report) -> None:
    rep.section("6. cluster_se —— CGM 单向聚类（按合约）")
    rng, X, b_true, cc, n, n_clusters, per = _cluster_fixture()
    y = X @ b_true + rng.normal(0, 0.01, n)
    b, V = cluster_se(X, y, cc)
    b_ref = np.linalg.lstsq(X, y, rcond=None)[0]
    rep.check("★ 点估计 = np.linalg.lstsq（1e-10）",
              bool(np.abs(b - b_ref).max() < 1e-10),
              "max|差| %.2e" % float(np.abs(b - b_ref).max()))
    rep.check("V 形状 (k,k) 且对称（相对 1e-12；矩阵乘法顺序会留下 1e-17 级的不对称）",
              V.shape == (3, 3)
              and float(np.abs(V - V.T).max()) <= 1e-12 * float(np.abs(V).max()),
              "max|V-V'| / max|V| = %.1e"
              % (float(np.abs(V - V.T).max()) / float(np.abs(V).max())))

    bread = np.linalg.inv(X.T @ X)

    def brute_vcov(X, u, codes, bread):
        """逐簇循环的独立实现：肉 = Σ_g s_g s_g'，不经 bincount。"""
        k = X.shape[1]
        meat = np.zeros((k, k))
        for g in np.unique(codes):
            s = (X[codes == g] * u[codes == g, None]).sum(axis=0)
            meat += np.outer(s, s)
        return bread @ meat @ bread

    u = y - X @ b
    V_ref = brute_vcov(X, u, cc, bread)
    rep.check("★★ 与独立实现（逐簇循环）的协方差矩阵一致（1e-12）",
              float(np.abs(V - V_ref).max()) < 1e-12,
              "max|差| %.2e" % float(np.abs(V - V_ref).max()))

    S = X * u[:, None]
    V_hc0 = bread @ (S.T @ S) @ bread
    ratio_0 = np.sqrt(np.diag(V)) / np.sqrt(np.diag(V_hc0))
    rep.check("★ iid 误差下 V ≈ HC0（簇内无相关时两种肉在估同一件事）",
              bool(np.all(ratio_0 > 0.85)) and bool(np.all(ratio_0 < 1.15)),
              "cluster/HC0 = %s" % np.array2string(ratio_0, precision=3))

    # 簇内相关的 DGP：同一合约的所有行共享一个冲击（真实数据的形状：
    # 一个 symbol 几百个事件、前向窗口大面积重叠）
    y_c = X @ b_true + rng.normal(0, 0.006, n_clusters)[cc] + rng.normal(0, 0.01, n)
    # 簇间冲击 sd 0.006 对簇内噪声 sd 0.01、每簇 30 行 → 理论放大
    # sqrt(30·0.006² / (0.006² + 0.01²)) ≈ 2.8 倍
    b_c, V_c = cluster_se(X, y_c, cc)
    S_c = X * (y_c - X @ b_c)[:, None]
    V_hc0_c = bread @ (S_c.T @ S_c) @ bread
    ratio_c = np.sqrt(np.diag(V_c)) / np.sqrt(np.diag(V_hc0_c))
    rep.check("★★ 簇内相关时按合约的 SE 明显大于 iid（≥ 1.2 倍，实测约 3 倍）",
              bool(np.all(ratio_c >= 1.2)),
              "cluster/HC0 = %s（%d 簇 × 每簇 %d 行）"
              % (np.array2string(ratio_c, precision=2), n_clusters, per))

    y_base = X @ b_true + rng.normal(0, 0.005, n)
    shock = np.repeat(rng.normal(0, 0.01, n_clusters), per)
    _, V_b = cluster_se(X, y_base, cc)
    _, V_s = cluster_se(X, y_base + shock, cc)
    rep.check("★★ 给同一簇内所有行加公共冲击 → V 必须随之变大",
              float(V_s[0, 0]) > 2.0 * float(V_b[0, 0]),
              "V[const] %.3e → %.3e（%.0f 倍）"
              % (V_b[0, 0], V_s[0, 0], V_s[0, 0] / V_b[0, 0]))

    eig = np.linalg.eigvalsh(V_c)
    rep.check("★ V 半正定（肉是簇外积和；双向聚类没有这个性质，W 可能为负）",
              float(eig.min()) >= -1e-10 * float(np.abs(V_c).max()),
              "最小特征值 %.3e（max|V| %.3e）" % (eig.min(), float(np.abs(V_c).max())))

    # 真实数据里 symbol 是字符串列（object dtype）：np.unique 必须能直接吃下去。
    s_str = np.array(["c%03d" % v for v in cc])
    b_obj, V_obj = cluster_se(X, y, s_str)
    rep.check("★★ 字符串（object dtype）簇标识与整数簇标识给出完全相同的 b 与 V",
              bool(np.array_equal(b_obj, b)) and bool(np.array_equal(V_obj, V)),
              "max|Δb| %.1e，max|ΔV| %.1e"
              % (float(np.abs(b_obj - b).max()), float(np.abs(V_obj - V).max())))

    msg = []
    try:
        cluster_se(np.column_stack([np.ones(n), np.ones(n)]), y, cc)
    except ValueError as e:
        msg.append(str(e).split("：")[0])
    try:
        cluster_se(X, y, np.zeros(n, dtype="int64"))
    except ValueError as e:
        msg.append(str(e).split("：")[0])
    rep.check("★ X 秩亏 / 簇数 < 2 都抛 ValueError（不静默返回 0）", len(msg) == 2,
              " / ".join(msg) if msg else "没有报错")


def _event_like_frame(rng, n_per_cell=600):
    rows = []
    for pc in (-2.0, 2.0):
        for oc in (-2.0, 2.0):
            rows.append((pc, oc, n_per_cell))
    return pd.concat([
        pd.DataFrame({"price_change": [pc] * k, "oi_change": [oc] * k,
                      "price_thr": 1.0, "oi_thr": 1.0,
                      "hour": rng.integers(0, 50, k)})
        for pc, oc, k in rows
    ], ignore_index=True)


def _t_four_cell(rep: _Report) -> None:
    rep.section("7. four_cell_design —— const, P, q, P*q（q 属于 {-1,+1}）")
    rng = np.random.default_rng(17)
    df = _event_like_frame(rng)
    X, names = four_cell_design(df)
    rep.check("★ 列名 = const, P, q, Pq", names == FOUR_CELL_NAMES, ", ".join(names))
    rep.check("形状 (n, 4)", X.shape == (len(df), 4), str(X.shape))
    p, q, pq = X[:, 1], X[:, 2], X[:, 3]
    rep.check("P 属于 {-1,+1}、q 属于 {-1,+1}",
              set(p.tolist()) == {-1.0, 1.0} and set(q.tolist()) == {-1.0, 1.0},
              "P %s / q %s" % (sorted(set(p.tolist())), sorted(set(q.tolist()))))
    rep.check("Pq = P*q 逐元素、const 全为 1",
              bool(np.array_equal(pq, p * q)) and bool(np.all(X[:, 0] == 1.0)))
    rep.check("★★ rank(X) = 4（D14.4 的硬断言）",
              int(np.linalg.matrix_rank(X)) == 4,
              "rank = %d" % int(np.linalg.matrix_rank(X)))
    cells = [(sv, ov) for sv in (1.0, -1.0) for ov in (1.0, -1.0)]
    D = np.column_stack([((p == sv) & (q == ov)).astype("float64") for sv, ov in cells])
    resid = float(np.abs(D - X @ np.linalg.lstsq(X, D, rcond=None)[0]).max())
    rep.check("任一行恰好落在 1 格，四格均值可由 X 完全还原（定义）",
              resid < 1e-12 and bool(np.all(D.sum(axis=1) == 1.0))
              and bool(np.all(D.sum(axis=0) == 600.0)),
              "max|残差| %.1e，每格 n = %s" % (resid, D.sum(axis=0).tolist()))

    bad = pd.concat([df, pd.DataFrame({"price_change": [2.0], "oi_change": [0.0],
                                       "price_thr": 1.0, "oi_thr": 1.0, "hour": [0]})],
                    ignore_index=True)
    msg = ""
    try:
        four_cell_design(bad)
    except ValueError as e:
        msg = str(e)
    rep.check("★ 样本里出现 OI 安静行 → ValueError（提示改用六格）",
              "six_cell_design" in msg, msg.split("：")[0] if msg else "没有报错")
    msg2 = ""
    try:
        four_cell_design(pd.DataFrame({"price_change": [0.5], "oi_change": [2.0],
                                       "price_thr": 1.0, "oi_thr": 1.0}))
    except ValueError as e:
        msg2 = str(e)
    rep.check("价格未超阈 → ValueError", "价格已超阈" in msg2)
    dropped = df[~((df["price_change"] > 0) & (df["oi_change"] < 0))]
    msg3 = ""
    try:
        four_cell_design(dropped)
    except ValueError as e:
        msg3 = str(e)
    rep.check("★ 某一格没有观测 → 秩亏 ValueError（不静默返回秩 3 的解）",
              "秩亏" in msg3, msg3.split("：")[0] if msg3 else "没有报错")


def _t_six_cell(rep: _Report) -> None:
    rep.section("8. six_cell_design —— 列名不变，加秩断言与域断言")
    rows = []
    for pc in (-2.0, 2.0):
        for oc in (-2.0, 0.0, 2.0):
            rows.extend([{"price_change": pc, "oi_change": oc,
                          "price_thr": 1.0, "oi_thr": 1.0}] * 3)
    df = pd.DataFrame(rows)
    X, names = six_cell_design(df)
    rep.check("★ 列名与 v1 完全一致（下游按名字取系数）",
              names == SIX_CELL_NAMES, ", ".join(names))
    rep.check("形状 (18, 6)", X.shape == (18, 6), str(X.shape))
    p, q, q2, pq, pq2 = X[:, 1], X[:, 2], X[:, 3], X[:, 4], X[:, 5]
    rep.check("q 属于 {-1,0,+1}、q2 = 1[q≠0]、Pq = P*q、Pq2 = P*q2",
              set(q.tolist()) == {-1.0, 0.0, 1.0}
              and bool(np.array_equal(q2, (q != 0).astype("float64")))
              and bool(np.array_equal(pq, p * q)) and bool(np.array_equal(pq2, p * q2)))
    cells = [(sv, ov) for sv in (1.0, -1.0) for ov in (1.0, 0.0, -1.0)]
    D = np.column_stack([((p == sv) & (q == ov)).astype("float64") for sv, ov in cells])
    resid = float(np.abs(D - X @ np.linalg.lstsq(X, D, rcond=None)[0]).max())
    rep.check("★★ rank(X) = 6，六格均值可由 X 完全还原",
              int(np.linalg.matrix_rank(X)) == 6 and resid < 1e-12,
              "rank = %d，max|残差| %.1e" % (int(np.linalg.matrix_rank(X)), resid))

    # 门槛边界：|oi| == thr 记"安静"，只超过一点点就算极端。这四行挂在完整的 2x3
    # 样本后面，才不破坏满秩。
    edge = pd.concat([df, pd.DataFrame({
        "price_change": [1.5, -1.5, 1.5, -1.5],
        "oi_change": [1.0, -1.0, 1.0000001, -1.0000001],
        "price_thr": 1.0, "oi_thr": 1.0})], ignore_index=True)
    Xe, _ = six_cell_design(edge)
    qe = Xe[-4:, 2].tolist()
    rep.check("|oi_change| == oi_thr 记'安静'，超过一点就算极端（q = 0, 0, 1, -1）",
              qe == [0.0, 0.0, 1.0, -1.0]
              and Xe[-4:, 3].tolist() == [0.0, 0.0, 1.0, 1.0],
              "边界四行 q = %s，q2 = %s" % (qe, Xe[-4:, 3].tolist()))

    msg = ""
    try:
        six_cell_design(df[df["oi_change"].abs() > 1.0])  # 事件子样本：OI 全极端
    except ValueError as e:
        msg = str(e)
    rep.check("★★ 事件子样本（OI 全极端）→ ValueError，指出秩只有 4 / 改用四格",
              ("秩只有 4" in msg) and ("four_cell_design" in msg),
              msg.split("。")[0][:70] if msg else "没有报错")
    msg2 = ""
    try:
        six_cell_design(pd.DataFrame({"price_change": [0.5], "oi_change": [2.0],
                                      "price_thr": 1.0, "oi_thr": 1.0}))
    except ValueError as e:
        msg2 = str(e)
    rep.check("价格未超阈 → ValueError（否则 P 多出 0 这一档，六格变十格）",
              "价格已超阈" in msg2)


def _t_median(rep: _Report) -> None:
    rep.section("9. cell_medians_boot —— 按小时有放回、整小时带走")
    rng = np.random.default_rng(19)
    n_hours, per = 400, 100
    n = n_hours * per
    hour = np.repeat(np.arange(n_hours), per)
    grp = np.tile(np.array(["A", "B"]), n // 2)
    base = 0.002 + 0.02 * rng.normal(size=n)
    shock = np.repeat(rng.normal(0, 0.01, n_hours), per)
    df = pd.DataFrame({"y": base, "g": grp, "h": hour})
    df_s = pd.DataFrame({"y": base + shock, "g": grp, "h": hour})
    df_c = pd.DataFrame({"y": base + 0.5, "g": grp, "h": hour})

    boot = cell_medians_boot(df, "y", "g", "h", reps=200, seed=7)
    rep.check("形状 (reps, 格数)，列序 = 组名的升序",
              boot.shape == (200, 2), str(boot.shape))
    pm = [float(np.median(base[grp == g])) for g in ("A", "B")]
    rel = [abs(boot[:, j].mean() - pm[j]) / abs(pm[j]) for j in range(2)]
    rep.check("★ 重抽均值 ≈ 点估计中位数（相对差 < 2%）",
              max(rel) < 0.02,
              "重抽均值 %s / 中位数 %s"
              % (np.array2string(boot.mean(axis=0), precision=6),
                 np.array2string(np.array(pm), precision=6)))
    rep.check("同 seed 可复现、换 seed 会变",
              bool(np.array_equal(boot, cell_medians_boot(df, "y", "g", "h", 200, 7)))
              and not bool(np.array_equal(boot,
                                          cell_medians_boot(df, "y", "g", "h", 200, 8))))

    boot_c = cell_medians_boot(df_c, "y", "g", "h", reps=200, seed=7)
    dev = float(np.abs(boot_c.var(axis=0, ddof=1) - boot.var(axis=0, ddof=1)).max())
    rep.check("★ 给所有值加常数 → 重抽分布方差不变（1e-12）", dev < 1e-12,
              "max|变化量| %.2e（中位数平移不变）" % dev)

    boot_s = cell_medians_boot(df_s, "y", "g", "h", reps=200, seed=7)
    ratio_v = boot_s.var(axis=0, ddof=1) / boot.var(axis=0, ddof=1)
    rep.check("★★ 给同一小时所有合约加公共冲击 → 方差变了（不是 1e-12 不变）",
              bool(np.all(np.abs(ratio_v - 1.0) > 0.01)),
              "方差比 %s" % np.array2string(ratio_v, precision=2))

    # 按行重抽（错误做法）作对照：同样的抽样次数
    rng2 = np.random.default_rng(7)
    yv = base + shock
    row_boot = np.empty((200, 2))
    for r in range(200):
        idx = rng2.integers(0, n, n)
        for j, g in enumerate(("A", "B")):
            row_boot[r, j] = np.median(yv[idx][grp[idx] == g])
    sd_hour = boot_s.std(axis=0, ddof=1)
    sd_row = row_boot.std(axis=0, ddof=1)
    rep.check("★★ 整小时带走的 sd >= 2 倍按行重抽的 sd（按行会把相关行当独立）",
              bool(np.all(sd_hour / sd_row > 2.0)),
              "整小时 [%.2e, %.2e] / 按行 [%.2e, %.2e] = %s"
              % (sd_hour[0], sd_hour[1], sd_row[0], sd_row[1],
                 np.array2string(sd_hour / sd_row, precision=2)))

    # 全量计时：923k 行 x 1000 次 <= 10 秒（SPEC 第六节）
    big_n_hours, big_per = 5_307, 174
    nb = big_n_hours * big_per
    big = pd.DataFrame({
        "y": 0.002 + 0.02 * rng.normal(size=nb),
        "g": np.tile(np.arange(4), nb // 4 + 1)[:nb],
        "h": np.repeat(np.arange(big_n_hours), big_per),
    })
    t0 = time.perf_counter()
    out = cell_medians_boot(big, "y", "g", "h")
    dt = time.perf_counter() - t0
    rep.check("★★ 全量 %d 行 x %d 次重抽 <= 10 秒（实测约 2 秒）"
              % (nb, EVENT.random_draws), dt <= 10.0,
              "%.2f s（%d 格）" % (dt, out.shape[1]))
    big_med = np.array([np.median(big["y"].to_numpy()[big["g"].to_numpy() == j])
                        for j in range(4)])
    rep.check("大样本上每格中位数与点估计一致（重抽均值相对差 < 1%）",
              bool(np.all(np.abs(out.mean(axis=0) / big_med - 1.0) < 0.01)),
              np.array2string(out.mean(axis=0), precision=6))
    raised = False
    try:
        cell_medians_boot(df.assign(y=np.where(df.index == 0, np.nan, df["y"])),
                          "y", "g", "h", reps=5, seed=7)
    except ValueError:
        raised = True
    rep.check("★ value_col 里有 NaN 时抛 ValueError（不静默污染中位数）", raised)


def _t_slope(rep: _Report) -> None:
    rep.section("10. overreaction_slope 与 kurtosis")
    rng = np.random.default_rng(18)
    theta_true = np.array([-0.5, -0.2, 0.0, 0.2, 0.5, 0.8])
    shock = np.exp(rng.uniform(0.0, np.log(5.0), size=2000 * 6))
    grp = np.repeat(np.array(["c0", "c1", "c2", "c3", "c4", "c5"]), 2000)
    y = np.repeat(theta_true, 2000) * np.log(shock) + rng.normal(size=shock.size)
    df = pd.DataFrame({"y": y, "shock": shock, "grp": grp})
    theta, se = overreaction_slope(df, "y", "shock", "grp")
    rep.check("★ 斜率个数 = 组数，标准误全 > 0",
              theta.size == 6 and bool(np.all(se > 0)),
              "SE = " + ", ".join("%.3f" % v for v in se))
    ok = all(abs(theta[gi] - np.polyfit(np.log(shock[grp == "c%d" % gi]),
                                        y[grp == "c%d" % gi], 1)[0]) < 1e-10
             for gi in range(6))
    rep.check("与独立实现（polyfit 每组）一致（1e-10）", ok)
    rep.check("斜率接近真值（每组 < 4 个 SE）",
              bool(np.all(np.abs(theta - theta_true) < 4 * se)),
              "max|theta-真值|/SE = %.2f" % float(np.max(np.abs(theta - theta_true) / se)))
    th2, se2 = overreaction_slope(
        df.assign(g=np.repeat([2, 1, 2, 1, 2, 1], 2000)), "y", "shock", "g")
    rep.check("换分组列 → 组数跟着变（2 组）", th2.size == 2 and bool(np.all(se2 > 0)))
    kn = kurtosis(rng.normal(size=400_000))
    rep.check("kurtosis 辅助函数：正态 ≈ 3（Pearson）", abs(kn - 3.0) < 0.02, "%.4f" % kn)


def _t_config(rep: _Report) -> None:
    rep.section("11. 参数来源与签名（SPEC 第五节：参数从 config 读）")
    import inspect
    import stats_core as me

    sig_w = inspect.signature(winsorize).parameters
    sig_d = inspect.signature(cross_sectional_demean).parameters
    sig_m = inspect.signature(cell_medians_boot).parameters
    rep.check("截尾默认值 = EventConfig.winsor_lower / winsor_upper",
              sig_w["lower"].default == EVENT.winsor_lower
              and sig_w["upper"].default == EVENT.winsor_upper,
              "%.2f / %.2f（config %.2f / %.2f）"
              % (sig_w["lower"].default, sig_w["upper"].default,
                 EVENT.winsor_lower, EVENT.winsor_upper))
    rep.check("模块常数 WINSOR_LOWER/UPPER 也是从 config 来的（build_event_table 从这里 import）",
              WINSOR_LOWER == EVENT.winsor_lower and WINSOR_UPPER == EVENT.winsor_upper)
    rep.check("cell_medians_boot 的 reps/seed 默认值 = EventConfig.random_draws/random_seed",
              sig_m["reps"].default == EVENT.random_draws
              and sig_m["seed"].default == EVENT.random_seed,
              "%s / %s" % (sig_m["reps"].default, sig_m["seed"].default))
    rep.check("cross_sectional_demean 默认列名 = SPEC 签名",
              sig_d["hour_col"].default == "hour" and sig_d["out_col"].default == "excess")
    rep.check("设计矩阵列名常数 = SPEC 1.3",
              FOUR_CELL_NAMES == ("const", "P", "q", "Pq")
              and SIX_CELL_NAMES == ("const", "P", "q", "q2", "Pq", "Pq2"))
    gone = [n for n in ("block_weights", "boot_se", "ols_boot", "boot_median_se")
            if hasattr(me, n)]
    rep.check("★ D14.1 要删的四个重抽函数确实不在了", not gone, "残留 %s" % gone)
    gone2 = [n for n in ("two_way_se", "_one_way_vcov", "_pair_codes")
             if hasattr(me, n)]
    rep.check("★ 双向聚类整个删掉了（two_way_se / _one_way_vcov / _pair_codes 都不在）",
              not gone2, "残留 %s" % gone2)
    sig_c = inspect.signature(cluster_se).parameters
    rep.check("cluster_se 的签名 = SPEC：X, y, cluster_codes（没有 hour 维度）",
              list(sig_c) == ["X", "y", "cluster_codes"], ", ".join(sig_c))
    # 本文件既可以被 import 成 stats_core，也可以直接当 __main__ 跑，所以比文件名
    # 而不是比 __module__（后者两种跑法不同）。
    rep.check("★ chi2_sf 是本文件实现的（不是 scipy 别名）",
              Path(chi2_sf.__code__.co_filename).resolve()
              == Path(me.__file__).resolve(),
              Path(chi2_sf.__code__.co_filename).name)


def _selftest() -> int:
    print("=" * 78)
    print("stats_core 自检（v3；合成数据，不读真实面板，不依赖 scipy）")
    print("=" * 78)
    t0 = time.perf_counter()
    rep = _Report()
    _t_units(rep)
    _t_demean(rep)
    _t_winsorize(rep)
    _t_winsorize_did(rep)
    _t_chi2(rep)
    _t_wald(rep)
    _t_cluster(rep)
    _t_four_cell(rep)
    _t_six_cell(rep)
    _t_median(rep)
    _t_slope(rep)
    _t_config(rep)
    print("\n" + "=" * 78)
    print("共 %d 项：PASS %d，FAIL %d（耗时 %.1f s）"
          % (rep.total, rep.total - rep.bad, rep.bad, time.perf_counter() - t0))
    print("结论：" + ("全部通过" if rep.bad == 0 else "有失败项，退出码 1"))
    print("=" * 78)
    return 1 if rep.bad else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
