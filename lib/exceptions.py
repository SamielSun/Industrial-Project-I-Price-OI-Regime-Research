"""
SchemaViolation —— schema 校验失败时抛出的异常。

虽然异常类是内置的（ValueError），但用一个子类让「数据未通过 schema 契约」
可被精确捕获：直接用 ValueError 的话，调用方 except ValueError 会把别处的
ValueError（例如 YAML 解析、类型转换）一起吞掉。

用法：
    try:
        schema.validate(df)
    except SchemaViolation as e:
        # e.problems 是问题清单，一次报全（§Q7 步骤 0 第 3 轮）
        ...
"""

from __future__ import annotations

from typing import Sequence


class SchemaViolation(ValueError):
    """DataFrame 未通过某个 TableSchema 的契约校验。"""

    def __init__(self, table: str, problems: Sequence[str]) -> None:
        self.table = table
        self.problems = list(problems)
        n = len(self.problems)
        head = "\n".join(f"  [{i + 1}] {p}" for i, p in enumerate(self.problems))
        super().__init__(f'表 "{table}" 未通过 schema 校验（{n} 处问题）：\n{head}')


class ConfigViolation(ValueError):
    """设计参数非法（例如 --sample-end 不是月末日）。"""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        head = "\n".join(f"  [{i + 1}] {p}" for i, p in enumerate(self.problems))
        super().__init__(f"配置非法（{len(self.problems)} 处问题）：\n{head}")
