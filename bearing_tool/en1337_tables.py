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
ELLIPTICAL_B_OVER_A_1_IS_INTERPOLATION_ONLY = True  # see docstring above
