"""Tests for the EN 1337-3 Table 4 restoring-moment-factor lookup."""

import math

from bearing_tool.en1337_tables import rectangular_ks


def test_exact_table_points():
    # Spot-check several exact points transcribed from Table 4.
    for b_over_a, expected_ks in [
        (0.5, 137), (1, 86.2), (1.3, 78.4), (1.5, 75.3), (2, 70.8), (10, 61.9),
    ]:
        ks, warning = rectangular_ks(b_over_a)
        assert math.isclose(ks, expected_ks, rel_tol=1e-9)
        assert warning is None


def test_interpolates_between_points():
    # Halfway between b/a=1.25 (79.3) and b/a=1.3 (78.4) -> 78.85.
    ks, warning = rectangular_ks(1.275)
    assert math.isclose(ks, 78.85, rel_tol=1e-9)
    assert warning is None


def test_infinite_strip_limit():
    ks, warning = rectangular_ks(1.0e12)
    assert math.isclose(ks, 60, rel_tol=1e-9)


def test_extrapolation_below_range_warns_and_clamps():
    ks, warning = rectangular_ks(0.2)
    assert math.isclose(ks, 137, rel_tol=1e-9)  # clamped to b/a=0.5 value
    assert warning is not None
    assert "below the tabulated range" in warning


def test_extrapolation_above_10_but_below_the_infinite_anchor_does_not_warn():
    # 10 and "infinity" are both real tabulated anchors (the standard's own
    # last two columns), so values in between are ordinary interpolation,
    # not extrapolation.
    ks, warning = rectangular_ks(50)
    assert warning is None
    assert 60 <= ks <= 61.9
