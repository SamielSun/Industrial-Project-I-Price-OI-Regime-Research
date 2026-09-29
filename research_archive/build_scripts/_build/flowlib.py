# -*- coding: utf-8 -*-
"""
Flow charts for the mentor's idea note (Price + Open Interest Regime Signal).

Engine notes
------------
* Every box is positioned by its CENTER (cx, cy) in data coordinates.
* Box height is NOT hand-tuned: text is drawn first, measured with the real
  renderer, then the box is drawn around the measured text extent.
* A validation pass afterwards checks (a) text inside its own box,
  (b) no box overlapping another box.
"""
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, FancyArrowPatch
from matplotlib.transforms import Bbox

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT = r"D:\Industrial Programme I\figures"
os.makedirs(OUT, exist_ok=True)
DPI = 150

INK = "#16202b"
SUB = "#44515e"
LINE = "#5b6b7c"

C = {
    "data":   ("#e4eef8", "#3f74ab"),
    "signal": ("#fdf2dc", "#c8963c"),
    "test":   ("#e2f2ea", "#3d8b6e"),
    "judge":  ("#efe8f8", "#7a58ad"),
    "warn":   ("#fbe7e7", "#bb5757"),
    "gate":   ("#f3f6f8", "#8592a0"),
}

_specs = []          # (text_artist, owner_key)
_boxes = {}          # owner_key -> patch
_geom = {"x0": 0.0, "x1": 100.0, "y0": 0.0, "y1": 100.0}
DRY = [False]        # dry-run switch: measure text, draw no box


def set_canvas(figsize, xlim, ylim, dpi=DPI, fresh=True):
    global _fig, _ax, _ren
    if fresh:
        plt.close("all")
        _fig, _ax = plt.subplots(figsize=figsize, dpi=dpi)
    _ax.set_autoscale_on(False)
    _ax.set_xlim(*xlim)
    _ax.set_ylim(*ylim)
    _ax.set_xlim(*xlim)          # set_ylim can re-autoscale x; pin both again
    _ax.axis("off")
    _fig.canvas.draw()
    _ren = _fig.canvas.get_renderer()
    _geom.update(x0=xlim[0], x1=xlim[1], y0=ylim[0], y1=ylim[1])
    return _fig, _ax, _ren


def px2du_dy(fig, dy_px):
    """Convert a vertical pixel size into data units."""
    bb = Bbox.from_extents(0, 0, 0, dy_px).transformed(
        _ax.transData.inverted())
    return abs(bb.y1 - bb.y0)


def px2du_dx(fig, dx_px):
    bb = Bbox.from_extents(0, 0, dx_px, 0).transformed(
        _ax.transData.inverted())
    return abs(bb.x1 - bb.x0)


def wrap(text, size, max_w_du, wrap_tokens=True):
    """Soft-wrap text to a data-unit width. Long ASCII tokens are broken too."""
    if max_w_du <= 0:
        return text
    out = []
    for hard in text.split("\n"):
        words = hard.split(" ") if " " in hard else [hard]
        cur = ""
        for wd in words:
            trial = wd if not cur else cur + " " + wd
            if px2du_dx(_fig, _t_width(trial, size)) <= max_w_du:
                cur = trial
                continue
            if cur:
                out.append(cur)
            # single token longer than the line -> hard break
            if px2du_dx(_fig, _t_width(wd, size)) > max_w_du and wrap_tokens:
                piece = ""
                for ch in wd:
                    if px2du_dx(_fig, _t_width(piece + ch, size)) > max_w_du:
                        out.append(piece)
                        piece = ch
                    else:
                        piece += ch
                cur = piece
            else:
                cur = wd
        out.append(cur)
    return "\n".join(out)


def _t_width(text, size):
    """Width in pixels of the widest line of `text` at `size`."""
    if not text:
        return 0.0
    t = _ax.text(0, 0, text, fontsize=size, linespacing=1.5)
    bb = t.get_window_extent(renderer=_ren)
    t.remove()
    return bb.width


