"""
跨期设计参数（研究设计的一部分，跨运行稳定）。

本文件集成三期，各用一个 frozen dataclass，**不合并**：
  · `Config`       —— Phase 1（数据采集与 universe）
  · `RegimeConfig` —— Phase 2（regime 标注）
  · `EventConfig`  —— Phase 3（事件研究）
分开是刻意的：`phase1/build_deliverables.py` 调 `CONFIG.snapshot()` 写
`phase1/REPRODUCE.md`；合并会让 Phase 2 的参数**泄漏进 D1 的产出快照**。

· 只放【设计参数】—— 改这里 = 改研究设计。
· 【工程控制】走 CLI，不进本文件（--out-root / --sample-end / --jobs / --dry-run /
  --subset / --batch / --verify 等 20 个开关）；完整清单见各脚本 --help 与
  对应的 REPRODUCE.md。

判断标准：**改它会不会改变产出？**
  会（如 --sample-end）→ 设计参数；但逐次运行不同且必须显式，故仍走 CLI，
    由 Step 6b 连同本文件全部字段写进 phase1/REPRODUCE.md 以便追溯。
  不会（如 --jobs、--out-root）→ 纯工程控制，放本文件只会污染设计快照。

每个字段的 docstring 给出【依据 + 关键实测数字】—— 那是判断"能不能改"的出处。
早期设计的 --no-refresh / --symbols 从未实现，已删除，不要照旧文档去传。
"""

from __future__ import annotations

import calendar
import dataclasses
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence


@dataclass(frozen=True)
class Config:
    """Phase 1 全部设计参数。"""

    # ---- 样本窗口 ----
    sample_start: str = "2021-12-01"
    """样本起点。由 OI 归档的断崖唯一定死，不是权衡结果。
    """

    # ---- Universe 构造 ----
    K: int = 50
    """成员数"""

    liq_window_days: int = 30
    """流动性计算窗口"""

    # ---- 四条资格闸 ----
    min_history_bars: int = 2160
    """闸 2①：截至月初已有的 1h bar 数下限（= 90 天）。2160 足以估计 p90，720（30 天）太薄。
    代价：样本前 3 个月所有合约都"历史不足"，成员集为空。

    ⚠️ 单独不够 —— 合约死后 bar 数不再增长而阈值固定，于是永远通过。
    必须与 require_live_at_month_start 合用。
    """

    require_live_at_month_start: bool = True
    """闸 2②：合约的【最后活跃日】不早于评估月月初（"月初仍在交易"）。

    没有它，下架合约永久留在候选里：实测 LUNAUSDT（2022-05-12 停止交易）的 bar 数
    冻结在 3,912 > 2,160，从 2022-07 起每月都"通过"。
    这不是流动性闸（只要求"还有成交"）；流动性由「按 liq 排名取前 K」承担。
    """

    min_oi_coverage: float = 0.90
    """闸 3①：trailing 30 天内 OI 覆盖率下限 —— 分母是窗口的【全部】小时。

    `bar_missing` 的小时同样没有 OI（网格整行置 NaN），算缺失。因此本闸还兜住了
    「窗口被截断」：通过闸 2 的单元里有 3 个窗口可观测度只有 5%–28%
    （BNXUSDT 2023-03 / TLMUSDT 2023-04 / ICPUSDT 2022-10），全部由本闸拦下。
    不取 1.0 —— 归档本身就有缺失：面板内 OI 缺口合计 32,514 小时
    （归因见 data/04_qa/data_quality.md §3）。

    ⚠️ 口径与闸 3②【不同，不可合并】：3② 跳过 `bar_missing`（见 max_oi_gap_hours）。
    ⚠️ 与 `oi == 0` 无关：那是【值等于 0】不是【快照缺失】，实测完全互斥
    （`oi == 0 & oi_missing` 有 0 行）。旧 docstring 拿"2022-03-07 一天 105 个合约
    同时为 0"当依据，是类别错误（那天的 105 个也不是最集中的 —— 2025-07-21 是 223 个）。
    """

    max_oi_gap_hours: int = 48
    """闸 3②：trailing 30 天内【OI 发布本身】最长连续缺失的上限。

    看的是覆盖率看不出的「整段断供」：缺 1 小时影响 1 个观测，缺 72 小时让 72 个
    观测全无 OI —— 对滚动窗口的破坏完全不同。窗口 30 天 ⇒ 该量天然落在 [0, 720]。

    ⚠️ 与 3① 口径【不同，不可合并】：本闸跳过 `bar_missing`。实测那些小时归档里
    其实【有】OI，是第 2 层网格规则丢的；不跳过会把 klines 归档洞记成「OI 不可靠」——
    2022-03 曾因此误拦 36 个合约，其中 18 个流动性本在前 50（SOLUSDT 是门槛的 36 倍）。

    实测（285 合约 × 57 月 = 16,245 单元）：
      · 真缺口 > 48h 的 33 个（LITUSDT 11 / ICPUSDT 9 / TLMUSDT 9 / AIAUSDT 2 / PUMPUSDT 2）
      · 窗口内无任何数据的 6,451 个 → 记 NaN，判「未知」而非「无缺口」，不达标
      · 【不单独拦下任何单元】：缺口取值只落在 {24, 43, 48, 72, 73, 168, 720}，
        (48, 72) 为空 → 阈值取 [48, 72) 内任何值结果相同，48 是空带下沿（保守侧）。
        保留本闸是防「49–71h 的单个真缺口」这个尚未出现的情况。

    ⚠️ 不要拿"全样本最长连续缺失 7,573 小时"当依据 —— 那是 index 源、跨全样本。
    """

    stablecoin_bases: tuple[str, ...] = (
        "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "SUSD", "USDD",
        "PYUSD", "FRAX", "USTC",
    )
    """闸 1：按 base_asset 判定，不按符号字面。

    ⚠️ **手工维护的名单 —— 没有任何单一来源能覆盖全。** 2026-10-04 对比三来源各自
    覆盖到币安期货归档的稳定币：本名单 USDC FRAX USTC · 币安官方 `stablecoin` 标签
    只覆盖 USDC（且【只打在现货交易对上】，集合不同；FRAX/USTC 官方只标 `defi`）
    · CoinGecko USDC FRAX USTC BOB（更全，但要与归档求交集才用得上 —— 212 个
    symbol 只 4 个命中）。→ **官方标签反而是三者里最少的**，不能单独用。

    口径：剔除的是【以稳定币或法币为标的的币对】，不是"名字叫稳定币的东西"。
    所以 `USDCUSDT` 与假想的 `EURUSDT` 同类，要剔一起剔。

    已移除：`USDT`/`EUR`（归档里 baseAsset 为它们的合约各 0 个，纯冗余；`USDTTRY`
    这类不以 USDT 结尾的早在 enumerate_archive 就被滤掉）；`BOB`（曾依 CoinGecko
    纳入后撤回 —— 币安现货无该对、官方标签覆盖不到、只有单一来源；当初用的 $0.9987
    是 CoinGecko 聚合价而非币安永续价；且其 exchangeInfo status 已是 `SETTLING`）。
    """

    # ---- 路径与IO：本类不含非设计参数 ----
    # 已删除 parquet_compression / event_lookbacks / refresh_months，同一理由：
    # **没有任何代码读取，却经 snapshot() 进产出元信息冒充"设计参数"**。
    # （分别对应：七个写盘点各自硬编码 zstd；Phase 2 的规划值；成员集本就逐月刷新。）

    def snapshot(self) -> dict[str, Any]:
        """设计参数快照，供 Step 6b 写入 phase1/REPRODUCE.md。
        只含【真正影响产出】的字段 —— 每一个都必须被至少一处代码读取。"""
        d = dataclasses.asdict(self)
        d["stablecoin_bases"] = list(self.stablecoin_bases)
        return d


CONFIG = Config()


# ============================================================================
# Phase 2 设计参数（regime 标注）—— 独立 dataclass，不与 Config 合并
# 完整依据见 phase3_event/PHASE3_GUIDANCE.md
# ============================================================================

