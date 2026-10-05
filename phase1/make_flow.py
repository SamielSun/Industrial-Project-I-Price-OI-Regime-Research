"""生成 Phase 1 处理流程图 -> phase1/phase1_flow.png

设计要点：**数字全部从产出自动读取**，不硬编码。
  之前手写数字导致过"图与数据不一致"（Step 1 明细对不上账）。
  现在合约数、行数、成员数、闸的拦下量都从 data/ 现读。

用法：
    python phase1/make_flow.py
"""
from __future__ import annotations

import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pyarrow.parquet as pq
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.family"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
D = ROOT / "data"
OUT = HERE / "phase1_flow.png"
tmp = OUT.with_name(OUT.name + ".tmp.png")

# ---------------------------------------------------------------- 读真实数字
run = json.loads((D / "00_config" / "sample_end.json").read_text(encoding="utf-8"))
archive = pd.read_csv(D / "00_config" / "archive_contracts.csv")
elig = pq.read_table(D / "03_reference" / "universe_eligibility.parquet",
                     partitioning=None).to_pandas()
mem = pq.read_table(D / "03_reference" / "universe_membership.parquet",
                    partitioning=None).to_pandas()
mst = pq.read_table(D / "03_reference" / "master.parquet",
                    partitioning=None).to_pandas()

N_ARCH = run["archive_contracts"]                    # 1,057
N_ARCH_USDT = run["archive_usdt"]                    # 901
N_KEPT = run["eligible_after_hard_filter"]           # 683
N_POOL = run["candidate_pool_size"]                  # 285
N_FEAT = run["step_5_build_features"]["grid_rows"]   # 7,253,002
N_MEM = run["step_6_build_universe"]["members"]      # 2,700
N_MEM_MONTHS = mem["month"].nunique()
N_MEM_SYMS = mem["symbol"].nunique()
N_CK = run["step_6_build_qa"]["checksums"]           # 1,441
N_ELIG = int(elig["eligible"].sum())

# 文件数 / 大小
def n_files(sub: str) -> int:
    return sum(1 for _ in (D / sub).rglob("*.parquet"))

def mb(sub: str) -> float:
    return sum(f.stat().st_size for f in (D / sub).rglob("*.parquet")) / 1024 / 1024

# Step 1 四条判据的拦下数（照 hard_filter 的 if/continue 顺序重现）
import sys
sys.path.insert(0, str(ROOT))
import config as cfg_mod
cfg = cfg_mod.Config()
snap = json.loads((HERE / "exchange_info_snapshot.json")
                  .read_text(encoding="utf-8"))["classifications"]
usdt = {r.symbol for r in archive.itertuples() if r.is_usdt}
cnt = {"nousdt": 0, "name": 0, "stable": 0, "noncrypto": 0, "kept": 0}
for s in sorted(usdt):
    rec = snap.get(s, {})
    base, quote = rec.get("baseAsset") or "", rec.get("quoteAsset") or ""
    if quote and quote != "USDT":
        cnt["nousdt"] += 1; continue
    if "_" in s or "SETTLED" in s:
        cnt["name"] += 1; continue
    if base and base in cfg.stablecoin_bases:
        cnt["stable"] += 1; continue
    if rec and (rec.get("contractType") != "PERPETUAL"
                or rec.get("underlyingType") != "COIN"):
        cnt["noncrypto"] += 1; continue
    cnt["kept"] += 1
assert cnt["kept"] == N_KEPT, f"重现 {cnt['kept']} != 记录 {N_KEPT}"

# 闸 2/3 的逐闸淘汰量（池内口径，分母 = 候选池 × 月数）
p = elig[elig["in_pool"]]
funnel, cur, prev = [], pd.Series(True, index=p.index), len(p)
for nm, mk in [("闸 1", p.g1), ("闸 2①", p.g2a), ("闸 2②", p.live),
               ("闸 3①", p.g3a), ("闸 3②", p.g3b), ("闸 4", p.g4)]:
    cur &= mk
    funnel.append((nm, prev - int(cur.sum())))
    prev = int(cur.sum())