def autofit(cx, lines, max_w, fit_size):
    """Shrink the given line indices until the widest line fits `max_w`.

    `fit_size` is (line_indices, minimum_point_size).
    """
    if not fit_size:
        return lines
    idx, min_size = fit_size
    out = list(lines)
    for i in idx:
        if i >= len(out):
            continue
        t, s, wt, c, ls = out[i]
        size = s
        while size > min_size and px2du_dx(_fig, _t_width(t, size)) > max_w:
            size -= 0.15
        out[i] = (t, max(size, min_size), wt, c, ls)
    return out


def text_block(cx, cy, lines, owner=None, align="center", gap=0.5):
    """Draw a stack of (text, size, weight, colour, linespacing) lines.

    Centred at (cx, cy). Returns (height, width, top, bottom) in data units.
    """
    drawn = []
    for item in lines:
        t, size, weight, colour, ls = item
        art = _ax.text(cx, cy, t,
                       ha={"center": "center", "left": "left",
                           "right": "right"}[align],
                       va="center", fontsize=size,
                       fontweight=weight, color=colour, linespacing=ls,
                       ma={"center": "center", "left": "left",
                           "right": "right"}[align], zorder=6)
        bb = art.get_window_extent(renderer=_ren)
        drawn.append([art, px2du_dy(_fig, bb.height), px2du_dx(_fig, bb.width)])

    h_total = sum(d[1] for d in drawn) + gap * max(0, len(drawn) - 1)
    w_total = max((d[2] for d in drawn), default=0.0)
    y = cy + h_total / 2.0
    for art, h_du, _ in drawn:
        art.set_position((cx, y - h_du / 2.0))
        y -= h_du + gap
        if owner is not None:
            _specs.append((art, owner))
    return h_total, w_total, cy + h_total / 2.0, cy - h_total / 2.0


def fit_lines(cx, lines, w_box, pad_x, wrap_w, fit_size):
    """Apply wrapping then auto-shrink; return the lines that will be drawn."""
    if wrap_w is not None:
        lines = [(wrap(t, s, wrap_w), s, wt, c, ls)
                 for (t, s, wt, c, ls) in lines]
    return autofit(cx, lines, w_box - 2 * pad_x, fit_size)


def box_h(cx, lines, w_box, pad_x=1.6, pad_y=0.9, wrap_w=None, fit_size=None):
    """Height a box will need, measured with the final (fitted) text."""
    fitted = fit_lines(cx, lines, w_box, pad_x, wrap_w, fit_size)
    h_txt = text_block(cx, -1e5, fitted)[0]
    _specs.clear()
    return h_txt + 2 * pad_y, fitted


def box(ax, key, cx, cy, w, lines, kind="data", pad_x=1.6, pad_y=0.9,
        min_h=0.0, radius=0.09, band=None, band_size=11.2, band_extra=1.9,
        wrap_w=None, fit_size=None, align="center"):
    """Draw a box sized to fit its text. `lines` are text_block line tuples."""
    lines = fit_lines(cx, lines, w, pad_x, wrap_w, fit_size)
    h_txt, w_txt, top, bot = text_block(
        cx, -1e5 if DRY[0] else cy, lines,
        owner=None if DRY[0] else key, align=align)
    h = max(h_txt + 2 * pad_y + (band_extra if band else 0.0), min_h)
    if w_txt + 2 * pad_x > w:
        msg = (f"[{key}] text {w_txt:.1f} wider than usable {w - 2 * pad_x:.1f}"
               + ("  (DRY)" if DRY[0] else ""))
        if DRY[0]:
            print("  !! " + msg)
        else:
            raise ValueError(msg)
    if DRY[0]:
        _specs.clear()
        _boxes[key] = (cx - w / 2, cy - h / 2, w, h, kind)
        print(f"  {key:10s} w={w_txt:6.1f} / {w - 2 * pad_x:6.1f}   "
              f"h_req={h_txt + 2 * pad_y:6.1f}")
        return cx - w / 2, cy - h / 2, w, h
    face, edge = C[kind]
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                                boxstyle=f"round,pad=0,rounding_size={radius}",
                                linewidth=1.6, edgecolor=edge, facecolor=face,
                                zorder=2))
    _boxes[key] = (cx - w / 2, cy - h / 2, w, h, kind)
    if band:
        bh = band_size * 0.55 + 2.4
        ax.add_patch(FancyBboxPatch((cx - w / 2, cy + h / 2 - bh), w, bh,
                                    boxstyle="round,pad=0,rounding_size=0.09",
                                    linewidth=0, facecolor=edge, alpha=0.92,
                                    zorder=3))
        ax.text(cx, cy + h / 2 - bh / 2, band, ha="center", va="center",
                fontsize=band_size, color="white", fontweight="bold",
                zorder=7)
    return cx - w / 2, cy - h / 2, w, h


