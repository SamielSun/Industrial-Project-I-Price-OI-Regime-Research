# -*- coding: utf-8 -*-
"""Figure 1: the mentor plan's research-logic pipeline.

Pass 1 measures every block (after wrapping, with a generous auto-shrink
floor), pass 2 rebuilds the canvas at exactly the height the layout needs.
Content lives in fig1_content.py.
"""
import sys
sys.path.insert(0, r"D:\Industrial Programme I\_build")
from flowlib import (set_canvas, box, box_h, arrow, edge, finish, L, C, INK,
                     text_block, _specs)  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

import fig1_content as CT  # noqa: E402

X_L, X_R = 2.0, 238.0
FIG_W = 15.6
DRY_CANVAS_H = 13.0            # dry figure height -> 0.065 in per unit
PAD_Y = 1.2
GAP = 2.8
FIT = ([1, 2, 3], 8.2)

cA = [16.6, 50.2, 83.8, 117.2]
wA = 32.8
GEO = {
    "head": dict(cx=120.0, w=X_R - X_L, lines=CT.HEAD, kind="gate",
                 pad_y=PAD_Y),
    "univ": dict(cx=120.0, w=120.0, lines=CT.UNIV, kind="gate", pad_x=2.4,
                 pad_y=1.2, wrap_w=115.0),
    "d1": dict(cx=cA[0], w=wA, lines=CT.D1, kind="data", wrap_w=wA - 4.6),
    "d2": dict(cx=cA[1], w=wA, lines=CT.D2, kind="signal", wrap_w=wA - 4.6),
    "d3": dict(cx=cA[2], w=wA, lines=CT.D3, kind="signal", wrap_w=wA - 4.6),
    "d4": dict(cx=cA[3], w=wA, lines=CT.D4, kind="signal", wrap_w=wA - 4.6),
    "regime": dict(cx=18.0, w=36.0, lines=CT.REG, kind="signal", pad_x=1.4,
                   wrap_w=33.0),
    "xtab": dict(cx=92.0, w=58.0, lines=CT.XTAB, kind="signal", wrap_w=54.0),
    "out": dict(cx=40.0, w=80.0, lines=CT.OUT, kind="test", wrap_w=75.0),
    "met": dict(cx=99.0, w=38.0, lines=CT.MET, kind="test", wrap_w=34.0),
    "base": dict(cx=40.0, w=80.0, lines=CT.BASE, kind="warn", wrap_w=75.0),
    "verdict": dict(cx=99.0, w=38.0, lines=CT.VERD, kind="judge", wrap_w=34.0,
                    pad_x=1.2),
    "deliv": dict(cx=120.0, w=X_R - X_L, lines=CT.DELIV, kind="gate",
                  wrap_w=224.0),
}

# ------------------------------------------------------------- dry measure ---
set_canvas((FIG_W, DRY_CANVAS_H), (0, 240), (0, 200))
_h, _fitted = {}, {}
for k, g in GEO.items():
    _h[k], _fitted[k] = box_h(g["cx"], g["lines"], g["w"],
                              pad_x=g.get("pad_x", 1.6),
                              pad_y=g.get("pad_y", PAD_Y),
                              wrap_w=g.get("wrap_w"), fit_size=FIT)

HA = max(_h["d1"], _h["d2"], _h["d3"], _h["d4"])
HB = max(_h["regime"], _h["xtab"])
HC = max(_h["out"], _h["met"])
HD = max(_h["base"], _h["verdict"])
HE = _h["deliv"]
total = (_h["head"] + 1.6 + _h["univ"] + GAP
         + HA + GAP + HB + GAP + HC + GAP + HD + GAP + HE)
PHYS_H = DRY_CANVAS_H * total / 200.0
print(f"content {total:.1f} du -> figure {FIG_W:.1f} x {PHYS_H:.2f} in")
print("   " + "  ".join(f"{k}={_h[k]:.1f}" for k in GEO))
print("   rows: " + "  ".join(f"{n}={v:.1f}" for n, v in
                              (("A", HA), ("B", HB), ("C", HC), ("D", HD),
                               ("E", HE))))

# --------------------------------------------------------------- real draw ---
fig, ax, ren = set_canvas((FIG_W, PHYS_H), (0, 240), (0, total))


def put(key, cy, min_h=0.0):
    g = GEO[key]
    box(ax, key, g["cx"], cy, g["w"], _fitted[key], kind=g["kind"],
        pad_x=g.get("pad_x", 1.6), pad_y=g.get("pad_y", PAD_Y), min_h=min_h)


y = total
put("head", y - _h["head"] / 2)
y -= _h["head"] + 1.6
put("univ", y - _h["univ"] / 2)
y -= _h["univ"] + GAP

# ---- row A ----
yA = y - HA / 2
for k in ("d1", "d2", "d3", "d4"):
    put(k, yA, min_h=HA)
for a, b in (("d1", "d2"), ("d2", "d3"), ("d3", "d4")):
    arrow(ax, edge(a, "r"), edge(b, "l"))
y -= HA + GAP

# ---- row B ----
yB = y - HB / 2
put("regime", yB, min_h=HB)
dh, dw, _, _ = text_block(0, -1e5, [L("状态 x 费率状态\n交叉分层", 10.0, "bold")])
_specs.clear()
DW, DH = max(dw + 11.0, 30.0), dh * 2.25
DCX = 46.0
ax.add_patch(Polygon([(DCX - DW / 2, yB), (DCX, yB + DH / 2),
                      (DCX + DW / 2, yB), (DCX, yB - DH / 2)], closed=True,
                     facecolor=C["judge"][0], edgecolor=C["judge"][1],
                     linewidth=1.6, zorder=2))
ax.text(DCX, yB, "状态 x 费率状态\n交叉分层", ha="center", va="center",
        fontsize=10.0, fontweight="bold", color=INK, linespacing=1.5, zorder=6)
put("xtab", yB, min_h=HB)
arrow(ax, edge("d1", "b"), edge("regime", "t"))
arrow(ax, edge("regime", "r"), (DCX - DW / 2, yB))
arrow(ax, (DCX + DW / 2, yB), edge("xtab", "l"))
arrow(ax, edge("d4", "b"), edge("xtab", "t"))
y -= HB + GAP

# ---- row C ----
yC = y - HC / 2
put("out", yC, min_h=HC)
put("met", yC, min_h=HC)
arrow(ax, edge("regime", "b"), edge("out", "t"))
arrow(ax, edge("met", "l"), edge("out", "r"))
y -= HC + GAP

# ---- row D ----
yD = y - HD / 2
put("base", yD, min_h=HD)
put("verdict", yD, min_h=HD)
arrow(ax, edge("out", "b"), edge("base", "t"))
arrow(ax, edge("base", "r"), edge("verdict", "l"))
arrow(ax, edge("met", "b"), edge("verdict", "t"))
y -= HD + GAP

# ---- row E ----
put("deliv", y - HE / 2, min_h=HE)
arrow(ax, edge("verdict", "b"), edge("deliv", "t"))

finish("fig1_research_pipeline",
       "图 1 ｜ 导师方案的研究逻辑主线：数据 → 信号 → 状态分类 → 交叉分层 → 前向检验 → 基线对比 → 结论")