assert prev == N_ELIG, f"漏斗终值 {prev} != eligible {N_ELIG}"
GATE_DROP = dict(funnel)

print(f"读到: 归档 {N_ARCH:,} / 硬过滤 {N_KEPT} / 候选池 {N_POOL} / "
      f"面板 {N_FEAT:,} / 成员 {N_MEM:,} / 校验和 {N_CK:,}")
print(f"      Step 1 判据: {cnt}")
print(f"      池内漏斗: {funnel}")

# ---------------------------------------------------------------- 画图
C_SRC, C_STEP = "#2E5E8E", "#1F6F4A"
C_L2, C_FEAT, C_REF, C_QA = "#8A5A00", "#B03030", "#6B3FA0", "#4A4A4A"
C_GATE = "#B5651D"

STEPS = [
    ("Step 0", "枚举归档", "S3 列表接口",
     "翻页枚举归档里【存在过】的全部合约，落盘成 archive_contracts.csv",
     f"archive_contracts.csv\n归档清单 {N_ARCH:,} 个合约", "秒级", C_SRC),
    ("Step 1", "硬过滤", "归档清单 + 分类表",
     "四条判据剔除非 USDT 结尾 / 名称怪象 / 稳定币 / 非加密资产",
     f"{N_KEPT} 个加密合约\n+ dropped_contracts.csv（剔除明细）",
     "秒级", C_STEP),
    ("Step 2", "算候选池", f"{N_KEPT} + 月频 klines",
     "逐月按 30 天开区间中位报价成交额取前 50，并集即候选池",
     f"candidate_pool.csv　{N_POOL} 个合约", "8 分钟", C_STEP),
    ("Step 3", "精筛下载", f"候选池 {N_POOL}",
     "一遍过：下载 → 就地解压 → 攒批 → 落盘 → 释放缓存 → 打进度戳",
     f"raw/　{n_files('raw'):,} 文件 / {mb('raw')/1024:.2f} GB", "111 分钟", C_STEP),
    ("Step 4", "建第 2 层", f"raw/ 的 {n_files('raw'):,} 个 parquet",
     "统一时间戳 / 类型 / 列名，以 klines 网格为准对齐 mark·index·OI",
     f"4 张规范化表　{n_files('01_layer2')} 文件 / {mb('01_layer2'):.1f} MB",
     "847s", C_L2),
    ("Step 5", "建分析面板", "4 张表 + 候选池名单",
     "铺密集小时网格 → 裁掉死尾 → 四表 LEFT JOIN（19 列）",
     f"features_1h　{N_FEAT:,} 行 / {n_files('02_features')} 文件", "357s", C_FEAT),
    ("Step 6a", "构造 Universe", "面板 + 候选池 + manifest + 分类表快照",
     "逐月评四条资格闸 → 通过的按流动性取前 50（成员按月冻结）",
     f"universe 四表　成员 {N_MEM:,} 行 / {N_MEM_MONTHS} 月", "239s", C_REF),
    ("Step 6b", "质量与审计", "面板 + manifest",
     "算逐指标缺口与覆盖率 → 生成数据字典 → 全量校验和",
     f"缺失报告 + 字典　校验和 {N_CK:,} 文件", "30s", C_QA),
]

FILTER1 = [
    ('s.endswith("USDT") 为假', "非 USDT 结尾", f"{N_ARCH - N_ARCH_USDT}"),
    ('not (ct=="PERPETUAL" and ut=="COIN")', "非加密资产", f"{cnt['noncrypto']}"),
    ("base_asset in stablecoin_bases", "稳定币", f"{cnt['stable']}"),
    ("'_' in s or 'SETTLED' in s", "交割 / SETTLED", f"{cnt['name']}"),
]

