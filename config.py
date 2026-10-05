"""
Phase 1 设计参数（研究设计的一部分，跨运行稳定）。

原则（phase1/guidance.md §5.3 与 §0）：
  · 本文件只放【设计参数】—— 定义"研究是什么"。改这里 = 改研究设计。
  · 【工程控制】走 CLI，不进本文件。全项目实际存在的参数共 20 个：

      样本窗口   --sample-end                    六个脚本都要；必须月末日
      路径       --out-root                      六个脚本全部必填
                 --raw-root --l2-root --fe-root --pool --manifest
      冒烟       --subset --batch
      断点       --skip-download --keep-cache --keep-existing --list-only
      网络/校验  --jobs --refresh-exchange-info --exchange-info
                 --no-validate --no-schema-note --verify

    判断标准：**改它会不会改变产出？**
      · 会（如 --sample-end）→ 设计参数，但因为它逐次运行不同、且必须显式，
        仍走 CLI 并落进 sample_end.json 以便追溯。
      · 不会（如 --jobs、--out-root）→ 纯工程控制，放本文件只会污染设计快照。

  · 早期设计里的 --no-refresh / --symbols 从未实现，已于本次清理时删除，
    不要照旧文档去传。

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
        "PYUSD", "FRAX", "USTC",
    )
    """闸 1：按 base_asset 判定，不按符号字面。

    ⚠️ **手工维护的名单 —— 没有任何单一来源能覆盖全。**
    2026-10-04 对比三种来源，各自覆盖到币安期货归档的稳定币：

      | 来源                      | 覆盖                |
      |---------------------------|---------------------|
      | 本名单                    | USDC FRAX USTC      |
      | 币安官方 `stablecoin` 标签 | USDC                |
      | CoinGecko 稳定币板块       | USDC FRAX USTC BOB  |

    · **币安官方标签在 get-products 端点（字段 `tags`）**，共 42 个现货交易对。
      但它【只打在现货交易对上】，而我们的标的是 U 本位永续，集合不同；
      且 `FRAXUSDT`/`USTCUSDT` 官方只标 `defi` 没标 `stablecoin`。
      → **官方标签反而是三者里最少的**，不能单独用。
    · CoinGecko 更全，但要与币安归档求交集才用得上（212 个 symbol 只 4 个命中）。

    判定口径：本名单剔除的是【以稳定币或法币为标的的币对】，
    而不是"名字叫稳定币的东西"。所以 `USDCUSDT` 与假想的 `EURUSDT` 同类，
    要剔一起剔；`EUR` 作为法定货币本可另设 `fiat_bases`，此处并入即可。

    已从名单移除的（2026-10-04）：
      · `USDT` / `EUR` —— 归档里 baseAsset 为它们的合约各 0 个，纯冗余。
        注意 `USDTTRY`/`USDTBRL` 这类【不以 USDT 结尾】，早在
        enumerate_archive 的 endswith("USDT") 就被滤掉，进不了闸 1。
      · `BOB` —— 曾依据 CoinGecko 纳入，后撤回。理由：
        (a) 币安现货没有 BOB 交易对，官方标签覆盖不到，只有单一来源；
        (b) 当初用的 $0.9987 是 CoinGecko 的【聚合价】，不是币安永续价格，
            而本项目应看币安永续自身的行为 —— 那个没验证过；
        (c) 币安 exchangeInfo 里 BOBUSDT 的 status 已是 `SETTLING`
            （2025-11-21 上市，正在结算/下架）。
        证据不足，不加。将来若它在币安永续侧确证钉住 1，再加。
    """

    # ---- 路径与IO：本类不含非设计参数 ----
    # 原 `parquet_compression`（"zstd"）与 `event_lookbacks`(1,4,8,24) 已删除：
    #   · 前者从未被任何代码读取 —— 七个写盘点各自硬编码 compression="zstd"，
    #     改这个字段不会有任何效果，留着会造成"改了却没生效"的误导。
    #   · 后者是 Phase 2 的规划值，Phase 1 全程不使用，只被 snapshot() 序列化进
    #     sample_end.json 冒充"设计参数"。规划信息已移入 phase1/guidance.md §2.2。

    def snapshot(self) -> dict[str, Any]:
        """设计参数的完整快照，供写入 00_config/sample_end.json（§5.3）。

        只含【真正影响产出的】字段 —— 每一个都必须被至少一处代码读取。
        """
        d = dataclasses.asdict(self)
        d["stablecoin_bases"] = list(self.stablecoin_bases)
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
