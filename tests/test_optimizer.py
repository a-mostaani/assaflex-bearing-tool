"""Tests for the optimal-design search (bearing_tool.optimizer)."""

from bearing_tool.catalog import Catalog
from bearing_tool.optimizer import DesignRequirement, find_optimal_design
from bearing_tool.solver import evaluate_bearing


SMALL_CATALOG = Catalog(
    plan_min=150, plan_max=450, plan_step=25,
    n_min=2, n_max=10,
    ti_options=[8, 10, 12, 16],
    ts_options=[2, 3, 4, 5, 6, 8],
    g_options=[1.0],
    bearing_types=[2, 3],
)


def test_finds_feasible_design_and_it_independently_validates():
    req = DesignRequirement(dl=250_000, dr=0.006, dd1=12, dd2=0)
    res = find_optimal_design(req, SMALL_CATALOG)

    assert res.best is not None
    assert res.feasible_count > 0

    b = res.best
    # The winning candidate must independently re-validate through the plain
    # solver -- the optimizer must never report a design it didn't actually
    # check end-to-end. Re-check with b.msf (the value the optimizer says it
    # actually used), not a fixed assumed value -- msf is itself searched
    # (see Catalog.msf_options), so the winning candidate isn't necessarily
    # at any one particular msf.
    check = evaluate_bearing(
        w=b.w, l=b.l, n=b.n, ti=b.ti, ts=b.ts, g=b.g, mu=SMALL_CATALOG.mu,
        bearing_type=b.bearing_type, esl=SMALL_CATALOG.esl, ndd=req.ndd,
        nrd=req.nrd, perc1=req.perc1, perc2=req.perc2, msf=b.msf,
        dl=req.dl, dr=req.dr, dd1=req.dd1, dd2=req.dd2,
    )
    assert check.feasible
    assert check.ts_ok
    assert abs(check.total_volume - b.total_volume) < 1e-6


def test_best_is_no_larger_than_any_alternative_returned():
    req = DesignRequirement(dl=250_000, dr=0.006, dd1=12, dd2=0)
    res = find_optimal_design(req, SMALL_CATALOG, top_n=5)
    volumes = [res.best.total_volume] + [c.total_volume for c in res.alternatives]
    assert volumes == sorted(volumes)


def test_impossible_requirement_reports_infeasible_cleanly():
    # A requirement no bearing in this tiny catalog could ever satisfy.
    req = DesignRequirement(dl=500_000_000, dr=0.5, dd1=500, dd2=0)
    res = find_optimal_design(req, SMALL_CATALOG)
    assert res.best is None
    assert res.feasible_count == 0
    assert "No design" in res.message


def test_oversized_catalog_is_rejected_before_searching():
    huge = Catalog(plan_min=100, plan_max=5000, plan_step=5, n_min=1, n_max=100,
                    max_combinations=1000)
    req = DesignRequirement(dl=100_000)
    res = find_optimal_design(req, huge)
    assert res.best is None
    assert "exceeds the safety cap" in res.message