GATES = [
    ("闸 1", "base_asset not in stablecoin_bases", f"{GATE_DROP['闸 1']:,}",
     "候选池在 Step 1 已剔掉稳定币"),
    ("闸 2①", "bars_before >= 2160", f"{GATE_DROP['闸 2①']:,}",
     "挡新上市合约（上市不足 90 天）"),
    ("闸 2②", "last_active >= 月初", f"{GATE_DROP['闸 2②']:,}",
     "挡死合约：只数 bar 数挡不住"),
    ("闸 3①", "oi_cov >= 0.90", f"{GATE_DROP['闸 3①']:,}",
     "挡 OI 长期残缺"),
    ("闸 3②", "oi_max_gap_h <= 48", f"{GATE_DROP['闸 3②']:,}",
     "挡 OI 整段空洞"),
    ("闸 4", "分类字段非加密资产", f"{GATE_DROP['闸 4']:,}",
     "候选池在 Step 1 已剔掉非加密资产"),
]

Y0, GAP = 0.95, 1.62
W, H = 7.0, 1.40
MX = 3.90
RX0, RW = 7.65, 3.75
FA0, FAW = 11.55, 2.55
FB0, FBW = 14.30, 3.05
FW = 17.55

row_y = {s[0]: Y0 + (len(STEPS) - 1 - i) * GAP for i, s in enumerate(STEPS)}
top_row = row_y["Step 0"]
YMAX = top_row + 3.22

fig = plt.figure(figsize=(17.55, 15.60), dpi=170)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, FW)
ax.set_ylim(0, YMAX)
ax.axis("off")


def rbox(x0, y0, w, h, fc, ec, lw=1.6, r=0.09):
    ax.add_patch(FancyBboxPatch(
        (x0, y0), w, h, boxstyle=f"round,pad=0.02,rounding_size={r}",
        linewidth=lw, edgecolor=ec, facecolor=fc, zorder=2))


ax.text(FW / 2, top_row + 2.86, "Phase 1 数据处理流程", ha="center",
        va="center", fontsize=23, fontweight="bold", color="#1A1A1A")
ax.text(FW / 2, top_row + 2.45,
        "THEO / FTEC5910 — Price + Open Interest Regime Signal　|　"
        f"D1：{N_POOL} 个 USDT 本位永续 · {N_MEM_MONTHS} 个月 · 逐小时面板",
        ha="center", va="center", fontsize=12, color="#555555")

col_y = top_row + 1.96
ax.text(MX, col_y, "处理步骤", ha="center", va="center", fontsize=13,
        fontweight="bold", color="#333333")
ax.text(RX0 + RW / 2, col_y, "产出", ha="center", va="center", fontsize=13,
        fontweight="bold", color="#333333")
ax.plot([0.35, FW - 0.25], [col_y - 0.26] * 2, color="#CCCCCC", lw=1.1)

for i, (sid, title, inp, proc, outp, took, col) in enumerate(STEPS):
    y = row_y[sid]
    rbox(MX - W / 2, y - H / 2, W, H, col, col)
    ax.text(MX - W / 2 + 0.28, y + H / 2 - 0.28, f"{sid}　{title}",
            ha="left", va="center", fontsize=11.5, color="white",
            fontweight="bold", zorder=3)
    ax.text(MX + W / 2 - 0.24, y + H / 2 - 0.28, took, ha="right",
            va="center", fontsize=9.2, color="white", alpha=0.88, zorder=3)
    ax.text(MX - W / 2 + 0.28, y + 0.11, f"输入：{inp}", ha="left",
            va="center", fontsize=8.6, color="white", alpha=0.85, zorder=3)
    ax.text(MX - W / 2 + 0.28, y - 0.32, proc, ha="left", va="center",
            fontsize=8.8, color="white", zorder=3)

    rbox(RX0, y - (H - 0.20) / 2, RW, H - 0.20, "#FFFFFF", col, lw=1.7)
    ax.text(RX0 + RW / 2, y, outp, ha="center", va="center", fontsize=9.6,
            color="#1A1A1A", zorder=3, linespacing=1.5)

    ax.add_patch(FancyArrowPatch((MX + W / 2, y), (RX0 - 0.06, y),
                                 arrowstyle="-|>", mutation_scale=13,
                                 lw=1.6, color="#98A2B3", zorder=1))
    if i < len(STEPS) - 1:
        yn = row_y[STEPS[i + 1][0]]
        ax.add_patch(FancyArrowPatch((MX, y - H / 2), (MX, yn + H / 2),
                                     arrowstyle="-|>", mutation_scale=16,
                                     lw=2.1, color="#7A8794", zorder=1))

