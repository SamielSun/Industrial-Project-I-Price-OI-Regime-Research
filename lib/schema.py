"""
Schema 契约 —— Phase 1 的 API 契约。下游 Phase 2–5 依此编写代码。

权威定义在本文件。PHASE1_GUIDANCE.md §8.2/§8.3 描述【语义】（每列什么意思、
单位、为什么），本文件定义【类型】。自测（python -m lib.schema）会校验
两者列名一致，防止漂移。

=============================================================================
类型词汇表（步骤0 第3轮 Q1：最小集，整数一律用 float64）
=============================================================================
    "string"    →  pandas "string"（原生，不绑 pyarrow 后端）
    "float64"   →  pandas float64
    "timestamp" →  pandas datetime64[ns, UTC]

为什么整数也用 float64：float64 精确表示到 2^53，而 trades 等远低于此。
  且 int8/int16/int32/int64 不支持 NaN（实测 TypeError），用 float 反而消除了
  「不确定某列是否可空」时的类型选择问题。

为什么 string 不绑 pyarrow 后端：string[pyarrow] 内存更省（实测 7.5 vs 28 MB
  / 50 万行），但 Parquet 对字符串本就字典编码，体积几乎无差；而绑后端会把
  schema 钉在 pandas 的实现细节上。

=============================================================================
可空性（步骤0 第4轮 Q4 + 第5轮 Q2）
=============================================================================
数据列【全部允许 null】—— funding_rate 只在 00/08/16 非空是设计要求，
  用可空性区分「设计性缺失 vs 损坏」与 oi_missing 职责重复。

唯一例外：每张表的【标识列】（source_timestamp_col）强制非空 ——
  主键为空不是设计而是损坏：NaT 在 join 时静默匹配不上，那些行会无声消失。

为补偿「全允许 null」，validate() 另加三条【无参】完整性检查（见 validate_contract）。
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from lib.exceptions import SchemaViolation

__all__ = [
    "Column", "TableSchema", "SemanticType",
    "SEMANTIC_TO_PANDAS", "pandas_dtype_of", "normalize_dtype",
    "SOURCE_SCHEMAS", "LAYER2_SCHEMAS", "FEATURES_1H", "ALL_SCHEMAS", "get_schema",
    "KLINE_12_NAMES", "raw_source_columns",
    "validate", "validate_contract",
]

SemanticType = Literal["string", "float64", "timestamp", "bool"]

SEMANTIC_TO_PANDAS: dict[str, str] = {
    "string": "string",
    "float64": "float64",
    "timestamp": "datetime64[ns, UTC]",
    "bool": "bool",
}

GUIDANCE_PATH = Path(__file__).resolve().parent.parent / "PHASE1_GUIDANCE.md"


@dataclass(frozen=True)
class Column:
    """一列的定义。frozen —— 契约不可就地修改。"""
    name: str
    dtype: str
    note: str = ""          # 语义注释（如改名来源 "← count"）


@dataclass(frozen=True)
class TableSchema:
    """一张表的完整契约。"""
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    source_timestamp_col: str | None = None
    """标识列：强制非空 + 必须落在整小时。funding 表为 None（事件表，无小时网格）。"""
    source_has_header_variants: bool = False
    """该源存在【无表头】的历史文件（实测：klines 2022-01 前、mark/index 2022-09 前）。"""
    is_grid: bool = False
    """是否密集网格。features_1h 是；第 2 层四张表都不是 —— 第 2 层忠实反映源里有什么。"""
    note: str = ""

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def dtypes(self) -> dict[str, str]:
        return {c.name: c.dtype for c in self.columns}

    def pandas_dtypes(self) -> dict[str, str]:
        """列名 → 期望的 pandas dtype 字符串。"""
        return {c.name: SEMANTIC_TO_PANDAS[c.dtype] for c in self.columns}


def pandas_dtype_of(sem: str) -> str:
    return SEMANTIC_TO_PANDAS[sem]


def normalize_dtype(dt: Any) -> str:
    """把 pandas dtype 归一到可比较的规范字符串。

    必要性：pandas 2.x 的字符串 dtype 有多种等价写法
    （'string' / 'string[pyarrow]' / StringDtype(storage=...)），
    直接字符串比较会误判。
    """
    s = str(dt)
    if s.startswith("datetime64"):
        return "datetime64[ns, UTC]" if ("UTC" in s or "utc" in s) else s
    if s.startswith("string") or s.startswith("StringDtype"):
        return "string"
    if s in ("bool", "boolean", "bool[pyarrow]"):
        return "bool"
    return s


# ============================================================================
# 源 schema —— 描述【解析器归一化之后】的形态
# 注意：原始文件里时间戳是 int 毫秒（open_time/calc_time）或字符串（create_time），
#       归一化后统一为 datetime64[ns, UTC]。
# ============================================================================

def _cols(*spec) -> tuple[Column, ...]:
    out = []
    for s in spec:
        out.append(Column(*s) if len(s) == 3 else Column(s[0], s[1]))
    return tuple(out)


# klines / markPriceKlines / indexPriceKlines / premiumIndexKlines 共用 12 列
KLINE_12_NAMES = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]
_KLINE_12 = tuple(
    (n, "timestamp" if n in ("open_time", "close_time") else "float64")
    for n in KLINE_12_NAMES
)

SOURCE_SCHEMAS: dict[str, TableSchema] = {
    "klines": TableSchema(
        name="klines", columns=_cols(*_KLINE_12),
        primary_key=("open_time",), source_timestamp_col="open_time",
        source_has_header_variants=True,
    ),
    "markPriceKlines": TableSchema(
        name="markPriceKlines", columns=_cols(*_KLINE_12),
        primary_key=("open_time",), source_timestamp_col="open_time",
        source_has_header_variants=True,
    ),
    "indexPriceKlines": TableSchema(
        name="indexPriceKlines", columns=_cols(*_KLINE_12),
        primary_key=("open_time",), source_timestamp_col="open_time",
        source_has_header_variants=True,
    ),
    "premiumIndexKlines": TableSchema(
        name="premiumIndexKlines", columns=_cols(*_KLINE_12),
        primary_key=("open_time",), source_timestamp_col="open_time",
        source_has_header_variants=True,
        note="登记备查；本项目不使用（基差由 mark/index 近似，见 §8.2）",
    ),
    "metrics": TableSchema(
        name="metrics",
        columns=_cols(
            ("create_time", "timestamp", "字符串格式，需按量级判断解析"),
            ("symbol", "string"),
            ("sum_open_interest", "float64", "张数"),
            ("sum_open_interest_value", "float64", "USDT 名义额"),
            ("count_toptrader_long_short_ratio", "float64", "2022 全年大面积为空；不存"),
            ("sum_toptrader_long_short_ratio", "float64", "同上；不存"),
            ("count_long_short_ratio", "float64", "同上；不存"),
            ("sum_taker_long_short_vol_ratio", "float64", "同上；不存"),
        ),
        primary_key=("create_time", "symbol"), source_timestamp_col="create_time",
        source_has_header_variants=False,
    ),
    "fundingRate": TableSchema(
        name="fundingRate",
        columns=_cols(
            ("calc_time", "timestamp", "毫秒位实测为 1 而非 0，勿假设整秒"),
            ("funding_interval_hours", "float64"),
            ("last_funding_rate", "float64"),
        ),
        primary_key=("calc_time",), source_timestamp_col="calc_time",
        source_has_header_variants=False,
    ),
}


# ============================================================================
# 第 2 层 schema（4 张规范化表，§8.2）
# ============================================================================

LAYER2_SCHEMAS: dict[str, TableSchema] = {
    "klines_1h": TableSchema(
        name="klines_1h",
        columns=_cols(
            ("symbol", "string"),
            ("ts", "timestamp", "← open_time 归一化"),
            ("ts_end", "timestamp", "= ts + 1h；区间终点 = OI 对齐时刻 = 决策时刻"),
            ("open", "float64"), ("high", "float64"), ("low", "float64"),
            ("close", "float64"),
            ("volume", "float64", "基础资产"),
            ("quote_volume", "float64", "USDT；流动性度量原料"),
            ("trades", "float64", "← count（改名）"),
            ("taker_buy_volume", "float64"), ("taker_buy_quote_volume", "float64"),
        ),
        primary_key=("symbol", "ts"), source_timestamp_col="ts",
    ),
    "mark_index_1h": TableSchema(
        name="mark_index_1h",
        columns=_cols(
            ("symbol", "string"),
            ("ts", "timestamp"), ("ts_end", "timestamp"),
            ("mark_close", "float64", "← markPriceKlines.close"),
            ("index_close", "float64", "← indexPriceKlines.close"),
        ),
        primary_key=("symbol", "ts"), source_timestamp_col="ts",
        note="mark 与 index 时间戳实测完全重合，故合并为一表（§8.2）",
    ),
    "oi_1h": TableSchema(
        name="oi_1h",
        columns=_cols(
            ("symbol", "string"),
            ("ts", "timestamp"),
            ("ts_end", "timestamp", "= ts + 1h；OI 快照取此整点"),
            ("oi", "float64", "← sum_open_interest（张数）"),
            ("oi_value", "float64", "← sum_open_interest_value（USDT）"),
            ("oi_missing", "bool", "该整点的快照不存在"),
        ),
        primary_key=("symbol", "ts"), source_timestamp_col="ts",
        note="重建表：源为 5 分钟快照，本表按 ts_end 抽样 24/288",
    ),
    "funding": TableSchema(
        name="funding",
        columns=_cols(
            ("symbol", "string"),
            ("ts_funding", "timestamp", "← calc_time；结算时刻，即 ts_end 的对齐目标"),
            ("funding_rate", "float64", "← last_funding_rate"),
            ("funding_interval_hours", "float64", "原样保留，暴露 4h/8h 差异"),
        ),
        primary_key=("symbol", "ts_funding"), source_timestamp_col=None,
        note="事件表，非小时网格 —— 不宜造 funding_1h（前向填充会发明数据）",
    ),
}


# ============================================================================
# 第 3 层：features_1h
# 列顺序与 PHASE1_GUIDANCE.md §8.3 的表格一致（自测校验）
# ============================================================================

FEATURES_1H = TableSchema(
    name="features_1h",
    columns=_cols(
        ("symbol", "string"),
        ("ts", "timestamp", "bar 起点 H"),
        ("ts_end", "timestamp", "= ts + 1h；区间终点 = OI 对齐时刻 = 决策时刻"),
        ("open", "float64"), ("high", "float64"), ("low", "float64"),
        ("close", "float64"),
        ("volume", "float64"),
        ("quote_volume", "float64", "流动性度量原料"),
        ("trades", "float64"),
        ("taker_buy_volume", "float64"), ("taker_buy_quote_volume", "float64"),
        ("oi", "float64", "OI(ts_end)，单位：张"),
        ("oi_value", "float64", "一致性校验用：oi_value/oi/close ≈ 1"),
        ("mark_close", "float64"), ("index_close", "float64"),
        ("funding_rate", "float64", "仅 00/08/16 非空"),
        ("funding_interval_hours", "float64", "仅结算时刻非空"),
        ("bar_missing", "bool", "该小时在 klines_1h 中无对应行"),
        ("oi_missing", "bool", "该小时 OI 快照不存在"),
    ),
    primary_key=("symbol", "ts"), source_timestamp_col="ts", is_grid=True,
    note="密集网格：覆盖 [oi_archive_start, last_active_date]，缺行显式置 null",
)

ALL_SCHEMAS: dict[str, TableSchema] = {
    **SOURCE_SCHEMAS, **LAYER2_SCHEMAS, FEATURES_1H.name: FEATURES_1H,
}


def get_schema(name: str) -> TableSchema:
    if name not in ALL_SCHEMAS:
        raise KeyError(f'未定义的 schema "{name}"。已定义：{sorted(ALL_SCHEMAS)}')
    return ALL_SCHEMAS[name]


def raw_source_columns(source: str) -> list[str]:
    """源归一化后的列名顺序，供解析器使用。

    注意：表头有无必须【逐文件检测】，不可按日期硬编码（§2.2）。
    """
    return list(get_schema(source).names)


# ============================================================================
# 校验
# ============================================================================

def _is_hour_aligned(s: pd.Series) -> bool:
    nn = s.dropna()
    if len(nn) == 0:
        return True
    d = nn.dt
    return bool(((d.minute == 0) & (d.second == 0) & (d.microsecond == 0)
                 & (d.nanosecond == 0)).all())


def validate_contract(
    df: pd.DataFrame,
    schema: TableSchema | str,
    *,
    check_ts_end: bool = True,
) -> None:
    """校验 DataFrame 是否满足契约。失败抛 SchemaViolation（一次报全部问题）。

    检查项：
      结构
        1. 列名与顺序完全一致
        2. dtype 与语义类型一致
        3. 标识列（source_timestamp_col）非空          ← 第4轮 Q2
        4. 主键唯一（无重复行）
        5. 主键已排序（按主键单调）
      完整性（无参，为补偿「数据列全允许 null」）      ← 第4轮 Q5
        6. 无整列为 NaN 的列
        7. 标识列落在整小时（若存在）
      仅 tz 相关
        8. 标识列为 tz-aware UTC（防 naive datetime）

    注意：跨列一致性（oi_value/oi/close ≈ 1）与值域检查【不在此处】——
    它们需要标定阈值，属质量巡检，另有函数（§6.3）。
    """
    if isinstance(schema, str):
        schema = get_schema(schema)

    problems: list[str] = []
    n_rows = len(df)

    # ---- 1. 列名与顺序 ----
    expected = schema.names
    actual = list(df.columns)
    if actual != expected:
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        if missing:
            problems.append(f"缺少列：{missing}")
        if extra:
            problems.append(f"多出列：{extra}")
        if not missing and not extra:
            problems.append(
                f"列名相同但【顺序不同】。期望 {expected}；实际 {actual}"
            )

    # 列名不一致时后续按名取值会失效，但仍尽量检查共同列
    common = [c for c in expected if c in df.columns]

    # ---- 2. dtype ----
    for col in schema.columns:
        if col.name not in df.columns:
            continue
        want = SEMANTIC_TO_PANDAS[col.dtype]
        got = normalize_dtype(df[col.name].dtype)
        if want == "datetime64[ns, UTC]":
            ok = got.startswith("datetime64")
            if ok and not got.endswith("UTC]"):
                problems.append(
                    f'列 "{col.name}" 是 tz-naive 时间戳（{got}），'
                    f"期望 tz-aware UTC。全程 UTC，禁用本地时间。"
                )
                continue
        else:
            ok = (got == want) or (want == "bool" and got == "bool")
        if not ok:
            problems.append(
                f'列 "{col.name}" dtype={got}，期望 {want}（语义类型 {col.dtype}）'
            )

    # ---- 8. 标识列 tz 检查（已在 2 中覆盖；此处不重复）----

    # ---- 3 & 7. 标识列非空 + 整点 ----
    tcol = schema.source_timestamp_col
    if tcol and tcol in df.columns:
        s = df[tcol]
        n_null = int(s.isna().sum())
        if n_null:
            problems.append(
                f'标识列 "{tcol}" 有 {n_null}/{n_rows} 行为空。'
                f"主键为空即损坏：NaT 在 join 时静默匹配不上，那些行会无声消失。"
            )
        if str(s.dtype).startswith("datetime64") and not _is_hour_aligned(s):
            problems.append(
                f'标识列 "{tcol}" 存在非整点的时间戳，期望全部落在整小时（§第4轮 Q5）'
            )

    # ---- 6. 无整列为 NaN ----
    for c in common:
        if df[c].isna().all() and n_rows > 0:
            problems.append(
                f'列 "{c}" 整列为空（{n_rows} 行全 NaN）。'
                f"多半是解析失败 —— 这类错误不会自然发生。"
            )

    # ---- 4 & 5. 主键唯一 + 排序 ----
    pk = [k for k in schema.primary_key if k in df.columns]
    if len(pk) == len(schema.primary_key) and n_rows > 1:
        dupes = int(df.duplicated(subset=pk, keep=False).sum())
        if dupes:
            problems.append(
                f"主键 {tuple(pk)} 有 {dupes} 行重复。"
                f"实测源文件存在完全一致的副本行，去重是必需步骤（§6.1）。"
            )
        else:
            try:
                sorted_ok = df[pk].equals(df[pk].sort_values(pk, kind="stable"))
                if not sorted_ok:
                    problems.append(f"未按主键 {tuple(pk)} 排序（§6.1）")
            except TypeError as e:
                problems.append(f"主键排序检查失败：{e}")

    # ---- ts_end 派生一致性（仅当两列都在）----
    if check_ts_end and "ts" in df.columns and "ts_end" in df.columns:
        both = df[["ts", "ts_end"]].dropna()
        if len(both):
            delta = (both["ts_end"] - both["ts"]).astype("int64")
            bad = int((delta != 3_600_000_000_000).sum())
            if bad:
                problems.append(
                    f"ts_end - ts ≠ 1h 的行有 {bad}/{len(both)}。"
                    f"多半是时间戳单位解析错误（毫秒 vs 秒）。"
                )

    if problems:
        raise SchemaViolation(schema.name, problems)


def validate(df: pd.DataFrame, schema: TableSchema | str, **kw) -> None:
    """validate_contract 的别名（对外主入口）。"""
    validate_contract(df, schema, **kw)


# ============================================================================
# 自测  ——  python -m lib.schema
# 完成判据（PHASE1_GUIDANCE.md §16）：
#   1) 假数据 round-trip：列名/类型/顺序完全一致
#   2) validate() 能捕获故意构造的错误
#   3) 文档 §8.3 的列名与代码一致（防漂移）
# ============================================================================

def _fake_frame(schema: TableSchema, n: int = 6) -> pd.DataFrame:
    """按 schema 生成一份合法的假数据。"""
    ts0 = pd.Timestamp("2026-08-01 00:00:00", tz="UTC")
    data: dict[str, Any] = {}
    for c in schema.columns:
        if c.dtype == "timestamp":
            data[c.name] = pd.Series(
                [ts0 + pd.Timedelta(hours=i) for i in range(n)],
                dtype="datetime64[ns, UTC]",
            )
        elif c.dtype == "float64":
            data[c.name] = pd.Series([1.0 + i for i in range(n)], dtype="float64")
        elif c.dtype == "bool":
            data[c.name] = pd.Series([False] * n, dtype="bool")
        else:  # string
            data[c.name] = pd.Series([f"SYM{i}" for i in range(n)], dtype="string")
    df = pd.DataFrame(data)[schema.names]
    # 若存在 ts/ts_end 对，令其满足 1 小时关系
    if "ts" in df.columns and "ts_end" in df.columns:
        df["ts_end"] = df["ts"] + pd.Timedelta(hours=1)
    return df


def _roundtrip(schema: TableSchema) -> list[str]:
    """写 parquet → 读回，比对列名/顺序/类型。返回问题清单。"""
    import io

    problems: list[str] = []
    df = _fake_frame(schema)
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="zstd")
    buf.seek(0)
    back = pd.read_parquet(buf)

    if list(back.columns) != schema.names:
        problems.append(f"列名/顺序不一致：{list(back.columns)} != {schema.names}")
    for c in schema.columns:
        if c.name not in back.columns:
            continue
        want = normalize_dtype(df[c.name].dtype)
        got = normalize_dtype(back[c.name].dtype)
        if c.dtype == "timestamp":
            if not got.startswith("datetime64") or not got.endswith("UTC]"):
                problems.append(f'"{c.name}" 读回后不是 tz-aware UTC：{got}')
        elif want != got:
            problems.append(f'"{c.name}" 类型变了：写出 {want} → 读回 {got}')
    return problems


def _guidance_column_names(schema_name: str) -> list[str] | None:
    """从 PHASE1_GUIDANCE.md 的标记块读取该表的列名（防文档与代码漂移）。"""
    if not GUIDANCE_PATH.exists():
        return None
    text = GUIDANCE_PATH.read_text(encoding="utf-8")
    pat = re.compile(
        r"<!--\s*COLUMNS:" + re.escape(schema_name) + r"\s*-->(.*?)<!--\s*/COLUMNS\s*-->",
        re.S,
    )
    m = pat.search(text)
    if not m:
        return None
    return re.findall(r"`([a-z_][a-z0-9_]*)`", m.group(1))


def _main() -> int:
    ok, fail = 0, 0

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if passed:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")
            if detail:
                for line in detail.splitlines():
                    print(f"         {line}")

    print("=" * 74)
    print("lib.schema 自测")
    print("=" * 74)

    # ---- 1. round-trip ----
    print("\n[1] 假数据 round-trip（列名 / 类型 / 顺序）")
    for name, sch in ALL_SCHEMAS.items():
        probs = _roundtrip(sch)
        check(f"{name:<20} round-trip", not probs, "\n".join(probs))

    # ---- 2. validate 能放行合法数据 ----
    print("\n[2] validate() 放行合法数据")
    for name, sch in ALL_SCHEMAS.items():
        try:
            validate(_fake_frame(sch), sch)
            check(f"{name:<20} 合法数据通过", True)
        except SchemaViolation as e:
            check(f"{name:<20} 合法数据通过", False, str(e))

    # ---- 3. validate 能捕获故意错误 ----
    print("\n[3] validate() 捕获故意构造的错误")
    sch = LAYER2_SCHEMAS["oi_1h"]
    good = _fake_frame(sch)

    cases: list[tuple[str, pd.DataFrame, str]] = []

    a = good.copy()
    a.loc[0, "ts"] = pd.NaT
    cases.append(("标识列为空 (NaT)", a, "为空"))

    b = good.copy()
    b.loc[0, "ts"] = pd.Timestamp("2026-08-01 00:30:00", tz="UTC")
    cases.append(("时间戳非整点", b, "非整点"))

    c = good.copy()
    c["oi"] = float("nan")
    cases.append(("某列整列为空", c, "整列为空"))

    d = pd.concat([good, good], ignore_index=True)
    cases.append(("主键重复", d, "重复"))

    e = good.iloc[::-1].reset_index(drop=True)
    cases.append(("未按主键排序", e, "排序"))

    f = good.copy()
    f["oi"] = f["oi"].astype("string")
    cases.append(("dtype 错误", f, "dtype"))

    g = good.drop(columns=["oi_value"])
    cases.append(("缺列", g, "缺少列"))

    h = good.copy()
    h["ts_end"] = h["ts"] + pd.Timedelta(minutes=30)
    cases.append(("ts_end 非 ts+1h（单位错误）", h, "ts_end"))

    for label, df, expect_kw in cases:
        try:
            validate(df, sch)
            check(f"捕获：{label}", False, "未抛出 SchemaViolation")
        except SchemaViolation as ex:
            hit = any(expect_kw in p for p in ex.problems)
            check(f"捕获：{label}", hit,
                  "" if hit else f"抛出了异常但信息未含 {expect_kw!r}：\n" +
                  "\n".join(ex.problems))

    # 一次报全
    multi = good.copy()
    multi["oi"] = float("nan")
    multi.loc[0, "ts"] = pd.NaT
    try:
        validate(multi, sch)
        check("一次报全多个问题", False, "未抛出")
    except SchemaViolation as ex:
        check("一次报全多个问题（≥2 条）", len(ex.problems) >= 2,
              f"只报了 {len(ex.problems)} 条")

    # ---- 4. 文档 / 代码一致性 ----
    print("\n[4] PHASE1_GUIDANCE.md §8.3 与代码列名一致（防漂移）")
    doc_names = _guidance_column_names("features_1h")
    if doc_names is None:
        check("找得到文档列名标记块", False,
              f"在 {GUIDANCE_PATH.name} 中未找到 "
              f"<!-- COLUMNS:features_1h --> ... <!-- /COLUMNS --> 标记块")
    else:
        code_names = FEATURES_1H.names
        check("文档与代码列名一致", doc_names == code_names,
              f"文档({len(doc_names)}) {doc_names}\n代码({len(code_names)}) {code_names}")

    # ---- 5. 结构自检 ----
    print("\n[5] schema 自身完整性")
    for name, s in ALL_SCHEMAS.items():
        missing = [k for k in s.primary_key if k not in s.names]
        check(f"{name:<20} 主键列存在", not missing, f"主键列不在列定义中：{missing}")
        if s.source_timestamp_col:
            check(f"{name:<20} 标识列在主键中",
                  s.source_timestamp_col in s.primary_key,
                  f"{s.source_timestamp_col} 不在 {s.primary_key}")
        bad = [c.name for c in s.columns if c.dtype not in SEMANTIC_TO_PANDAS]
        check(f"{name:<20} 类型都在词汇表内", not bad, f"未知类型：{bad}")

    # ---- 6. 主键形状（仅下游表）----
    # 本项目的下游表都是 (symbol, 时间戳) 形状。若丢了实体键（例如误写成 ("ts",)），
    # 表就无法区分不同合约在同一小时的记录 —— 而这类退化不会在任何数据检查中暴露。
    # 源 schema 不适用：源文件是【单合约文件】，主键里没有 symbol 是正常的。
    print("\n[6] 主键形状（仅第 2 层与 features）：(symbol, 时间戳)")
    downstream = {**LAYER2_SCHEMAS, FEATURES_1H.name: FEATURES_1H}
    for name, s in downstream.items():
        want = ("symbol", s.source_timestamp_col) if s.source_timestamp_col \
            else ("symbol", "ts_funding")
        check(f"{name:<20} 主键 = {want}", tuple(s.primary_key) == want,
              f"实际 {s.primary_key}")

    # ---- 7. 源 schema 主键：标识列必须在主键中 ----
    print("\n[7] 源 schema 主键含其标识列（源为单合约文件，无需 symbol）")
    for name, s in SOURCE_SCHEMAS.items():
        check(f"{name:<20} 标识列 {s.source_timestamp_col} 在主键中",
              s.source_timestamp_col in s.primary_key,
              f"主键 {s.primary_key}")

    print("\n" + "=" * 74)
    print(f"结果：{ok} 通过 / {fail} 失败")
    print("=" * 74)
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_main())
