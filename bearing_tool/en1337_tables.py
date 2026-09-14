"""
Tabulated factors from BS EN 1337-3, transcribed from the standard's own
Table 4 (rectangular bearings) and Table A.1 / Annex A (elliptical bearings).

Source: images supplied by Ash, 2026-09-13 (page 30 for Table 4, page 42 for
Table A.1). Transcribed by hand -- double-check against your copy of the
standard before relying on this for a real design.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Table 4 -- Restoring moment factor Ks for RECTANGULAR bearings, vs b/a.
# This is the table the original MATLAB tool should have looked up instead
# of hardcoding Ks=78.4 (which is exactly this table's value at b/a=1.3 --
# almost certainly a one-off test value that got left in as a "constant").
# ---------------------------------------------------------------------------
_RECT_B_OVER_A: List[float] = [
    0.5, 0.75, 1, 1.2, 1.25, 1.3, 1.4, 1.5,
    1.6, 1.7, 1.8, 1.9, 2, 2.5, 10,
    1.0e9,  # standard tabulates this point as "∞" (infinite strip limit)
]
_RECT_KS: List[float] = [
    137, 100, 86.2, 80.4, 79.3, 78.4, 76.7, 75.3,
    74.1, 73.1, 72.2, 71.5, 70.8, 68.3, 61.9,
    60,
]


def _interp1d(x: float, xs: List[float], ys: List[float]) -> Tuple[float, Optional[str]]:
    """Piecewise-linear interpolation with clamped extrapolation.

    Returns (value, warning) -- warning is None unless x fell outside the
    tabulated range, in which case the boundary value was used.
    """
    if x <= xs[0]:
        warn = None if x == xs[0] else (
            f"b/a={x:.3f} is below the tabulated range (>= {xs[0]}); "
            f"using the boundary value Ks({xs[0]})={ys[0]} -- verify against "
            "EN 1337-3 Table 4 for this aspect ratio."
        )
        return ys[0], warn
    if x >= xs[-1]:
        warn = None if x == xs[-1] else (
            f"b/a={x:.3f} is above the tabulated range; using the infinite-"
            f"strip limit Ks={ys[-1]}."
        )
        return ys[-1], warn
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i]), None
    return ys[-1], None  # unreachable given the bounds checks above


def rectangular_ks(b_over_a: float) -> Tuple[float, Optional[str]]:
    """EN 1337-3 Table 4 restoring-moment factor Ks for a rectangular bearing.

    `b_over_a` is the plan aspect ratio b/a (b = the dimension NOT aligned
    with the rotation axis being checked, i.e. the "length"; a = the
    dimension aligned with it, i.e. the "width" -- matching the original
    tool's convention where Max_moment = max_ang_w * b**5 * a / (n*ti^3*Ks)).

    Returns (Ks, warning). `warning` is set (not raised) when `b_over_a`
    fell outside the tabulated 0.5..∞ range and had to be clamped -- this is
    a secondary/informational coefficient in this tool, so evaluation
    continues rather than failing.
    """
    return _interp1d(b_over_a, _RECT_B_OVER_A, _RECT_KS)


# ---------------------------------------------------------------------------
# Table A.1 -- Factors for ELLIPTICAL (incl. circular) bearings, vs b/a.
# NOT currently wired into the solver: circular/elliptical bearings use
# different area, perimeter and shape-factor formulas throughout (A =
# 0.25*pi*ae*be, P = 0.5*pi*(ae+be), etc.) -- adding real support means a
# parallel geometry path in solver.py, not just swapping this table in for
# rectangular_ks(). Kept here, transcribed and ready, for when that's built.
#
# IMPORTANT per the standard's own footnote: the b/a=1.0 column is valid
# ONLY as an interpolation anchor -- it is explicitly NOT the value to use
# for an actual circular bearing. The correct circular-specific value/formula
# was not visible in the supplied table image; get it from the standard's
# text (Annex A) before using this table for a real circular design.
# ---------------------------------------------------------------------------
ELLIPTICAL_B_OVER_A: List[float] = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 1.0e9]
ELLIPTICAL_KCE: List[float] = [0.25, 0.252, 0.258, 0.262, 0.266, 0.269, 0.270, 0.277, 0.300]  # compression factor
ELLIPTICAL_KDE: List[float] = [0.125, 0.174, 0.204, 0.233, 0.249, 0.265, 0.272, 0.277, 0.300]  # rotation factor
ELLIPTICAL_KSE: List[float] = [150, 115.6, 100, 84.4, 75.7, 68.7, 64.1, 62, 60]  # restoring moment factor


# ---------------------------------------------------------------------------
# Table 3 -- Standard sizes for TYPE B bearings (rectangular a x b rows only;
# this table's separate circular "phi D" rows are omitted since this solver
# doesn't support circular bearings -- see the elliptical table above).
#
# Source: image supplied by Ash, 2026-09-14. Transcribed by hand -- double-
# check against your copy of the standard before relying on this.
#
# Reference/informational only -- NOT wired into bearing_tool.catalog.Catalog
# or the optimizer's search loop. It's here so bearing_tool.catalog's
# ti_options/n_min/n_max defaults can be checked against it (see that
# module's docstrings) and so a future "snap to a real EN 1337-3 standard
# size" feature has the data ready, without forcing the optimizer to only
# ever try these exact (a, b) pairs -- a real design's plan size is
# routinely somewhere *between* these nominal rows (e.g. the H3428 schedule's
# own best design, 250x425mm, falls between the table's 250x400 and 300x400
# rows), so restricting the search to only the table's listed sizes would
# make real, previously-working designs newly unfindable.
#
# Fields, in order: (a_mm, b_mm, unloaded_thickness_min_mm,
# unloaded_thickness_max_mm, elastomer_total_min_mm, elastomer_total_max_mm,
# elastomer_layer_thickness_mm, reinforcing_plates, n_min, n_max).
# `elastomer_layer_thickness_mm` is this table's "ti" -- confirmed exactly
# self-consistent with the total/n columns throughout (e.g. 100x150:
# n=2..3 layers of 8mm = 16..24mm total, matching the table). Note
# `reinforcing_plates` is a single reference count per row (not itself a
# min/max range) and doesn't always equal n_min+1 or n_max+1 -- treat it as
# nominal/typical rather than a hard per-n constraint; bearing_tool already
# derives the real plate count from n (n+1 for type 2, n-1 for type 3 --
# see solver.py) rather than reading it from here.
# ---------------------------------------------------------------------------
TABLE_3_TYPE_B_SIZES: List[Tuple[float, float, float, float, float, float, float, int, int, int]] = [
    (100, 150, 30, 41, 16, 24, 8, 3, 2, 3),
    (100, 200, 30, 41, 16, 24, 8, 3, 2, 3),
    (150, 200, 30, 52, 16, 32, 8, 3, 2, 4),
    (150, 250, 30, 52, 16, 32, 8, 3, 2, 4),
    (150, 300, 30, 52, 16, 32, 8, 3, 2, 4),
    (200, 250, 41, 74, 24, 48, 8, 3, 3, 6),
    (200, 300, 41, 74, 24, 48, 8, 3, 3, 6),
    (200, 350, 41, 74, 24, 48, 8, 3, 3, 6),
    (200, 400, 41, 74, 24, 48, 8, 3, 3, 6),
    (250, 300, 41, 85, 24, 56, 8, 3, 3, 7),
    (250, 400, 41, 85, 24, 56, 8, 3, 3, 7),
    (300, 400, 57, 105, 36, 72, 12, 4, 3, 6),
    (300, 500, 57, 105, 36, 72, 12, 4, 3, 6),
    (300, 600, 57, 105, 36, 72, 12, 4, 3, 6),
    (350, 450, 57, 121, 36, 84, 12, 4, 3, 7),
    (400, 500, 73, 137, 48, 96, 12, 4, 4, 8),
    (400, 600, 73, 137, 48, 96, 12, 4, 4, 8),
    (450, 600, 73, 153, 48, 108, 12, 4, 4, 9),
    (500, 600, 73, 169, 48, 120, 12, 4, 4, 10),
    (600, 600, 94, 199, 64, 144, 16, 5, 4, 9),
    (600, 700, 94, 199, 64, 144, 16, 5, 4, 9),
    (700, 700, 94, 220, 64, 160, 16, 5, 4, 10),
    (700, 800, 94, 220, 64, 160, 16, 5, 4, 10),
    (800, 800, 110, 285, 80, 220, 20, 5, 4, 10),
    (900, 900, 110, 285, 80, 220, 20, 5, 4, 11),
]
ELLIPTICAL_B_OVER_A_1_IS_INTERPOLATION_ONLY = True  # see docstring above