def arrow(ax, p0, p1, color=LINE, lw=1.7, ls="-", ms=15, rad=0.0):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=ms,
                                 linewidth=lw, color=color, linestyle=ls,
                                 connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=1, shrinkB=2, zorder=5))


def edge(key, side):
    x, y, w, h, _ = _boxes[key]
    return {
        "l": (x, y + h / 2), "r": (x + w, y + h / 2),
        "t": (x + w / 2, y + h), "b": (x + w / 2, y),
    }[side]


def validate(name):
    fig = _fig
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
    problems = []
    # (a) text inside its box
    for art, owner in _specs:
        if owner not in _boxes:
            continue
        x, y, w, h, _ = _boxes[owner]
        tb = art.get_window_extent(renderer=ren)
        bb = _ax.transData.transform([(x, y), (x + w, y + h)])
        bx = Bbox.from_extents(bb[0][0], bb[0][1], bb[1][0], bb[1][1])
        if not (tb.x0 >= bx.x0 - 1.5 and tb.x1 <= bx.x1 + 1.5
                and tb.y0 >= bx.y0 - 1.5 and tb.y1 <= bx.y1 + 1.5):
            problems.append(
                f"TEXT OUT OF BOX [{owner}]: '{art.get_text()[:34]}' "
                f"text=({tb.x0:.0f},{tb.y0:.0f})-({tb.x1:.0f},{tb.y1:.0f}) "
                f"box=({bx.x0:.0f},{bx.y0:.0f})-({bx.x1:.0f},{bx.y1:.0f})")
    # (b) boxes must not overlap
    items = list(_boxes.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            k1, b1 = items[i]
            k2, b2 = items[j]
            ov_x = min(b1[0] + b1[2], b2[0] + b2[2]) - max(b1[0], b2[0])
            ov_y = min(b1[1] + b1[3], b2[1] + b2[3]) - max(b1[1], b2[1])
            if ov_x > 0.05 and ov_y > 0.05:
                problems.append(f"BOX OVERLAP {k1} <-> {k2} "
                                f"({ov_x:.2f} x {ov_y:.2f})")
    # (c) boxes inside canvas
    for k, (x, y, w, h, _) in _boxes.items():
        if x < _geom["x0"] - .01 or x + w > _geom["x1"] + .01 \
           or y < _geom["y0"] - .01 or y + h > _geom["y1"] + .01:
            problems.append(f"BOX OUT OF CANVAS [{k}] "
                            f"x=({x:.1f},{x+w:.1f}) y=({y:.1f},{y+h:.1f})")
    print(f"--- validate {name}: {len(problems)} problem(s)")
    for p in problems:
        print("   ", p)
    return problems


def finish(name, caption):
    _fig.text(0.006, 0.004, caption, fontsize=8.8, color="#54636f",
              ha="left", va="bottom")
    _fig.subplots_adjust(left=0.006, right=0.994, top=0.996, bottom=0.018)
    validate(name)
    for ext in ("png", "pdf"):
        _fig.savefig(os.path.join(OUT, f"{name}.{ext}"), dpi=DPI,
                     facecolor="white")
    plt.close(_fig)
    _specs.clear()
    _boxes.clear()


L = lambda t, s=9.0, w="normal", c=INK, ls=1.5: (t, s, w, c, ls)   # noqa: E731
