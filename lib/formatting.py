"""
lib/formatting.py —— 显示与日志格式。

Phase 1 是数据管道，需要【描述统计】与【一致性检查】的可读输出。
注意分工（§6.3 与步骤0 第2轮 Q6）：
  · validate()          只查【结构】契约，必须绝对可靠
  · 本模块的函数        是【统计判断】，阈值需要标定
两者不可混为一谈。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import pandas as pd


def _fmt_num(x: Any) -> str:
    """数字的紧凑显示。"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    if isinstance(x, bool):
        return "是" if x else "否"
    if isinstance(x, float):
        if x != 0 and (abs(x) < 1e-4 or abs(x) >= 1e12):
            return f"{x:.3e}"
        if x == int(x):
            return f"{int(x):,}"
        return f"{x:,.4f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def describe(df: pd.DataFrame, *, sample_rows: int = 5) -> str:
    """表的概览：形状、列、dtype、非空率、样例。"""
    n, m = df.shape
    lines = [f"shape = ({n:,} 行, {m} 列)"]
    if n == 0:
        lines.append("（空表）")
        return "\n".join(lines)

    w = max((len(c) for c in df.columns), default=4)
    lines.append(f"  {'列'.ljust(w)}  {'dtype':<22} {'非空率':>8}  样例")
    lines.append("  " + "-" * (w + 46))
    for c in df.columns:
        s = df[c]
        nn = 1.0 - float(s.isna().mean())
        sample = ", ".join(_fmt_num(v) for v in s.dropna().head(3).tolist()) or "—"
        lines.append(
            f"  {c.ljust(w)}  {str(s.dtype):<22} {nn:>7.1%}  {sample[:34]}"
        )
    if sample_rows:
        lines.append("")
        lines.append(df.head(sample_rows).to_string(max_colwidth=18))
    return "\n".join(lines)


def null_summary(df: pd.DataFrame) -> str:
    """逐列非空计数，按缺失比例降序（缺失最多的排前面）。"""
    if len(df) == 0:
        return "（空表）"
    rows = []
    n = len(df)
    for c in df.columns:
        nn = int(df[c].notna().sum())
        rows.append((c, nn, n - nn, 1.0 - nn / n))
    rows.sort(key=lambda r: -r[3])
    lines = [f"{'列':<28}{'非空':>10}{'空':>10}{'缺失率':>9}"]
    lines.append("-" * 57)
    for c, nn, nu, frac in rows:
        flag = "  <<" if frac > 0 else ""
        lines.append(f"{c:<28}{nn:>10,}{nu:>10,}{frac:>8.2%}{flag}")
    return "\n".join(lines)


def dedup_counts(
    frames: Iterable[tuple[str, pd.DataFrame]],
    *,
    key: Sequence[str] | None = None,
) -> str:
    """对若干 (标签, DataFrame) 统计重复行。

    用于 §6.1 的「去重 + 记录」：实测 2020-09→2021-06 每天 576 行/288 唯一，
    且是完全一致的副本。重复【静默去除】但必须【留下记录】。
    """
    lines = [f"{'来源':<34}{'总行':>12}{'去重后':>12}{'重复':>10}"]
    lines.append("-" * 68)
    total_dup = 0
    for label, df in frames:
        before = len(df)
        after = len(df.drop_duplicates(subset=list(key) if key else None))
        dup = before - after
        total_dup += dup
        mark = "  <<" if dup else ""
        lines.append(f"{label:<34}{before:>12,}{after:>12,}{dup:>10,}{mark}")
    lines.append("-" * 68)
    lines.append(f"{'合计重复行':<34}{'':>12}{'':>12}{total_dup:>10,}")
    if total_dup == 0:
        lines.append("（无重复——若期望有而这里为 0，说明去重逻辑未命中，需排查）")
    return "\n".join(lines)


def consistency_oi_price(df: pd.DataFrame, *, tol: float = 0.02) -> str:
    """OI 价格一致性：oi_value / oi ÷ close ≈ 1（§6.3 c）。

    这是 oi_value 存在的意义 —— 免费的独立校验：若某个源解析错了，
    这个比值会明显偏离 1。
    """
    need = {"oi", "oi_value", "close"}
    if not need.issubset(df.columns):
        return f"（缺列 {sorted(need - set(df.columns))}，跳过）"
    d = df[list(need)].dropna()
    d = d[(d["oi"] > 0) & (d["close"] > 0)]
    if len(d) == 0:
        return "（无有效行）"
    ratio = d["oi_value"] / d["oi"] / d["close"]
    dev = (ratio - 1.0).abs()
    n_bad = int((dev > tol).sum())
    q = dev.quantile([0.5, 0.9, 0.99]).tolist()
    return (
        f"n={len(d):,}  |偏差| 中位={q[0]:.2e} p90={q[1]:.2e} p99={q[2]:.2e} "
        f"max={dev.max():.2e}  |  超阈值({tol}) {n_bad:,} 行 "
        + ("✓" if n_bad == 0 else "<< 需排查")
    )


def consistency_basis(df: pd.DataFrame, *, tol: float = 1e-3) -> str:
    """基差一致性（§6.3 d）：|premium_close − (mark/index − 1)| > tol 即告警。

    注意：features_1h 不含 premium_close（已决定不存），本函数用于
    在【构建时】用 premium 源校验 mark/index 的解析正确性。
    """
    need = {"premium_close", "mark_close", "index_close"}
    if not need.issubset(df.columns):
        return f"（缺列 {sorted(need - set(df.columns))}，跳过）"
    d = df[list(need)].dropna()
    d = d[d["index_close"] > 0]
    if len(d) == 0:
        return "（无有效行）"
    approx = d["mark_close"] / d["index_close"] - 1.0
    dev = (d["premium_close"] - approx).abs()
    n_bad = int((dev > tol).sum())
    return (
        f"n={len(d):,}  |偏差| 中位={dev.median():.2e} max={dev.max():.2e}  "
        f"超阈值({tol}) {n_bad:,} 行 " + ("✓" if n_bad == 0 else "<< 需排查")
    )


def gap_runs(
    present: pd.Series,
    dates: pd.Series,
    *,
    label: str = "",
) -> pd.DataFrame:
    """把逐日缺失【合并成连续缺口区间】（§12.1）。

    检测粒度=日，呈现粒度=区间。预期规模几百到几千行，可逐行肉眼审。
    present: bool 序列（True=该日有数据）
    dates:   日期序列（同一顺序）
    """
    df = pd.DataFrame({"date": pd.to_datetime(dates), "present": present.astype(bool)})
    df = df.sort_values("date").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=["gap_start", "gap_end", "days", "category"])
    grp = (df["present"] != df["present"].shift()).cumsum()
    out = []
    for _, blk in df.groupby(grp):
        if blk["present"].iloc[0]:
            continue
        out.append({
            "gap_start": blk["date"].iloc[0].date().isoformat(),
            "gap_end": blk["date"].iloc[-1].date().isoformat(),
            "days": len(blk),
            "category": "confirmed_404",   # 由调用方按实际情况覆盖
        })
    res = pd.DataFrame(out, columns=["gap_start", "gap_end", "days", "category"])
    if label and len(res):
        res.insert(0, "source", label)
    return res
