"""
Optimal bearing pad design search.

The MATLAB tool this was ported from only ever answers "what can this
geometry take" or "does this geometry satisfy this demand" -- it never picks
a geometry for you (see its own "To Be Developed" note #2 at the bottom of
des_reinf_bearing_bsi_test_2.m). This module is the new piece: given a
client's performance requirements (design load / rotation / displacement),
it searches the manufacturing catalog (bearing_tool.catalog.Catalog) for the
design that satisfies EN 1337-3 (via bearing_tool.solver.evaluate_bearing in
"check mode") with the smallest total material volume.

APPROACH
--------
This is a brute-force search over the catalog's discrete grid, not a
gradient/analytic optimum -- deliberately, since the underlying feasibility
region (EN 1337-3 strain limits) is not convex in these variables and a
closed-form optimum is not obvious. It is fast enough to brute-force in
practice: `ts` (steel shim thickness) never affects feasibility (it only
appears in the 5.3.3.5 reinforcement check and in overall height/volume), so
it is solved for analytically per candidate rather than searched, which cuts
the search from 6 dimensions to 5. At default catalog settings that is on
the order of 10^6 evaluations, taking single-digit seconds in pure Python
(see benchmarks in tests/test_optimizer.py).

If your catalog grows much larger than the default and search time becomes a
problem, the natural next step is a proper heuristic (simulated annealing /
coordinate search seeded from this grid's best point) rather than a finer
grid -- flagged here rather than built pre-emptively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .catalog import Catalog
from .schedule import BearingSchedule, ScheduleCheckResult
from .solver import BearingResult, evaluate_bearing


@dataclass
class DesignRequirement:
    """A client's stated performance criteria for one bearing pad.

    Field names deliberately mirror bearing_tool.solver.evaluate_bearing's
    dl/dr/dd1/dd2/ndd/nrd/perc1/perc2 so a requirements table can be mapped
    straight across.
    """

    dl: float  # required design vertical load (N)
    dr: float = 0.0  # required design rotation (rad)
    dd1: float = 0.0  # required design longitudinal displacement (mm)
    dd2: float = 0.0  # required design transverse displacement (mm)
    ndd: int = 1  # number of displacement directions (1 or 2)
    nrd: int = 1  # number of rotation directions (1 or 2)
    perc1: float = 0.0  # transverse/longitudinal displacement ratio (if ndd=2)
    perc2: float = 0.0  # transverse/longitudinal rotation ratio (if nrd=2)
    label: str = ""  # optional identifier, e.g. a client's row/support number


@dataclass
class Candidate:
    w: float
    l: float
    n: int
    ti: float
    ts: float
    g: float
    bearing_type: float
    result: BearingResult

    @property
    def total_volume(self) -> Optional[float]:
        return self.result.total_volume

    @property
    def plan_area(self) -> Optional[float]:
        return self.result.plan_area


@dataclass
class OptimizationResult:
    requirement: DesignRequirement
    best: Optional[Candidate] = None
    alternatives: List[Candidate] = field(default_factory=list)  # next-best, for comparison
    combinations_evaluated: int = 0
    feasible_count: int = 0
    message: str = ""


def _smallest_sufficient_ts(catalog: Catalog, min_ts: float) -> Optional[float]:
    sufficient = [t for t in catalog.ts_options if t >= min_ts]
    return min(sufficient) if sufficient else None


def find_optimal_design(
    req: DesignRequirement,
    catalog: Catalog,
    mu: Optional[float] = None,
    msf: Optional[float] = None,
    esl: Optional[int] = None,
    top_n: int = 5,
) -> OptimizationResult:
    """Search the catalog for the minimum-total-volume design that satisfies `req`.

    `mu`/`msf`/`esl` default to the catalog's process defaults but can be
    overridden per call (e.g. a client requiring a non-standard safety factor).
    """
    mu = catalog.mu if mu is None else mu
    msf = catalog.msf if msf is None else msf
    esl = catalog.esl if esl is None else esl

    plan_values = catalog.plan_values()
    n_values = catalog.n_values()

    n_combos = (
        len(plan_values) ** 2
        * len(catalog.ti_options)
        * len(n_values)
        * len(catalog.g_options)
        * len(catalog.bearing_types)
    )
    if n_combos > catalog.max_combinations:
        return OptimizationResult(
            requirement=req,
            message=(
                f"Catalog defines {n_combos:,} combinations, which exceeds the "
                f"safety cap of {catalog.max_combinations:,}. Narrow the catalog "
                "(smaller plan range/step, fewer ti/n/g/type options) and retry."
            ),
        )

    best: Optional[Candidate] = None
    top: List[Candidate] = []  # kept sorted ascending by total_volume, capped at top_n
    evaluated = 0
    feasible_count = 0

    for w in plan_values:
        for l in plan_values:
            for g in catalog.g_options:
                for ti in catalog.ti_options:
                    for n in n_values:
                        evaluated += 1
                        # First pass: cheapest ts placeholder just to learn
                        # feasibility and the required min_ts (ts does not
                        # affect either the strain checks or min_ts itself).
                        probe = evaluate_bearing(
                            w=w, l=l, n=n, ti=ti, ts=catalog.ts_options[0], g=g,
                            mu=mu, bearing_type=catalog.bearing_types[0], esl=esl,
                            ndd=req.ndd, nrd=req.nrd, perc1=req.perc1, perc2=req.perc2,
                            msf=msf, dl=req.dl, dr=req.dr, dd1=req.dd1, dd2=req.dd2,
                        )
                        if not probe.feasible:
                            continue
                        feasible_count += 1

                        chosen_ts = _smallest_sufficient_ts(catalog, probe.min_ts)
                        if chosen_ts is None:
                            continue  # no catalog shim is thick enough

                        for bearing_type in catalog.bearing_types:
                            final = evaluate_bearing(
                                w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                                mu=mu, bearing_type=bearing_type, esl=esl,
                                ndd=req.ndd, nrd=req.nrd, perc1=req.perc1,
                                perc2=req.perc2, msf=msf, dl=req.dl, dr=req.dr,
                                dd1=req.dd1, dd2=req.dd2,
                            )
                            if not final.feasible or not final.ts_ok:
                                continue

                            cand = Candidate(
                                w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                                bearing_type=bearing_type, result=final,
                            )
                            top.append(cand)
                            top.sort(key=lambda c: c.total_volume)
                            del top[top_n:]

    if not top:
        return OptimizationResult(
            requirement=req,
            combinations_evaluated=evaluated,
            feasible_count=feasible_count,
            message=(
                "No design in the catalog satisfies this requirement. Widen the "
                "catalog (larger plan_max, more ti/n options) or double-check the "
                "requirement values."
            ),
        )

    best = top[0]
    return OptimizationResult(
        requirement=req,
        best=best,
        alternatives=top[1:],
        combinations_evaluated=evaluated,
        feasible_count=feasible_count,
        message=f"Found {feasible_count} feasible design(s) out of {evaluated:,} evaluated.",
    )


# ---------------------------------------------------------------------------
# Schedule-driven design: given a full client bearing schedule (every
# combination must pass, per BearingSchedule.check_all), search the catalog
# for the minimum-volume design, respecting the schedule's own max envelope
# in preference to the catalog's generic plan-size range.
# ---------------------------------------------------------------------------

@dataclass
class ScheduleOptimizationResult:
    schedule_label: str
    best: Optional[Candidate] = None
    best_check: Optional[ScheduleCheckResult] = None  # per-combination pass/fail for `best`
    alternatives: List[Candidate] = field(default_factory=list)
    combinations_evaluated: int = 0  # geometries tried (not schedule rows)
    feasible_count: int = 0
    message: str = ""


def _analytic_min_height(n: int, ti: float, ts: float, bearing_type: float) -> Optional[float]:
    """overal_height using the smallest allowed ts, without a solver call --
    a cheap, exact (not approximate) lower bound used to skip geometries that
    can never fit the schedule's height cap no matter which ts is chosen.
    Mirrors solver.evaluate_bearing's finalization; returns None for an
    unsupported bearing_type (2.5, or anything else)."""
    if bearing_type == 2:
        return n * ti + (n + 1) * ts + 2 * 2.5
    if bearing_type == 3:
        return n * ti + (n - 1) * ts + 2 * 20
    return None


def find_optimal_design_for_schedule(
    schedule: BearingSchedule,
    catalog: Catalog,
    top_n: int = 5,
) -> ScheduleOptimizationResult:
    """Search the catalog for the minimum-total-volume design that passes
    EVERY combination in `schedule` (see BearingSchedule.check_all)."""
    if not schedule.combinations:
        return ScheduleOptimizationResult(
            schedule_label=schedule.label,
            message="Schedule has no usable load combinations to check against.",
        )

    plan_values = catalog.plan_values()
    w_values = [v for v in plan_values
                if schedule.max_longitudinal_mm is None or v <= schedule.max_longitudinal_mm]
    l_values = [v for v in plan_values
                if schedule.max_transverse_mm is None or v <= schedule.max_transverse_mm]
    if not w_values or not l_values:
        return ScheduleOptimizationResult(
            schedule_label=schedule.label,
            message=(
                "The schedule's maximum envelope is smaller than the catalog's "
                "smallest plan dimension -- lower the catalog's plan_min/plan_step "
                "to search within this envelope."
            ),
        )

    n_values = catalog.n_values()
    n_combos = (len(w_values) * len(l_values) * len(catalog.ti_options)
                * len(n_values) * len(catalog.g_options) * len(catalog.bearing_types))
    if n_combos > catalog.max_combinations:
        return ScheduleOptimizationResult(
            schedule_label=schedule.label,
            message=(
                f"Catalog x envelope defines {n_combos:,} geometries, which exceeds "
                f"the safety cap of {catalog.max_combinations:,}. Narrow the catalog "
                "and retry."
            ),
        )

    ts_min_catalog = min(catalog.ts_options)
    top: List[Candidate] = []
    top_checks: List[ScheduleCheckResult] = []  # parallel to `top`
    evaluated = 0
    feasible_count = 0

    for w in w_values:
        for l in l_values:
            for g in catalog.g_options:
                for ti in catalog.ti_options:
                    for n in n_values:
                        for bearing_type in catalog.bearing_types:
                            min_height = _analytic_min_height(n, ti, ts_min_catalog, bearing_type)
                            if min_height is None:
                                continue  # unsupported type
                            if schedule.max_height_mm is not None and min_height > schedule.max_height_mm:
                                continue  # cannot possibly fit, even with the thinnest shim
                            evaluated += 1

                            check = schedule.check_all(w=w, l=l, n=n, ti=ti,
                                                        ts=ts_min_catalog, g=g,
                                                        bearing_type=bearing_type)
                            if not check.feasible:
                                continue
                            feasible_count += 1

                            chosen_ts = ts_min_catalog
                            if check.required_min_ts and check.required_min_ts > ts_min_catalog:
                                chosen_ts = _smallest_sufficient_ts(catalog, check.required_min_ts)
                                if chosen_ts is None:
                                    continue  # no catalog shim is thick enough

                            # ts doesn't affect any strain/capacity formula (see
                            # solver.py), only overal_height/volume/ts_ok -- so a
                            # single extra call with the real ts is enough here,
                            # no need to re-run check_all.
                            final = evaluate_bearing(
                                w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                                mu=schedule.mu, bearing_type=bearing_type,
                                esl=schedule.esl, ndd=1, nrd=1, perc1=0, perc2=0,
                                msf=schedule.msf, dl=0, dr=0, dd1=0, dd2=0,
                            )
                            if final.overal_height is None:
                                continue
                            if schedule.max_height_mm is not None and final.overal_height > schedule.max_height_mm:
                                continue  # the real (thicker) shim pushed height over the cap

                            cand = Candidate(w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                                              bearing_type=bearing_type, result=final)
                            top.append(cand)
                            top_checks.append(check)
                            order = sorted(range(len(top)), key=lambda i: top[i].total_volume)
                            top = [top[i] for i in order][:top_n]
                            top_checks = [top_checks[i] for i in order][:top_n]

    if not top:
        return ScheduleOptimizationResult(
            schedule_label=schedule.label,
            combinations_evaluated=evaluated,
            feasible_count=feasible_count,
            message=(
                "No design in the catalog satisfies every combination in this "
                "schedule within its envelope. Widen the catalog (more ti/n/g "
                "options) or double-check the schedule values."
            ),
        )

    return ScheduleOptimizationResult(
        schedule_label=schedule.label,
        best=top[0],
        best_check=top_checks[0],
        alternatives=top[1:],
        combinations_evaluated=evaluated,
        feasible_count=feasible_count,
        message=f"Found {feasible_count} design(s) satisfying all "
                f"{len(schedule.combinations)} combinations, out of {evaluated:,} "
                f"geometries tried.",
    )