# 栏 A：Step 1 四条判据
y1 = row_y["Step 1"]
ax.text(FA0 + FAW / 2, y1 + 1.34, "Step 1 四条判据", ha="center",
        va="center", fontsize=10.4, fontweight="bold", color=C_STEP)
ax.text(FA0 + FAW / 2, y1 + 1.04,
        f"归档 {N_ARCH:,} → {N_KEPT}", ha="center", va="center",
        fontsize=8.6, color="#777777")
ax.text(FA0 + FAW / 2, y1 + 0.78, "（判据命中即剔除）", ha="center",
        va="center", fontsize=7.8, color="#999999")
fh, fgap = 0.62, 0.07
fy = y1 + 0.42
for cond, label, n in FILTER1:
    rbox(FA0, fy - fh, FAW, fh, "#EDF6F1", C_STEP, lw=1.2, r=0.06)
    ax.text(FA0 + 0.13, fy - 0.18, cond, ha="left", va="center",
            fontsize=7.3, color="#1F6F4A", fontweight="bold", zorder=3)
    ax.text(FA0 + 0.13, fy - 0.44, f"→ {label}", ha="left", va="center",
            fontsize=7.6, color="#666666", zorder=3)
    ax.text(FA0 + FAW - 0.13, fy - 0.32, n, ha="right", va="center",
            fontsize=9.6, color="#8A4A10", fontweight="bold", zorder=3)
    fy -= fh + fgap

# 栏 B：Step 6a 四条资格闸
y6 = row_y["Step 6a"]
gh, ggap = 0.335, 0.035
n_g = len(GATES)
col_h = n_g * gh + (n_g - 1) * ggap
gy = y6 + col_h / 2 + 0.02
y_head = gy + 0.40
ax.text(FB0 + FBW / 2, y_head + 0.30, "Step 6a 四条资格闸", ha="center",
        va="center", fontsize=10.4, fontweight="bold", color=C_GATE)
ax.text(FB0 + FBW / 2, y_head + 0.04,
        f"分母 {N_POOL} × {N_MEM_MONTHS + 3} = {len(p):,} 合约月",
        ha="center", va="center", fontsize=8.3, color="#777777")

for gid, cond, nfail, why in GATES:
    top = gy
    rbox(FB0, top - gh, FBW, gh, "#FFF6EC", C_GATE, lw=1.3, r=0.06)
    ax.text(FB0 + 0.13, top - 0.10, f"{gid}　{cond}", ha="left", va="center",
            fontsize=8.1, color=C_GATE, fontweight="bold", zorder=3)
    ax.text(FB0 + 0.13, top - 0.25, why, ha="left", va="center",
            fontsize=7.3, color="#888888", zorder=3)
    ax.text(FB0 + FBW - 0.13, top - 0.145, nfail, ha="right", va="center",
            fontsize=9.8, color="#8A4A10", fontweight="bold", zorder=3)
    gy -= gh + ggap

ax.text(FB0 + FBW / 2, gy + ggap - 0.22, f"逐闸递进 → {N_ELIG:,} 合格",
        ha="center", va="center", fontsize=8.3, color="#777777")

fig.savefig(tmp, dpi=170, facecolor="white")
# 先写临时文件再替换：PNG 常被 PowerPoint / 照片查看器占着，
# 直接写会 Errno 22，而且可能留下半截文件。
tmp.replace(OUT)
print(f"wrote {OUT}")