@dataclass(frozen=True)
class RegimeConfig:
    """Phase 2（regime 标注）的全部设计参数。"""

    # ---- 频率与变化窗 ----
    freqs: tuple[str, ...] = ("1h", "4h", "8h", "1d")
    """⚠️ 1d 的**身份是稳健性对照，不是并列主频率**。note 第 61-64 行把它排在
    "Preferred frequency" 的最后一条："Daily aggregation for robustness" ——
    1h 是 initial study，4h/8h 是 optional tests，1d 是 robustness。
    报告里 1d 只出现在稳健性小节，不参与主结论。"""
    n_bars: int = 1
    """变化窗 N，单位是【该频率的 bar】。1h 频率下 N=1 即 1 小时。
    实测 N=1/4/24 对 undefined 占比几乎无影响（85.86% / 86.14% / 86.11%）——
    N 只定"事件的时间尺度"，不是"严格程度"的旋钮。"""

    # ---- 分位阈值 ----
    window_days: int = 90
    """分位窗 W（日历天）。不用 bar 数：若写"252 根 bar"，1h 只看 10.5 天、
    8h 看 84 天，含义不同。"""
    min_history_days: int = 30
    """最短历史，**时间判据而非观测数**。不足 → regime=undefined 且 excl_reason=warmup。
    三处统一（价格/OI、funding、市场条件）：funding 的结算序列不规则（1/2/4/8h），
    "30 天"无法用固定观测数表达；规则序列上两种判据结果相同。"""
    quantiles: tuple[float, ...] = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
    """阈值敏感性扫描。D2 要求 60–80，上下各多一档看边界行为。"""
    quantile_main: float = 0.70
    """主口径。实测组成几乎不随分位变（p55→p80 只漂 2–4pp），所以它只是样本量旋钮
    （标注率 23.01% → 7.49%）。"""
    z_thresholds: tuple[float, ...] = (0.50, 0.75, 1.00, 1.25, 1.50)
    """note §6 点名的第二种方法。对照时必须按【匹配标注率】与分位法配对
    （实测 |z|>0.50 ↔ p60、|z|>0.75 ↔ p75），否则两者标注量差 3 倍、不可比。"""

    # ---- funding ----
    funding_window_days: int = 90
    funding_min_history_days: int = 30
    """在【结算序列】上算：一次结算一票，不填充 / 不累加 / 不归一。
    三序列（结算 / 小时 ffill / 小时年化）的状态分歧只有 1.91%~2.82%，选结算序列
    是为了不发明观测。"""

    # ---- 市场条件（note §10 的 "market condition"） ----
    mkt_vol_window_hours: int = 8760
    """切点的回看窗口 = 1 年（trailing，不是全样本分位——后者是前视）。"""
    mkt_vol_min_history_days: int = 30
    """取 30 天而非 83 天：缺口从 6.47% 降到 4.20%，并让 2022-05 的 LUNA 崩盘月
    （note §11 里 "Stress / High Vol" 的原型样本）被覆盖。"""
    mkt_vol_smooth_hours: int = 24
    """横截面中位数之后的 trailing 平滑窗口（去掉小时级噪声）。"""
    mkt_vol_quantiles: tuple[float, float] = (1 / 3, 2 / 3)
    """低 / 中 / 高的切点。注意三档**不等分**（实测 37.4 / 31.1 / 31.5）——
    这是 trailing 切点的必然结果，报告里必须写明占比。"""

    def snapshot(self) -> dict[str, Any]:
        """设计参数快照，供 regime_generator 写入 phase2_regime/REPRODUCE.md。"""
        d = dataclasses.asdict(self)
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}


REGIME = RegimeConfig()


# ============================================================================
# Phase 3 设计参数（事件研究）—— 独立 dataclass，不与 Config / RegimeConfig 合并
# 依据与全部实测数字见 phase3_event/PHASE3_GUIDANCE.md
# ============================================================================

