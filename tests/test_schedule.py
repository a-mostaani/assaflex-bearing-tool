"""Tests for bearing_tool.schedule and the schedule-driven optimizer."""

from math import isclose
from pathlib import Path

from bearing_tool.catalog import Catalog, default_catalog
from bearing_tool.optimizer import find_optimal_design_for_schedule
from bearing_tool.schedule import BearingSchedule, LoadCombination
from bearing_tool.solver import evaluate_bearing

REPO_ROOT = Path(__file__).resolve().parent.parent
H3428_PATH = REPO_ROOT / "schedules" / "H3428_A0_A5_bearing_1.1.json"


def test_loads_real_client_schedule():
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)
    # "Permanent" has no coincident rotation/displacement -- must be excluded.
    assert all(c.case != "Permanent" for c in sched.combinations)
    # 9 force-governed rows (Max/Min Vertical, Max Longitudinal, Max Transverse)
    # + a "Max Displacement" row for each limit state that states one (SLS, ULS,
    # ALS all do) + a "Max Rotation" row for each limit state that states one
    # (SLS, ULS only -- this schedule has no ALS rotation-governed row) --
    # 9 + 3 + 2 = 14.
    assert len(sched.combinations) == 14
    assert sched.max_longitudinal_mm == 450
    assert sched.max_transverse_mm == 600
    assert sched.max_height_mm == 100
    # Spot-check one force-governed row end to end.
    uls_max_long = next(c for c in sched.combinations
                         if c.limit_state == "ULS" and c.case == "Max Longitudinal")
    assert uls_max_long.longitudinal_kN == 121
    assert uls_max_long.long_displacement_mm == 35
    assert uls_max_long.trans_displacement_mm == 0
    assert uls_max_long.rotation_mrad == 5.24


def test_loads_the_governing_displacement_and_rotation_rows():
    """These rows are transcribed in the JSON's own displacement_mm/rotation_mrad
    blocks with DIFFERENT coincident loads than the "Max Longitudinal" row that
    happens to share the same displacement/rotation magnitude -- they must be
    checked as their own, separate combinations, not folded into an existing one.
    """
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)

    uls_max_disp = next(c for c in sched.combinations
                         if c.limit_state == "ULS" and c.case == "Max Displacement")
    assert uls_max_disp.long_displacement_mm == 35
    assert uls_max_disp.trans_displacement_mm == 5
    assert uls_max_disp.vertical_kN == 907  # differs from Max Longitudinal's 886
    assert uls_max_disp.longitudinal_kN == 20  # differs from Max Longitudinal's 121

    uls_max_rot = next(c for c in sched.combinations
                        if c.limit_state == "ULS" and c.case == "Max Rotation")
    assert uls_max_rot.rotation_mrad == 6.67  # higher than any force-governed ULS row (5.24)
    assert uls_max_rot.transverse_rotation_mrad == 1.13
    assert uls_max_rot.vertical_kN == 1150
    assert uls_max_rot.long_displacement_mm == 33
    assert uls_max_rot.trans_displacement_mm == 5

    # ALS states a governing displacement row (with its own coincident loads)
    # but no governing rotation row.
    als_max_disp = next(c for c in sched.combinations
                         if c.limit_state == "ALS" and c.case == "Max Displacement")
    assert als_max_disp.long_displacement_mm == 14
    assert als_max_disp.trans_displacement_mm == 24
    assert als_max_disp.vertical_kN == 734
    assert not any(c.limit_state == "ALS" and c.case == "Max Rotation"
                   for c in sched.combinations)


def test_transverse_rotation_ratio_reproduces_the_stated_value():
    """perc2 = transverse/dominant must make the solver's derived max_ang_l
    come out to exactly the transverse rotation figure that was stated."""
    combo = LoadCombination(limit_state="ULS", case="Max Rotation", vertical_kN=1150,
                             rotation_mrad=6.67, transverse_rotation_mrad=1.13)
    kwargs = combo.to_solver_kwargs(msf=0.7)
    assert kwargs["nrd"] == 2
    dr = kwargs["dr"]
    perc2 = kwargs["perc2"]
    assert isclose(dr * perc2 * 1000, 1.13, rel_tol=1e-9)  # back in mrad


def test_displacement_axes_are_vector_summed_not_added():
    """Feeding both axes should match evaluate_bearing's own sqrt(dd1**2+dd2**2)
    -- schedule.py must not pre-combine them itself."""
    combo = LoadCombination(limit_state="ULS", case="Max Rotation", vertical_kN=1150,
                             long_displacement_mm=33, trans_displacement_mm=5,
                             rotation_mrad=6.67)
    kwargs = combo.to_solver_kwargs(msf=0.7)
    assert kwargs["dd1"] == 33
    assert kwargs["dd2"] == 5
    assert kwargs["ndd"] == 2


