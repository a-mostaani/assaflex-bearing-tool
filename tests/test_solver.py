"""
Regression tests for bearing_tool.solver.evaluate_bearing.

The golden values below were produced by running the ORIGINAL MATLAB file
(reference/des_reinf_bearing_bsi_test_2.m) under Octave 8.4, using the exact
same inputs, and copying its printed outputs verbatim. This is how the port
was validated -- if you change the solver, re-run the matching Octave case
(see tests/octave_check/run_case.m) and update both sides together.

EXCEPTION: `Max_moment` values are NOT taken from Octave. The original
MATLAB hardcodes Ks=78.4 instead of looking up EN 1337-3 Table 4; this port
now does the real lookup (bearing_tool.en1337_tables.rectangular_ks), so
Max_moment is expected to differ slightly from an Octave run and is checked
against an independently hand-computed value instead (see comments below).
See tests/test_en1337_tables.py for direct tests of the lookup itself.
"""

import math

import pytest

from bearing_tool.solver import evaluate_bearing

COMMON = dict(w=400, l=500, n=6, ti=10, ts=3, g=1.0, mu=0.3, bearing_type=2,
              esl=0, ndd=1, nrd=1, perc1=0, perc2=0, msf=0.7)


def assert_close(a, b, rel=1e-6):
    assert a is not None and b is not None
    assert math.isclose(a, b, rel_tol=rel), f"{a} != {b}"


def test_capacity_mode_both_free():
    # Octave: run_case(400,500,6,10,3,1.0,0.3,2,0,1,1,0,0,0.7,0,0,0,0)
    r = evaluate_bearing(**COMMON, dl=0, dr=0, dd1=0, dd2=0)
    assert r.feasible
    assert_close(r.max_ver_def_alwd, 1.998906475)
    assert_close(r.max_vec_shear_def, 42)
    assert_close(r.disp_upperbound, 42)
    assert_close(r.max_load, 2667043.015)
    assert_close(r.min_load, 466666.6667)
    assert_close(r.load_upperbound, 5655214.437)
    assert_close(r.max_ang_w, 0.01578084059)
    assert_close(r.rot_upperbound, 0.01578084059)
    assert_close(r.Max_force_exerted, 140000)
    # Ks from EN 1337-3 Table 4 at b/a=bp/ap=480/380=1.2632 (interpolated
    # between b/a=1.25->79.3 and b/a=1.3->78.4) = 79.0632, not Octave's 78.4.
    assert_close(r.ks_used, 79.06315789473685)
    assert_close(r.Max_moment, 322102806.8427868)
    assert_close(r.overal_height, 86)
    # max_hor_f (AssaFlex's "Rxy") = A*g*max_vec_shear_def/Tq -- min_load is
    # this same quantity divided by mu, so the two must be exactly related.
    assert_close(r.max_hor_f, r.min_load * COMMON["mu"])
    # buckling_load_capacity is captured before the strain-convergence loop
    # narrows max_load down further, so it can only be >= the final max_load
    # (both free) -- see the module docstring on where each is captured.
    assert r.buckling_load_capacity is not None
    assert r.buckling_load_capacity >= r.max_load


def test_check_mode_both_given():
    # Octave: run_case(400,500,6,10,3,1.0,0.3,2,0,1,1,0,0,0.7,300000,0.008,15,0)
    r = evaluate_bearing(**COMMON, dl=300000, dr=0.008, dd1=15, dd2=0)
    assert r.feasible
    assert_close(r.max_ver_def_alwd, 0.2248452459)
    assert_close(r.max_vec_shear_def, 15)
    assert_close(r.max_load, 300000)
    assert_close(r.min_load, 166666.6667)
    assert_close(r.load_upperbound, 6081725.023)
    assert_close(r.max_ang_w, 0.008)
    assert_close(r.rot_upperbound, 0.001775094047)
    assert_close(r.Max_force_exerted, 50000)
    assert_close(r.Max_moment, 163288035.2336573)  # see Ks note above
    assert_close(r.overal_height, 86)
    assert_close(r.max_hor_f, r.min_load * COMMON["mu"])
    # Here buckling_load_capacity is captured in the dl!=0 branch, sharing
    # its first term with the final load_upperbound but combined via max()
    # instead of min() -- so it can only be >= the final load_upperbound.
    assert r.buckling_load_capacity is not None
    assert r.buckling_load_capacity >= r.load_upperbound


