"""
Phase 1 设计参数（研究设计的一部分，跨运行稳定）。

原则（PHASE1_GUIDANCE.md §12.5）：
  · 本文件只放【设计参数】—— 定义"研究是什么"。
  · 运行参数（--sample-end、--no-refresh、--symbols）走 CLI，不进本文件。
    理由：若把 sample_end 写进这里，两次运行会共用同一份 config.py 却内容不同，
    事后无法回答"这个结果是用哪套设计跑的"。

所有数值的依据见 PHASE1_GUIDANCE.md §4。
"""

from __future__ import annotations

import calendar
import dataclasses
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence


@dataclass(frozen=True)
class Config:
    """Phase 1 全部设计参数。"""

    # ---- 样本窗口 ----
    sample_start: str = "2021-12-01"
    """样本起点。实测：除 BTC 外全部主流币的 OI 归档最早可用日为 2021-12-01。"""

    # ---- Universe 构造（§7）----
    K: int = 50
    """成员数"""

    liq_window_days: int = 30
    """流动性计算窗口"""

    refresh_months: int = 1
    """成员集刷新频率（月）"""

    # ---- 四条资格闸（§5）----
    min_history_bars: int = 720
    """闸 2：截至月初已有的 1h bar 数下限（= 30 天）。再小则算不出 30 天滚动中位。"""

    min_oi_coverage: float = 0.90
    """闸 3：trailing 30 天内 sum_open_interest 非空天数占比下限。
    不取 1.0 —— 存在全市场级偶发缺失（如 2025-04-15），100% 会误杀全部合约。"""

    min_active_days: int = 15
    """闸 4：trailing 30 天内 quote_volume > 0 的天数下限。
    实测有成交天数分布两极（正常币 30/30，停摆币 0/30），任何 10–90% 阈值都能切开。"""

    stablecoin_bases: tuple[str, ...] = (
        "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "SUSD", "USDD", "PYUSD", "EUR",
    )
    """闸 1：按 base_asset 判定，不按符号字面"""

    # ---- 路径与IO（非设计参数，但需集中管理）----
    parquet_compression: str = "zstd"
    event_lookbacks: tuple[int, ...] = (1, 4, 8, 24)
    """事件 horizon（小时）。仅登记，Phase 1 不使用（§2.3 派生量放 Phase 2）。"""

    def snapshot(self) -> dict[str, Any]:
        """设计参数的完整快照，供写入 00_config/sample_end.json（§12.5）。"""
        d = dataclasses.asdict(self)
        d["stablecoin_bases"] = list(self.stablecoin_bases)
        d["event_lookbacks"] = list(self.event_lookbacks)
        return d


CONFIG = Config()


# ============================================================================
# --sample-end 校验（§12.5：强制显式、必须是月末日）
# ============================================================================

def is_month_end(s: str) -> bool:
    """字符串是否为「某月最后一天」的 ISO 日期。"""
    try:
        d = date.fromisoformat(s)
    except (ValueError, TypeError):
        return False
    last = calendar.monthrange(d.year, d.month)[1]
    return d.day == last


def last_complete_month(today: date | None = None) -> date:
    """今天之前最后一个【完整】月的月末日。

    注意：这只是给人工参考的便利函数。--sample-end 必须显式传入，
    不存在自动取值（§12.5：强制显式使每个结果必然携带样本边界）。
    """
    today = today or datetime.now().date()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    return last_month_end


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
      1. 必须提供（该参数必填且无默认值，§12.5）
      2. 必须是合法 ISO 日期
      3. 必须是月末日（因 §1.6.6 只用完整月）
      4. 不早于 sample_start
    """
    problems: list[str] = []

    if not isinstance(s, str) or not s:
        raise ConfigViolation(["--sample-end 未提供。该参数【必填且无默认值】（§12.5）。"])

    try:
        d = date.fromisoformat(s)
    except ValueError:
        raise ConfigViolation([
            f'--sample-end="{s}" 不是合法 ISO 日期（应为 YYYY-MM-DD）。'
        ])

    if not is_month_end(s):
        last = calendar.monthrange(d.year, d.month)[1]
        problems.append(
            f'--sample-end="{s}" 不是月末日。因 §1.6.6 只用完整月，'
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
