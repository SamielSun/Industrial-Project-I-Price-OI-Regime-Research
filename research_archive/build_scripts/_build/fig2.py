# -*- coding: utf-8 -*-
"""Figure 2: the mentor plan's 5-phase test plan (vertical flow) + deliverables.

Same two-pass method as figure 1: measure with final wrapping, then build the
canvas at exactly the needed height.
"""
import sys
sys.path.insert(0, r"D:\Industrial Programme I\_build")
from flowlib import (set_canvas, box, box_h, arrow, finish, L, C, INK, SUB,
                     _specs)  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

X_L, X_R = 2.0, 238.0
SPINE_W = 38.0                 # phase-name column
OPS_X = 44.0                   # operations column starts here
OUT_W = 58.0                   # output column width
FIG_W = 16.0
DRY_CANVAS_H = 13.0
PAD_Y = 1.2
PAD_Y_ROW = 1.6
GAP_ROW = 3.2
GAP_BLOCK = 3.0
FIT = ([0, 1, 2], 8.0)

HDR = [
    L("导师方案 First Test Plan：五个阶段，前一阶段的输出就是后一阶段的输入", 13.8, "bold", INK, 1.45),
    L("Phase 1 数据采集  →  Phase 2 状态标注  →  Phase 3 事件研究  →  Phase 4 费率交互  →  Phase 5 简单策略测试",
      10.0, "normal", INK, 1.6),
]

ROWS = [
    ("Phase 1", "数据采集", "data", "D1",
     "· 抓取 OHLCV / 未平仓量 / 资金费率 /\n     成交量 / mark-index 价格\n"
     "· 对齐 UTC 时间戳；处理缺失值与异常值",
     "输出：干净面板数据集 ·\n缺失值报告 · 数据字典"),
    ("Phase 2", "状态标注", "signal", "D2",
     "· 计算价格变化与 OI 变化，按阈值生成\n     四种状态标签\n"
     "· 在 1h / 4h / 8h 三个频率上各做一遍\n· 测试阈值敏感性并统计各状态频率",
     "输出：各状态出现次数 ·\n分资产频率 · 分市场环境频率"),
    ("Phase 3", "事件研究", "signal", "D3",
     "· 对每种状态分别统计：前向收益\n     （均值与中位数）、命中率 hit rate\n"
     "· 事件后的已实现波动、反转概率、延续概率",
     "输出：前向收益表 ·\n事件研究图 · 状态对比图"),
    ("Phase 4", "费率交互", "signal", "D3",
     "· 把每种状态再按资金费率切成\n     负 / 中性 / 高 / 极端四档\n"
     "· 形成 4 x 4 表格，逐格看前向收益与波动",
     "输出：4 x 4 表格（状态 x 费率）·\n每格的前向收益与前向波动"),
    ("Phase 5", "简单策略测试", "test", "D4",
     "· 只有前面几个阶段显示出价值才做。例如：\n"
     "     中性费率下「价升 OI 升 → 延续」、\n     去杠杆后「价跌 OI 降 → 反转」\n"
     "· 含成本回测 + 与四个基线对比；\n     属于 exploratory backtest，不是生产策略",
     "输出：一两条简单规则 ·\n含成本的探索性回测\n（不是生产策略）"),
]

DEL = [
    L("交付物 Deliverables：D1 - D6（导师列的清单，顺序即依赖顺序）", 11.2, "bold"),
    L("D1 干净数据管线：Binance 公开数据拉取 · OHLCV / OI / 资金费率 / 成交量 · Parquet 存储 · 数据字典", 8.8, "normal", INK, 1.62),
    L("D2 价格/OI 状态分类器：变化量计算 · 阈值逻辑 · 四状态标签生成器", 8.8, "normal", INK, 1.62),
    L("D3 事件研究报告：各状态前向收益 · 反转/延续概率 · 费率交互 · 波动影响        "
      "D4 简单策略原型：一两条规则 · 含成本回测 · 与基线对比", 8.8, "normal", INK, 1.62),
    L("D5 看板 / 可视化：各币种当前状态 · 新多建仓榜 · 新空建仓榜 · 去杠杆候选 · 费率调整后的拥挤度视图",
      8.8, "normal", INK, 1.62),
    L("D6 期末报告与答辩：回答「加入 open interest 是否比只看价格更能理解加密永续的短期行为」",
      8.8, "normal", INK, 1.62),
]
COST = [
    L("这个方案里唯一真正会决定成败的部分：成本（cost）", 10.8, "bold"),
    L("导师原文只在评价指标里写了一行 transaction cost sensitivity，把含成本回测推到 D4 / Phase 5。"
      "但本项目已有的实测显示：", 8.6, "normal", INK, 1.62),
    L("(a) 往返成本约 25 bps，其中约 90% 是手续费；"
      "(b) 有效价差在 2021 - 2026 年间从约 23 bps 压缩到约 0.1 bps；", 8.6, "normal", INK, 1.62),
    L("(c) 因此「用一个固定费率 / 价差假设跑全历史」会得出错误结论，成本必须做成时变的。"
      "=> 成本精度是这套信号能否落地的约束条件，不能拖到 Phase 5 才处理。", 8.6, "normal", INK, 1.62),
]