def test_rotation_free_mode():
    # Octave: run_case(400,500,6,10,3,1.0,0.3,2,0,1,1,0,0,0.7,300000,0,0,0)
    r = evaluate_bearing(**COMMON, dl=300000, dr=0, dd1=0, dd2=0)
    assert r.feasible
    assert_close(r.max_ver_def_alwd, 0.2248452459)
    assert_close(r.max_load, 300000)
    assert_close(r.max_ang_w, 0.001775094047)
    assert_close(r.rot_upperbound, 0.001775094047)
    assert_close(r.Max_moment, 36231452.40351087)  # see Ks note above


def test_load_free_mode():
    # Octave: run_case(400,500,6,10,3,1.0,0.3,2,0,1,1,0,0,0.7,0,0.006,0,0)
    r = evaluate_bearing(**COMMON, dl=0, dr=0.006, dd1=0, dd2=0)
    assert r.feasible
    assert_close(r.max_ver_def_alwd, 3.011701361)
    assert_close(r.max_load, 4018365.63)
    assert_close(r.max_ang_w, 0.006)
    assert_close(r.rot_upperbound, 0.02377658969)
    assert_close(r.Max_moment, 122466026.42524298)  # see Ks note above


def test_msf_above_one_is_rejected():
    # Per Ash: cap msf at 1.0 everywhere -- EN 1337-3's own strain/
    # displacement limits are msf=1.0's full stated allowance, so anything
    # above that (e.g. AssaFlex's own calculation documents have used
    # msf=1.1) is refused here rather than silently allowed through.
    with pytest.raises(ValueError):
        evaluate_bearing(**{**COMMON, "msf": 1.1}, dl=0, dr=0, dd1=0, dd2=0)


def test_msf_exactly_one_is_allowed():
    r = evaluate_bearing(**{**COMMON, "msf": 1.0}, dl=0, dr=0, dd1=0, dd2=0)
    assert r.feasible


def test_type3_ndd2():
    # Octave: run_case(300,300,10,12,4,1.0,0.3,3,0,2,1,0.3,0,0.7,0,0,0,0)
    r = evaluate_bearing(w=300, l=300, n=10, ti=12, ts=4, g=1.0, mu=0.3,
                          bearing_type=3, esl=0, ndd=2, nrd=1, perc1=0.3,
                          perc2=0, msf=0.7, dl=0, dr=0, dd1=0, dd2=0)
    assert r.feasible
    assert_close(r.max_ver_def_alwd, 5.204519839)
    assert_close(r.max_load, 533164.8911)
    assert_close(r.load_upperbound, 444841.0477)
    assert_close(r.max_ang_w, 0.05576271257)
    assert_close(r.overal_height, 196)


def test_overload_returns_infeasible_gracefully():
    # Octave: run_case(200,200,4,10,3,1.0,0.3,2,0,1,1,0,0,0.7,9000000,0,0,0)
    # In MATLAB/Octave this configuration prints a warning and then ERRORS
    # ("'max_ver_def_alwd' undefined") the moment a caller asks for all 11
    # outputs. Here it must come back as a clean infeasible result instead.
    r = evaluate_bearing(w=200, l=200, n=4, ti=10, ts=3, g=1.0, mu=0.3,
                          bearing_type=2, esl=0, ndd=1, nrd=1, perc1=0,
                          perc2=0, msf=0.7, dl=9000000, dr=0, dd1=0, dd2=0)
    assert not r.feasible
    assert r.failure_reason == "load_exceeds_buckling_capacity"
    assert_close(r.load_upperbound, 351086.4)