def test_msf_is_searched_and_unlocks_designs_a_fixed_low_msf_cannot():
    # A requirement chosen to be infeasible at the smallest msf option but
    # feasible at a larger one -- demonstrates the search actually widens
    # what's findable, which is the whole point of making msf searchable
    # (see Catalog.msf_options) rather than one fixed process constant.
    low_msf_catalog = Catalog(
        plan_min=150, plan_max=450, plan_step=25, n_min=2, n_max=10,
        ti_options=[8, 10, 12, 16], ts_options=[2, 3, 4, 5, 6, 8],
        g_options=[1.0], bearing_types=[2, 3], msf_options=[0.7],
    )
    wide_msf_catalog = Catalog(
        plan_min=150, plan_max=450, plan_step=25, n_min=2, n_max=10,
        ti_options=[8, 10, 12, 16], ts_options=[2, 3, 4, 5, 6, 8],
        g_options=[1.0], bearing_types=[2, 3], msf_options=[0.7, 0.85, 1.0],
    )
    # A large design rotation demand (dr, rad): in "check" mode (dl and dr
    # both nonzero) the total strain itself is independent of msf, but the
    # strain limit it's checked against is `msf * 7` (see solver.py) -- so a
    # large enough dr pushes every geometry in the catalog's search space
    # over the msf=0.7 limit (4.9) while staying under the msf=1.0 limit
    # (7.0) for at least one geometry. Found empirically by sweeping dr
    # against find_optimal_design() directly (not a hand-guessed literal) --
    # 0.9 sits with margin on both sides of that boundary (infeasible for
    # every geometry from dr=0.8 upward at msf=0.7, feasible again from
    # dr<=0.75 downward), so it isn't fragile to small solver changes.
    req = DesignRequirement(dl=250_000, dr=0.9, dd1=12, dd2=0)
    strict = find_optimal_design(req, low_msf_catalog)
    wide = find_optimal_design(req, wide_msf_catalog)
    assert strict.best is None, (
        "test setup assumption failed: this requirement needs to be "
        "infeasible at msf=0.7 alone for this test to demonstrate anything -- "
        "adjust dr if the solver's formulas changed."
    )
    assert wide.best is not None
    assert wide.best.msf > 0.7


def test_explicit_msf_override_pins_a_single_value_not_a_search():
    # Passing msf= explicitly must behave exactly as before this became
    # searchable: only that one value is ever tried.
    req = DesignRequirement(dl=250_000, dr=0.006, dd1=12, dd2=0)
    res = find_optimal_design(req, SMALL_CATALOG, msf=0.7)
    assert res.best is not None
    assert res.best.msf == 0.7


# ---------------------------------------------------------------------------
# min_vertical_kN / Type B anti-slip check (see solver.evaluate_bearing's
# min_vertical_load and DesignRequirement.min_vertical_kN). The important
# thing to prove here isn't just that the check rejects Type B -- it's that
# it does so WITHOUT wrongly rejecting the whole geometry, since the
# msf-search probes run against a placeholder bearing_type
# (catalog.bearing_types[0]) before the real one is tried (see
# find_optimal_design's comments).
# ---------------------------------------------------------------------------

def test_zero_min_vertical_load_rejects_type_b_but_finds_type_c():
    # A pure-rotation demand with no vertical load at all: friction has
    # nothing to work with, so Type B (bearing_type=2, this catalog's first
    # and therefore the probe's placeholder type) must be rejected for
    # every geometry, yet Type C should still be found -- proving the
    # rejection doesn't also throw away geometries that ARE feasible via
    # Type C.
    req = DesignRequirement(dl=0, dr=0.006, dd1=0, dd2=0, min_vertical_kN=0)
    res = find_optimal_design(req, SMALL_CATALOG)
    assert res.best is not None
    assert res.best.bearing_type == 3
    assert all(c.bearing_type == 3 for c in [res.best] + res.alternatives)
    assert res.min_vertical_assumed_zero is False  # explicitly given as 0, not defaulted
    assert res.min_vertical_kN_used == 0.0


def test_unstated_min_vertical_load_is_assumed_zero_and_reported():
    req = DesignRequirement(dl=250_000, dr=0.006, dd1=12, dd2=0)  # min_vertical_kN left at default None
    res = find_optimal_design(req, SMALL_CATALOG)
    assert res.min_vertical_assumed_zero is True
    assert res.min_vertical_kN_used == 0.0
    assert "0 kN was assumed" in res.message


def test_sufficient_min_vertical_load_keeps_type_b_available():
    # Same pure-rotation demand as above, but now with enough stated
    # minimum vertical load that friction alone should cover it -- Type B
    # must become available again (and, being the cheaper/thinner type,
    # should win).
    req = DesignRequirement(dl=0, dr=0.006, dd1=0, dd2=0, min_vertical_kN=2_000)
    res = find_optimal_design(req, SMALL_CATALOG)
    assert res.best is not None
    assert res.best.bearing_type == 2


# ---------------------------------------------------------------------------
# Bounded (smallest-volume-first) schedule search: must return exactly what an
# exhaustive search over every geometry would, just without checking them all.
# ---------------------------------------------------------------------------