@dataclass(frozen=True)
class EventConfig:
    """Phase 3（事件研究）的全部设计参数。"""

    horizons: tuple[int, ...] = (1, 4, 8, 24)
    """前向期，单位【日历小时】。note §8A 原文点名这四个。
    ⚠️ 与 RegimeConfig.n_bars 不同：n_bars 定"事件的时间尺度"（该频率的 bar 数），
    本字段定"往后看多远"。两者正交 —— 4h 标签的 fwd_1h 仍在 1h 阶梯上量。"""

    random_draws: int = 1000
    """随机时点基准 / 合约内安慰剂的重复次数。
    取 1000 是因为分位检验的双侧 p 下限 = 2/B = 0.002；再大对小样本的收益递减。"""

    random_seed: int = 20240501
    """抽样的固定种子。写死在这里而不是 CLI，否则同一份报告两次运行不可比。"""

    bh_q: float = 0.05
    """Benjamini-Hochberg 的 FDR 水平。家族 = 4 状态 × 4 前向期 × 2 样本 = 32 个
    mean_sig 的双侧聚类 t 检验；除此之外不做任何校正。"""

    ic_min_contracts: int = 20
    """IC 每小时参与排名的合约数下限。headline 平均 49.8 个合约/时刻
    （1,966,729 行 / 39,459 个时刻），20 约为均值 40%，低于此的小时不稳。"""

    figure_dpi: int = 200
    """图的分辨率（工程参数，不影响任何统计量，但按本文件口径一并快照）。"""

    # ---- v2 冻结口径（D13）----
    # winsor_lower / winsor_upper 已删除（2026-10-28）：主口径改成"市场中性、不截尾"之后，
    # 全仓库没有任何代码读它们，截尾那一整套（面板的 y / y_sig、events 的 winsor_fwd、
    # 全池阈值 json）也已从 build.py 里拔掉。留在这里会让人以为还有个截尾开关。
    # （block_hours 已随 D14 删除：市场中性化后小时维度的序列相关 lag24 只剩 0.001，
    #   block bootstrap 只把 SE 放大 1.04×，买不到东西。）

    def snapshot(self) -> dict[str, Any]:
        """设计参数快照（与 Config / RegimeConfig 同接口；Phase 3 现在不落盘快照，
        参数直接写在 EventConfig 与 PHASE3_GUIDANCE.md 里）。"""
        d = dataclasses.asdict(self)
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}


EVENT = EventConfig()


# ============================================================================
# --sample-end 校验（强制显式、必须是月末日）
# ============================================================================

def is_month_end(s: str) -> bool:
    """字符串是否为「某月最后一天」的 ISO 日期。"""
    try:
        d = date.fromisoformat(s)
    except (ValueError, TypeError):
        return False
    last = calendar.monthrange(d.year, d.month)[1]
    return d.day == last


class ConfigViolation(ValueError):
    """设计参数非法（例如 --sample-end 不是月末日）。定义在此处而非单独模块，
    好让本文件零外部依赖。"""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        head = "\n".join(f"  [{i + 1}] {p}" for i, p in enumerate(self.problems))
        super().__init__(f"配置非法（{len(self.problems)} 处问题）：\n{head}")


def validate_sample_end(s: str, cfg: Config = CONFIG) -> None:
    """校验 --sample-end。通过则静默返回，否则抛 ConfigViolation。
    规则：① 必须提供（必填无默认）② 合法 ISO 日期 ③ 月末日（因只用完整月）
    ④ 不早于 sample_start。"""
    problems: list[str] = []

    if not isinstance(s, str) or not s:
        raise ConfigViolation(["--sample-end 未提供。该参数【必填且无默认值】。"])

    try:
        d = date.fromisoformat(s)
    except ValueError:
        raise ConfigViolation([
            f'--sample-end="{s}" 不是合法 ISO 日期（应为 YYYY-MM-DD）。'
        ])

    if not is_month_end(s):
        last = calendar.monthrange(d.year, d.month)[1]
        problems.append(
            f'--sample-end="{s}" 不是月末日。因只用完整月，'
            f"本月的合法取值为 {d.year:04d}-{d.month:02d}-{last:02d}。"
        )

    start = date.fromisoformat(cfg.sample_start)
    if d < start:
        problems.append(
            f'--sample-end="{s}" 早于 sample_start="{cfg.sample_start}"。'
        )

    if problems:
        raise ConfigViolation(problems)


if __name__ == "__main__":
    # 自测：python config.py
    import sys

    cases = [
        ("2026-10-31", True), ("2026-10-15", False), ("2026-02-28", True),
        ("2026-02-29", False), ("notadate", False), ("2020-01-31", False), ("", False),
    ]
    bad = 0
    print("validate_sample_end 自测")
    for s, should_pass in cases:
        try:
            validate_sample_end(s)
            got = True
        except ConfigViolation:
            got = False
        ok = got == should_pass
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {s or '(空)':12s} "
              f"期望{'通过' if should_pass else '拒绝'}，实际{'通过' if got else '拒绝'}")

    try:
        CONFIG.K = 30
        print("  [FAIL] Config 可被修改")
        bad += 1
    except Exception as e:
        print(f"  [PASS] Config frozen（{type(e).__name__}）")

    print(f"\n结果：{'全部通过' if bad == 0 else f'{bad} 项失败'}")
    sys.exit(1 if bad else 0)