# ------------------------------------------------------------- dry measure ---
set_canvas((FIG_W, DRY_CANVAS_H), (0, 240), (0, 200))
ops_w = (X_R - OUT_W - 4.0) - OPS_X
_h = {}
_h["head"], f_head = box_h(120.0, HDR, X_R - X_L, pad_y=PAD_Y, fit_size=FIT)
row_h, f_ops, f_out, ops_cx, out_cx = [], [], [], OPS_X + ops_w / 2, X_R - OUT_W / 2
for i, (tag, name, kind, dlv, ops, out) in enumerate(ROWS):
    ho, fo = box_h(ops_cx, [L(ops, 9.0, "normal", INK, 1.66)], ops_w,
                   pad_x=2.0, pad_y=PAD_Y_ROW, fit_size=FIT)
    hp, fp = box_h(out_cx, [L(out, 8.8, "normal", "#2d3b48", 1.6)], OUT_W - 2.0,
                   pad_x=1.0, pad_y=PAD_Y_ROW, fit_size=FIT)
    f_ops.append(fo)
    f_out.append(fp)
    row_h.append(max(ho, hp))
_h["deliv"], f_del = box_h(120.0, DEL, X_R - X_L, pad_y=PAD_Y, fit_size=FIT)
_h["cost"], f_cost = box_h(120.0, COST, X_R - X_L, pad_y=PAD_Y, fit_size=FIT)

total = (_h["head"] + GAP_BLOCK + sum(r + GAP_ROW for r in row_h)
         + _h["deliv"] + GAP_BLOCK + _h["cost"])
PHYS_H = DRY_CANVAS_H * total / 200.0
print(f"content {total:.1f} du -> figure {FIG_W:.1f} x {PHYS_H:.2f} in")
print(f"   rows h={[round(r, 1) for r in row_h]}  head={_h['head']:.1f} "
      f"deliv={_h['deliv']:.1f} cost={_h['cost']:.1f}")

# --------------------------------------------------------------- real draw ---
fig, ax, ren = set_canvas((FIG_W, PHYS_H), (0, 240), (0, total))

y = total
box(ax, "head", 120.0, y - _h["head"] / 2, X_R - X_L, f_head, kind="gate",
    pad_y=PAD_Y)
y -= _h["head"] + GAP_BLOCK

spine_x = X_L + 1.0
for i, (tag, name, kind, dlv, ops, out) in enumerate(ROWS):
    cy = y - row_h[i] / 2
    box(ax, f"r{i}", ops_cx, cy, ops_w, f_ops[i], kind=kind,
        pad_x=2.0, pad_y=PAD_Y_ROW)
    box(ax, f"o{i}", out_cx, cy, OUT_W - 2.0, f_out[i], kind="gate",
        pad_x=1.0, pad_y=PAD_Y_ROW, wrap_w=None)

    # left spine marker + phase name
    ax.add_patch(FancyBboxPatch((spine_x, cy - row_h[i] / 2 + 1.2), 1.8,
                                row_h[i] - 2.4,
                                boxstyle="round,pad=0,rounding_size=0.3",
                                linewidth=0, facecolor=C[kind][1], alpha=0.9,
                                zorder=3))
    ax.text(spine_x + 3.4, cy + row_h[i] / 2 - 1.4, tag, ha="left", va="top",
            fontsize=12.6, fontweight="bold", color=C[kind][1], zorder=6)
    ax.text(spine_x + 3.4, cy + row_h[i] / 2 - 5.6, name, ha="left", va="top",
            fontsize=10.8, fontweight="bold", color=INK, zorder=6)

    # D-number marker between rows
    if i > 0:
        arrow(ax, (spine_x + 3.4, y + row_h[i] + GAP_ROW), (spine_x + 3.4, y),
              color="#98a4b0", lw=1.5)
        ax.text(spine_x + 5.6, y + GAP_ROW / 2, dlv, ha="left", va="center",
                fontsize=8.4, color="#6b7885", zorder=6,
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none"))
    y -= row_h[i] + GAP_ROW

ydel = y + GAP_ROW - GAP_BLOCK - _h["deliv"] / 2
box(ax, "deliv", 120.0, ydel, X_R - X_L, f_del, kind="gate", pad_y=PAD_Y)
arrow(ax, (spine_x + 3.4, y + GAP_ROW), (spine_x + 3.4,
                                         ydel + _h["deliv"] / 2),
      color="#98a4b0", lw=1.5)
y = ydel - _h["deliv"] / 2 - GAP_BLOCK
box(ax, "cost", 120.0, y - _h["cost"] / 2, X_R - X_L, f_cost, kind="warn",
    pad_y=PAD_Y)

finish("fig2_test_plan_deliverables",
       "图 2 ｜ 导师方案的执行路线：五个阶段的操作、产出与依赖关系，以及 D1 - D6 交付物与成本约束")