def _exhaustive_schedule_top(schedule, catalog, top_n):
    """Reference implementation: full check_all on every geometry, no bounding."""
    from bearing_tool.optimizer import _analytic_min_height, _smallest_sufficient_ts
    msfs = [schedule.msf] if schedule.msf is not None else sorted(catalog.msf_options)
    ts0 = min(catalog.ts_options)
    found = []
    seq = 0
    for w in catalog.plan_values():
        if schedule.max_longitudinal_mm is not None and w > schedule.max_longitudinal_mm:
            continue
        for l in catalog.plan_values():
            if schedule.max_transverse_mm is not None and l > schedule.max_transverse_mm:
                continue
            for g in catalog.g_options:
                for ti in catalog.ti_options:
                    for n in catalog.n_values():
                        for bt in catalog.bearing_types:
                            h = _analytic_min_height(n, ti, ts0, bt)
                            if schedule.max_height_mm is not None and h > schedule.max_height_mm:
                                continue
                            seq += 1
                            chosen = None
                            for m in msfs:
                                c = schedule.check_all(w=w, l=l, n=n, ti=ti, ts=ts0, g=g,
                                                       bearing_type=bt, msf=m)
                                if c.feasible:
                                    chosen = (m, c)
                                    break
                            if chosen is None:
                                continue
                            ts = ts0
                            if chosen[1].required_min_ts and chosen[1].required_min_ts > ts0:
                                ts = _smallest_sufficient_ts(catalog, chosen[1].required_min_ts)
                                if ts is None:
                                    continue
                            height = _analytic_min_height(n, ti, ts, bt)
                            if schedule.max_height_mm is not None and height > schedule.max_height_mm:
                                continue
                            found.append((w * l * height, seq, (w, l, n, ti, ts, g, bt, chosen[0])))
    found.sort()
    return [f[2] for f in found[:top_n]]


def test_bounded_schedule_search_matches_exhaustive_search():
    from bearing_tool.optimizer import find_optimal_design_for_schedule
    from bearing_tool.schedule import BearingSchedule, LoadCombination

    cat = Catalog(plan_min=150, plan_max=400, plan_step=50, n_min=2, n_max=8,
                  ti_options=[8, 10, 12], ts_options=[2, 3, 5], g_options=[0.9, 1.15])
    sched = BearingSchedule(
        label="bounded-vs-exhaustive",
        combinations=[
            LoadCombination(limit_state="ULS", case="Max Vertical", vertical_kN=900,
                            longitudinal_kN=30, transverse_kN=10,
                            long_displacement_mm=12, rotation_mrad=4),
            LoadCombination(limit_state="SLS", case="Max Rotation", vertical_kN=500,
                            longitudinal_kN=10, transverse_kN=5,
                            long_displacement_mm=6, rotation_mrad=7,
                            transverse_rotation_mrad=1),
        ],
        min_vertical_kN=300,
    )
    expected = _exhaustive_schedule_top(sched, cat, top_n=5)
    assert expected, "test schedule should have feasible designs"

    res = find_optimal_design_for_schedule(sched, cat, top_n=5)
    got = [(c.w, c.l, c.n, c.ti, c.ts, c.g, c.bearing_type, c.msf)
           for c in [res.best] + res.alternatives]
    assert got == expected
    # And it actually skipped work.
    assert res.combinations_evaluated < res.geometries_in_envelope
    # The winner's per-combination check is complete and in schedule order.
    assert [c.combination.case for c in res.best_check.checks] == \
        [c.case for c in sched.combinations]
    assert all(c.passed for c in res.best_check.checks)


def test_schedule_search_time_budget_stops_and_reports():
    from bearing_tool.optimizer import find_optimal_design_for_schedule
    from bearing_tool.schedule import BearingSchedule, LoadCombination

    sched = BearingSchedule(
        label="impossible",
        combinations=[LoadCombination(limit_state="ULS", case="Max Vertical",
                                      vertical_kN=1e6, rotation_mrad=1)],
    )
    res = find_optimal_design_for_schedule(sched, Catalog(), time_budget_s=0.01)
    assert res.timed_out
    assert res.best is None
    assert "stopped after" in res.message
