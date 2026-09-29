"""
项目路径定义。

原则：全部由 __file__ 推导，与当前工作目录（cwd）无关。
理由：各阶段脚本可能从 phase1_data/ 等子目录运行，相对路径会失效。

目录布局见 PHASE1_GUIDANCE.md §10。
"""

from pathlib import Path

# 项目根 = 本文件的父目录的父目录（本文件位于 <root>/lib/paths.py）
ROOT = Path(__file__).resolve().parent.parent

# ---- data/ 下四个目录（§10）----
DATA = ROOT / "data"
CONFIG_DIR = DATA / "00_config"        # sample_end.json, manifest.parquet
LAYER2 = DATA / "01_layer2"            # 4 张规范化源表
FEATURES = DATA / "02_features"        # features_1h
REFERENCE = DATA / "03_reference"      # master, universe_*, member_changes

OUTPUTS = ROOT / "outputs"

# ---- 具体文件 ----
SAMPLE_END_JSON = CONFIG_DIR / "sample_end.json"
MANIFEST = CONFIG_DIR / "manifest.parquet"

# ---- 第 2 层表目录（§8.2）----
LAYER2_KLINES = LAYER2 / "klines_1h"
LAYER2_MARK_INDEX = LAYER2 / "mark_index_1h"
LAYER2_OI = LAYER2 / "oi_1h"
LAYER2_FUNDING = LAYER2 / "funding"

FEATURES_1H = FEATURES / "features_1h"

# ---- 参考表（§10，03_reference/）----
MASTER = REFERENCE / "master.parquet"
UNIVERSE_ELIGIBILITY = REFERENCE / "universe_eligibility.parquet"
UNIVERSE_MEMBERSHIP = REFERENCE / "universe_membership.parquet"
MEMBER_CHANGES = REFERENCE / "member_changes.parquet"

# 第 2 层表名 → 目录，供构建与校验按名索引
LAYER2_DIRS = {
    "klines_1h": LAYER2_KLINES,
    "mark_index_1h": LAYER2_MARK_INDEX,
    "oi_1h": LAYER2_OI,
    "funding": LAYER2_FUNDING,
}


def chunk_path(table_dir: Path, year: int, month: int) -> Path:
    """按月 chunk 的文件路径：<table>/year=YYYY/chunk=YYYY-MM.parquet（§12.6.4）"""
    ym = f"{year:04d}-{month:02d}"
    return table_dir / f"year={year:04d}" / f"chunk={ym}.parquet"


def ensure_dirs() -> None:
    """创建全部数据目录（幂等）。"""
    for d in (CONFIG_DIR, LAYER2_KLINES, LAYER2_MARK_INDEX, LAYER2_OI,
              LAYER2_FUNDING, FEATURES_1H, REFERENCE, OUTPUTS):
        d.mkdir(parents=True, exist_ok=True)
