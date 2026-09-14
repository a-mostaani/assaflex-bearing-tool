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
