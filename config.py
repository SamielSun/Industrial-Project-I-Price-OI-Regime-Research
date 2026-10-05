"""
Phase 1 设计参数（研究设计的一部分，跨运行稳定）。

原则（phase1/guidance.md §5.3 与 §0）：
  · 本文件只放【设计参数】—— 定义"研究是什么"。
  · 运行参数（--sample-end、--no-refresh、--symbols）走 CLI，不进本文件。
    理由：若把 sample_end 写进这里，两次运行会共用同一份 config.py 却内容不同，
    事后无法回答"这个结果是用哪套设计跑的"。

所有数值的依据见 phase1/guidance.md §3。
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

    实测（285 个候选池合约）：OI 首月分布是断崖 —— 2020-09 只有 BTCUSDT 一个，
    2021-11 为零，2021-12 突然 101 个。各候选起点的 OI 覆盖率：
        2020-01 → 0/285    2021-09 → 1/285
        2021-12 → 102/285  2022-06 → 114/285
    其余四源（klines/mark/index/funding）都有 101 个合约能回溯到 2020，
    唯一卡住的是 OI。往前推可多得约 100 万根 bar，但那段 OI 覆盖率为 0.4%——
    本项目研究 Price + Open Interest，没有 OI 的历史段对核心信号无用。

    BTC 另有 2020-09..2021-11 的完整历史，但【不做附录、不进任何产出】（已决策）。
    """

    # ---- Universe 构造（§3）----
    K: int = 50
    """成员数"""

    liq_window_days: int = 30
    """流动性计算窗口"""

    refresh_months: int = 1
    """成员集刷新频率（月）"""

    # ---- 四条资格闸（§3.1）----
    min_history_bars: int = 2160
    """闸 2①：截至月初已有的 1h bar 数下限（= 90 天）。

    note 要求 regime 阈值用 rolling 60/70 分位、funding 状态用 trailing
    25/75/90 分位。2160 个观测足以估计 p90，720（30 天）太薄。
    代价：样本前 3 个月所有合约都"历史不足"，成员集为空。

    ⚠️ 这一条【单独不够】—— 合约死后 bar 数不再增长而阈值固定，于是永远通过。
    必须与「最后活跃日 >= 月初」合用（见 require_live_at_month_start）。
    """

    require_live_at_month_start: bool = True
    """闸 2②：要求合约的【最后活跃日】不早于评估月月初，即"月初仍在交易"。

    没有这一条，下架合约会永久留在候选里：实测 LUNAUSDT（2022-05-12 停止交易）
    的 bar 数冻结在 3,912 > 2,160，从 2022-07 起每月都"通过"。

    这不是流动性闸 —— 它只要求"月初之后还有成交"，不要求"成交足够多"。
    流动性由「按 liq 排名取前 K」承担。
    """

    min_oi_coverage: float = 0.90
    """闸 3①：trailing 30 天内 OI 快照非空占比下限。
    不取 1.0 —— 存在全市场级偶发缺失（如 2022-03-07 一天 105 个合约同时为 0）。"""

    max_oi_gap_hours: int = 48
    """闸 3②：trailing 30 天内【最长连续缺失】的小时数上限。

    这一条比覆盖率更有区分度：实测每合约最长连续缺失中位仅 10h，
    而 >48h 的只有 46 个合约（最长 7832h）。"缺 1 小时"影响 1 个观测，
    "缺 48 小时"让 48 个观测全无 OI —— 对滚动窗口的破坏完全不同。
    """

    stablecoin_bases: tuple[str, ...] = (
        "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "SUSD", "USDD",
        "PYUSD", "EUR", "FRAX", "USTC",
    )
    """闸 1：按 base_asset 判定，不按符号字面。

    ⚠️ **这是手工维护的名单，不是官方字段** —— exchangeInfo 没有"是否稳定币"
    这一列，只能自己列。所以它的完备性需要定期核。

    2026-10-04 审计（655 个纯加密合约的 baseAsset）：
      · 归档里名字像稳定币的有 3 个：USDC / FRAX / USTC
      · 初版名单只有 USDC，**漏了 FRAX（Frax 算法稳定币）与 USTC（TerraUSD）**
      · 已补上。两者当时都不在候选池，所以不影响任何产出数字。
      · 另反向核过：候选池 285 个里"价格最大偏离 1"< 0.05 的为 0 个。

    复核方法（不用价格猜，只用名字 + 价格交叉验证）：
      1. 取所有 contractType==PERPETUAL 且 underlyingType==COIN 的 baseAsset
      2. 筛名字像稳定币的（以 USD/EUR/DAI 等开头或结尾）
      3. 逐个用 klines 验证：`(close - 1).abs().max() < 0.05` 才是真稳定币
         ⚠️ 不能用 close 的【中位数】—— 实测 THETAUSDT 中位数 1.007 会误判，
            它在区间内涨跌数倍，只是恰好穿越过 1。
    """

    # ---- 路径与IO（非设计参数，但需集中管理）----
    parquet_compression: str = "zstd"
    event_lookbacks: tuple[int, ...] = (1, 4, 8, 24)
    """事件 horizon（小时）。仅登记，Phase 1 不使用（派生量放 Phase 2，见 §2.2 Step 5）。"""

    def snapshot(self) -> dict[str, Any]:
        """设计参数的完整快照，供写入 00_config/sample_end.json（§5.3）。"""
        d = dataclasses.asdict(self)
        d["stablecoin_bases"] = list(self.stablecoin_bases)
        d["event_lookbacks"] = list(self.event_lookbacks)
        return d


CONFIG = Config()


# ============================================================================
# --sample-end 校验（§5.3：强制显式、必须是月末日）
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
    """设计参数非法（例如 --sample-end 不是月末日）。

    异常类定义在此处而非单独模块，好让本文件零外部依赖。
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        head = "\n".join(f"  [{i + 1}] {p}" for i, p in enumerate(self.problems))
        super().__init__(f"配置非法（{len(self.problems)} 处问题）：\n{head}")


def validate_sample_end(s: str, cfg: Config = CONFIG) -> None:
    """校验 --sample-end。通过则静默返回，否则抛 ConfigViolation。

    规则：
      1. 必须提供（该参数必填且无默认值，§5.3）
      2. 必须是合法 ISO 日期
      3. 必须是月末日（因只用完整月）
      4. 不早于 sample_start
    """
    problems: list[str] = []

    if not isinstance(s, str) or not s:
        raise ConfigViolation(["--sample-end 未提供。该参数【必填且无默认值】（§5.3）。"])

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