def test_check_all_matches_individual_evaluate_bearing_calls():
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)
    w, l, n, ti, ts, g, bt = 400, 550, 8, 10, 4, 1.0, 2

    # This schedule's own msf is None (search), so pin an explicit value here
    # -- check_all's None-fallback behaviour is exercised elsewhere; this test
    # only cares that check_all's per-combination results match a direct
    # evaluate_bearing() call at whatever msf is actually used.
    used_msf = 0.7
    result = sched.check_all(w=w, l=l, n=n, ti=ti, ts=ts, g=g, bearing_type=bt, msf=used_msf)
    assert len(result.checks) == len(sched.combinations)

    for check in result.checks:
        kwargs = check.combination.to_solver_kwargs(used_msf)
        direct = evaluate_bearing(w=w, l=l, n=n, ti=ti, ts=ts, g=g, mu=sched.mu,
                                   bearing_type=bt, esl=sched.esl, **kwargs)
        assert direct.feasible == check.passed
        assert direct.total_strain_i == check.result.total_strain_i


def test_a_combination_that_fails_makes_the_whole_schedule_infeasible():
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)
    # A tiny, thin bearing should fail at least the ULS Max Vertical combo.
    result = sched.check_all(w=150, l=150, n=2, ti=8, ts=2, g=1.0, bearing_type=2)
    assert not result.feasible
    assert len(result.failures) > 0


SMALL_CATALOG = Catalog(
    plan_min=150, plan_max=600, plan_step=25,
    n_min=2, n_max=10,
    ti_options=[8, 10, 12, 16],
    ts_options=[2, 3, 4, 5, 6, 8],
    g_options=[1.0, 1.15],
    bearing_types=[2, 3],
)


def test_schedule_optimizer_finds_a_design_that_independently_validates():
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)
    res = find_optimal_design_for_schedule(sched, SMALL_CATALOG)

    assert res.best is not None
    b = res.best

    # Stays within the schedule's own envelope.
    assert b.w <= sched.max_longitudinal_mm
    assert b.l <= sched.max_transverse_mm
    assert b.result.overal_height <= sched.max_height_mm

    # Independently re-validate against every combination from scratch, using
    # b.msf (the value the optimizer actually used to find this design) --
    # msf is itself searched (see Catalog.msf_options), so re-checking at a
    # fixed assumed value would be wrong whenever the search picked a
    # different one.
    check = sched.check_all(w=b.w, l=b.l, n=b.n, ti=b.ti, ts=b.ts, g=b.g,
                             bearing_type=b.bearing_type, msf=b.msf)
    assert check.feasible
    assert all(c.passed for c in check.checks)


def test_schedule_optimizer_alternatives_are_not_smaller_than_best():
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)
    res = find_optimal_design_for_schedule(sched, SMALL_CATALOG, top_n=4)
    volumes = [res.best.total_volume] + [c.total_volume for c in res.alternatives]
    assert volumes == sorted(volumes)


def test_impossible_schedule_reports_infeasible_cleanly():
    huge_load = LoadCombination(limit_state="ULS", case="Max Vertical",
                                 vertical_kN=500_000, long_displacement_mm=10,
                                 rotation_mrad=5)
    sched = BearingSchedule(label="impossible", combinations=[huge_load],
                             max_longitudinal_mm=450, max_transverse_mm=600,
                             max_height_mm=100)
    res = find_optimal_design_for_schedule(sched, SMALL_CATALOG)
    assert res.best is None
    assert "No design" in res.message


def test_envelope_smaller_than_catalog_minimum_is_reported():
    tiny_envelope = BearingSchedule(
        label="tiny", combinations=[LoadCombination(limit_state="ULS", case="Max Vertical",
                                                      vertical_kN=100, long_displacement_mm=5,
                                                      rotation_mrad=2)],
        max_longitudinal_mm=100, max_transverse_mm=100,  # below SMALL_CATALOG.plan_min=150
    )
    res = find_optimal_design_for_schedule(tiny_envelope, SMALL_CATALOG)
    assert res.best is None
    assert "envelope" in res.message.lower()


def test_json_round_trip(tmp_path):
    sched = BearingSchedule.from_client_schedule_json(H3428_PATH)
    out = tmp_path / "roundtrip.json"
    sched.to_json(out)
    reloaded = BearingSchedule.from_json(out)
    assert len(reloaded.combinations) == len(sched.combinations)
    assert reloaded.max_longitudinal_mm == sched.max_longitudinal_mm
