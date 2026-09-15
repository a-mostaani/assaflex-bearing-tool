"""Tests for the capacity-surface sweep (bearing_tool.surface), the Python
port of lrd_surface.m's main loop."""

import numpy as np
import pytest

from bearing_tool.surface import capacity_surface

COMMON = dict(w=400, l=500, n=6, ti=10, ts=3, g=1.0, mu=0.3, bearing_type=2, msf=0.7)


def test_grid_shape_and_axis_bounds():
    surface = capacity_surface(**COMMON, resolution=12)

    assert surface.displacement.shape == (12,)
    assert surface.rotation.shape == (12,)
    assert surface.load.shape == (12, 12)

    # Axes are swept from a small step up to the bearing's own full envelope
    # (a fresh dl=dr=dd1=dd2=0 "both free" solve), not an arbitrary range.
    assert surface.displacement[-1] == pytest.approx(surface.max_displacement)
    assert surface.rotation[-1] == pytest.approx(surface.max_rotation)
    assert surface.displacement[0] > 0
    assert surface.rotation[0] > 0

    assert np.all(np.isfinite(surface.load))
    assert np.all(surface.load > 0)


def test_load_decreases_with_displacement_and_rotation():
    # More demanded displacement/rotation should never increase how much
    # load-free capacity is left over -- the surface should slope downward
    # away from the origin corner, matching the reference document's plot.
    surface = capacity_surface(**COMMON, resolution=12)

    assert surface.load[0, 0] >= surface.load[-1, 0]
    assert surface.load[0, 0] >= surface.load[0, -1]
    assert surface.load[0, 0] >= surface.load[-1, -1]
