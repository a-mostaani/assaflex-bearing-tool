"""Tests for bearing_tool.catalog.Catalog."""

from bearing_tool.catalog import Catalog


def test_msf_options_are_clamped_to_one():
    # Per Ash: cap msf at 1.0 everywhere -- a catalog built (or loaded from
    # JSON) with values above 1.0 should never carry them through to the
    # optimizer, which would otherwise hand them straight to
    # evaluate_bearing (which itself now refuses msf > 1.0).
    cat = Catalog(msf_options=[0.7, 0.9, 1.1, 1.5])
    assert cat.msf_options == [0.7, 0.9, 1.0]