def test_shear_deflection_exhausting_plan_dimension_returns_infeasible_gracefully():
    # Found via the schedule optimizer's own search: capacity mode (dl=dr=
    # dd1=dd2=0) sets max_shear_def_w = msf*n*ti, and when that lands on
    # exactly `w` (as it does here: 0.7*25*10 == 175), Ar = A1*(1 - w/w) = 0,
    # which every strain formula a few lines later divides by -- previously
    # an unhandled ZeroDivisionError that crashed the public web API.
    r = evaluate_bearing(w=175, l=775, n=25, ti=10, ts=5, g=1.15, mu=0.3,
                          bearing_type=2, esl=0, ndd=1, nrd=1, perc1=0,
                          perc2=0, msf=0.7, dl=0, dr=0, dd1=0, dd2=0)
    assert not r.feasible
    assert r.failure_reason == "shear_displacement_exceeds_plan_dimension"


def test_type_2point5_raises_not_implemented():
    kwargs = {**COMMON, "bearing_type": 2.5}
    with pytest.raises(NotImplementedError):
        evaluate_bearing(**kwargs, dl=0, dr=0, dd1=0, dd2=0)


def test_invalid_type_raises_value_error():
    kwargs = {**COMMON, "bearing_type": 99}
    with pytest.raises(ValueError):
        evaluate_bearing(**kwargs, dl=0, dr=0, dd1=0, dd2=0)


# ---------------------------------------------------------------------------
# Type B (friction-only) vs Type C (positive fixing): a Type B bearing is
# only adequate if friction (mu * the lowest vertical load it'll ever see)
# can resist the horizontal force its own shear deformation generates
# (BearingResult.min_load) -- see the module docstring's "min_vertical_load"
# parameter. Per Ash: this must be enforced as a real feasibility check, not
# just reported.
# ---------------------------------------------------------------------------

def test_insufficient_min_vertical_load_rejects_type_b():
    # From test_capacity_mode_both_free: this exact COMMON call has
    # min_load=466666.6667 N -- a stated minimum vertical load below that
    # can't satisfy friction alone.
    r = evaluate_bearing(**COMMON, dl=0, dr=0, dd1=0, dd2=0,
                          min_vertical_load=400_000)
    assert not r.feasible
    assert r.failure_reason == "insufficient_min_vertical_load_for_type_b"
    assert r.min_vertical_load == 400_000
    assert any("Type C" in w for w in r.warnings)


def test_sufficient_min_vertical_load_leaves_type_b_feasible():
    r = evaluate_bearing(**COMMON, dl=0, dr=0, dd1=0, dd2=0,
                          min_vertical_load=500_000)
    assert r.feasible
    assert r.min_vertical_load == 500_000


def test_type_c_is_not_subject_to_the_min_vertical_load_check():
    # Same insufficient value that rejects Type B above -- Type C doesn't
    # rely on friction to prevent sliding, so it must be unaffected.
    kwargs = {**COMMON, "bearing_type": 3}
    r = evaluate_bearing(**kwargs, dl=0, dr=0, dd1=0, dd2=0,
                          min_vertical_load=400_000)
    assert r.feasible


def test_min_vertical_load_none_skips_the_check_entirely():
    # Backward compatibility: callers that don't pass min_vertical_load at
    # all (e.g. direct solver use, or the optimizer's msf-search probes,
    # which run against a placeholder bearing_type -- see optimizer.py) get
    # the pre-existing behaviour, unaffected by how low a real min vertical
    # load might be.
    r = evaluate_bearing(**COMMON, dl=0, dr=0, dd1=0, dd2=0)
    assert r.feasible
    assert r.min_vertical_load is None
