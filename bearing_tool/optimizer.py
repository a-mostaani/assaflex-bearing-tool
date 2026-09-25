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

`msf` (see Catalog.msf_options) is handled similarly to `ts` but isn't
solved for analytically -- unlike `ts`, it changes what the strain/capacity
checks themselves allow, not just downstream geometry, so it has to be
probed via real evaluate_bearing() calls. It's cheap in practice: for each
of the 5 geometry dimensions above, candidate msf values are tried smallest
(safest) first and the search stops at the first one that's feasible, so a
geometry that's already feasible at the smallest msf costs exactly one
extra evaluate_bearing() call, not len(msf_options) of them -- only a
geometry that needs a larger msf (or is infeasible at every value) costs
more, up to len(msf_options) calls.

If your catalog grows much larger than the default and search time becomes a
problem, the natural next step is a proper heuristic (simulated annealing /
coordinate search seeded from this grid's best point) rather than a finer
grid -- flagged here rather than built pre-emptively.
"""

from __future__ import annotations

import time
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

    # The lowest vertical load this bearing could plausibly see in service
    # (kN) -- for the Type B vs Type C anti-slip check, see
    # bearing_tool.schedule.BearingSchedule.min_vertical_kN (same concept,
    # same "None = not stated, so 0 is assumed and always reported" rule --
    # see find_optimal_design below and BearingResult.min_vertical_load).
    min_vertical_kN: Optional[float] = None


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
    # The msf actually used to make this candidate feasible (see
    # Catalog.msf_options) -- always recorded, even when the caller pinned
    # a single msf explicitly, so it's visible in every result rather than
    # only when it was searched.
    msf: float = 0.7

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
    # What was actually used for the Type B anti-slip check (see
    # DesignRequirement.min_vertical_kN) -- populated on every result, so a
    # caller can always show it, not just when a design was found.
    min_vertical_kN_used: float = 0.0
    min_vertical_assumed_zero: bool = False


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

    `mu`/`esl` default to the catalog's process defaults but can be
    overridden per call. `msf` defaults to *searching* `catalog.msf_options`
    (smallest/most conservative first, keeping the smallest one that makes
    each candidate geometry feasible) -- pass an explicit `msf` to pin a
    single value instead (e.g. a client requiring a specific safety factor),
    which skips that search entirely.
    """
    mu = catalog.mu if mu is None else mu
    esl = catalog.esl if esl is None else esl
    msf_candidates = [msf] if msf is not None else sorted(catalog.msf_options)
    # See DesignRequirement.min_vertical_kN -- None means not stated, and
    # per Ash, that's enforced as 0 kN (the conservative assumption) rather
    # than skipped; OptimizationResult.message says so explicitly when it
    # applies (see the "no design" / "found" messages below).
    min_vertical_load_n = (req.min_vertical_kN if req.min_vertical_kN is not None else 0.0) * 1000.0

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
                        #
                        # Check the LARGEST (loosest) msf candidate first,
                        # not the smallest: a geometry infeasible even at the
                        # most permissive msf can't become feasible at a
                        # stricter one either, so this single probe rejects
                        # it at the same cost as before msf became
                        # searchable. Most geometries in a real catalog are
                        # infeasible outright (too small/thin for the load),
                        # so checking smallest-first would pay for every
                        # candidate on every one of those before giving up --
                        # multiplying the whole search by len(msf_candidates)
                        # for no benefit (this is what made the search time
                        # out in production against the default catalog).
                        # Only once we know a geometry passes at the loosest
                        # value is it worth the extra calls to find the
                        # smallest (safest) one that still works.
                        loosest_msf = msf_candidates[-1]
                        probe = evaluate_bearing(
                            w=w, l=l, n=n, ti=ti, ts=catalog.ts_options[0], g=g,
                            mu=mu, bearing_type=catalog.bearing_types[0], esl=esl,
                            ndd=req.ndd, nrd=req.nrd, perc1=req.perc1, perc2=req.perc2,
                            msf=loosest_msf, dl=req.dl, dr=req.dr, dd1=req.dd1, dd2=req.dd2,
                        )
                        if not probe.feasible:
                            continue
                        chosen_msf = loosest_msf
                        for cand_msf in msf_candidates[:-1]:
                            cand_probe = evaluate_bearing(
                                w=w, l=l, n=n, ti=ti, ts=catalog.ts_options[0], g=g,
                                mu=mu, bearing_type=catalog.bearing_types[0], esl=esl,
                                ndd=req.ndd, nrd=req.nrd, perc1=req.perc1, perc2=req.perc2,
                                msf=cand_msf, dl=req.dl, dr=req.dr, dd1=req.dd1, dd2=req.dd2,
                            )
                            if cand_probe.feasible:
                                chosen_msf = cand_msf
                                probe = cand_probe
                                break
                        feasible_count += 1

                        chosen_ts = _smallest_sufficient_ts(catalog, probe.min_ts)
                        if chosen_ts is None:
                            continue  # no catalog shim is thick enough

                        for bearing_type in catalog.bearing_types:
                            # min_vertical_load is deliberately omitted from
                            # the msf-search probes above (they run against
                            # a placeholder bearing_type before the real one
                            # is known -- see this module's docstring) and
                            # only applied here, on the real bearing_type,
                            # so the anti-slip check can correctly reject
                            # Type B for a geometry while still finding it
                            # feasible via Type C.
                            final = evaluate_bearing(
                                w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                                mu=mu, bearing_type=bearing_type, esl=esl,
                                ndd=req.ndd, nrd=req.nrd, perc1=req.perc1,
                                perc2=req.perc2, msf=chosen_msf, dl=req.dl, dr=req.dr,
                                dd1=req.dd1, dd2=req.dd2,
                                min_vertical_load=min_vertical_load_n,
                            )
                            if not final.feasible or not final.ts_ok:
                                continue

                            cand = Candidate(
                                w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                                bearing_type=bearing_type, result=final, msf=chosen_msf,
                            )
                            top.append(cand)
                            top.sort(key=lambda c: c.total_volume)
                            del top[top_n:]

    min_vertical_assumed_zero = req.min_vertical_kN is None
    min_vertical_kN_used = min_vertical_load_n / 1000.0

    if not top:
        return OptimizationResult(
            requirement=req,
            combinations_evaluated=evaluated,
            feasible_count=feasible_count,
            min_vertical_kN_used=min_vertical_kN_used,
            min_vertical_assumed_zero=min_vertical_assumed_zero,
            message=(
                "No design in the catalog satisfies this requirement. Widen the "
                "catalog (larger plan_max, more ti/n options) or double-check the "
                "requirement values."
                + (" (No minimum vertical load was stated -- 0 kN was assumed "
                   "for the Type B/Type C check.)" if min_vertical_assumed_zero else "")
            ),
        )

    best = top[0]
    return OptimizationResult(
        requirement=req,
        best=best,
        alternatives=top[1:],
        combinations_evaluated=evaluated,
        feasible_count=feasible_count,
        min_vertical_kN_used=min_vertical_kN_used,
        min_vertical_assumed_zero=min_vertical_assumed_zero,
        message=(
            f"Found {feasible_count} feasible design(s) out of {evaluated:,} evaluated."
            + (" No minimum vertical load was stated -- 0 kN was assumed for the "
               "Type B/Type C check." if min_vertical_assumed_zero else "")
        ),
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
    combinations_evaluated: int = 0  # geometries actually checked (not schedule rows)
    feasible_count: int = 0          # of those checked
    message: str = ""
    # Geometries in the envelope before bounding; the ones not checked were
    # skipped because they could not beat the designs already found.
    geometries_in_envelope: int = 0
    timed_out: bool = False
    # Mirrors OptimizationResult's fields of the same name -- populated even
    # when no design was found, so a caller can always show what was used
    # for the Type B anti-slip check (see BearingSchedule.min_vertical_kN).
    # `best_check.min_vertical_kN_used`/`.min_vertical_assumed_zero` carry
    # the same information when a design WAS found; these are here so it's
    # available without a `best_check` too.
    min_vertical_kN_used: float = 0.0
    min_vertical_assumed_zero: bool = False


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
    time_budget_s: Optional[float] = None,
) -> ScheduleOptimizationResult:
    """Search the catalog for the minimum-total-volume design that passes
    EVERY combination in `schedule` (see BearingSchedule.check_all).

    If `schedule.msf` is set to a specific number, every check uses exactly
    that value (unchanged from before this became searchable). If it's
    None, each candidate geometry is checked against `catalog.msf_options`
    (smallest/safest first), keeping the smallest value that makes it
    feasible -- see Catalog.msf_options.

    `time_budget_s`, if given, stops the search once that many seconds have
    passed and reports it (`timed_out=True`) instead of running on -- a
    backstop for the public API so a pathological request fails visibly
    rather than hanging until the client disconnects. Any design returned
    after a timeout is the best found so far, not a proven optimum.
    """
    started = time.monotonic()
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

    msf_candidates = [schedule.msf] if schedule.msf is not None else sorted(catalog.msf_options)

    ts_min_catalog = min(catalog.ts_options)

    # Branch-and-bound over total volume. Every geometry's volume is at
    # least w * l * (its height with the thinnest catalog shim) -- an exact
    # lower bound, since the real ts can only be thicker (see
    # _analytic_min_height). Enumerating geometries cheapest-bound-first
    # means that once `top` holds top_n feasible designs, any geometry whose
    # bound already exceeds the worst of them can't make the list, and
    # neither can anything after it -- so the search stops there instead of
    # running the full schedule check on every remaining geometry. This
    # returns exactly the same designs, in the same order, as checking every
    # geometry (ties are broken by the original nested-loop order via
    # `seq`); it just skips work that could never change the answer.
    #
    # Before this, every geometry in the envelope got a full check_all(), so
    # a submission with a wide envelope (e.g. no height cap) spent minutes
    # checking large, obviously-not-optimal pads and hit the public API's
    # request timeout in production.
    geoms = []
    seq = 0
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
                            geoms.append((w * l * min_height, seq, w, l, g, ti, n, bearing_type))
                            seq += 1
    geoms.sort()

    deadline = (started + time_budget_s) if time_budget_s else None
    timed_out = False

    top: List[Candidate] = []
    top_checks: List[ScheduleCheckResult] = []  # parallel to `top`
    top_seq: List[int] = []                     # parallel to `top`, tie-breaker
    evaluated = 0
    feasible_count = 0
    # Rows tried in this order; whichever row rejects a geometry moves to the
    # front, since it usually rejects its neighbours too. Only affects speed.
    order = list(range(len(schedule.combinations)))

    for i, (bound, gseq, w, l, g, ti, n, bearing_type) in enumerate(geoms):
        if len(top) >= top_n and bound > top[-1].total_volume:
            break  # nothing from here on can beat the current top_n
        if deadline is not None and (i & 255) == 0 and time.monotonic() > deadline:
            timed_out = True
            break
        evaluated += 1

        # Check the loosest msf candidate first, not the smallest -- a
        # geometry infeasible at the loosest value can't pass at a stricter
        # one, and most geometries are infeasible, so this rejects them in
        # one pass instead of len(msf_candidates) passes.
        loosest_msf = msf_candidates[-1]
        check = schedule.check_all(w=w, l=l, n=n, ti=ti, ts=ts_min_catalog, g=g,
                                   bearing_type=bearing_type, msf=loosest_msf,
                                   fail_fast=True, order=order)
        if not check.feasible:
            fi = check.failed_index
            if fi is not None and order[0] != fi:
                order.remove(fi)
                order.insert(0, fi)
            continue
        chosen_msf = loosest_msf
        for cand_msf in msf_candidates[:-1]:
            c = schedule.check_all(w=w, l=l, n=n, ti=ti, ts=ts_min_catalog, g=g,
                                   bearing_type=bearing_type, msf=cand_msf,
                                   fail_fast=True, order=order)
            if c.feasible:
                check = c
                chosen_msf = cand_msf
                break
        feasible_count += 1

        chosen_ts = ts_min_catalog
        if check.required_min_ts and check.required_min_ts > ts_min_catalog:
            chosen_ts = _smallest_sufficient_ts(catalog, check.required_min_ts)
            if chosen_ts is None:
                continue  # no catalog shim is thick enough

        # ts doesn't affect any strain/capacity formula (see solver.py), only
        # overal_height/volume/ts_ok -- so a single extra call with the real
        # ts is enough here, no need to re-run check_all. chosen_msf (never
        # None) is used rather than schedule.msf, which is None whenever msf
        # was searched.
        final = evaluate_bearing(
            w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
            mu=schedule.mu, bearing_type=bearing_type,
            esl=schedule.esl, ndd=1, nrd=1, perc1=0, perc2=0,
            msf=chosen_msf, dl=0, dr=0, dd1=0, dd2=0,
        )
        if final.overal_height is None:
            continue
        if schedule.max_height_mm is not None and final.overal_height > schedule.max_height_mm:
            continue  # the real (thicker) shim pushed height over the cap

        cand = Candidate(w=w, l=l, n=n, ti=ti, ts=chosen_ts, g=g,
                         bearing_type=bearing_type, result=final, msf=chosen_msf)
        top.append(cand)
        top_checks.append(check)
        top_seq.append(gseq)
        idxs = sorted(range(len(top)), key=lambda k: (top[k].total_volume, top_seq[k]))[:top_n]
        top = [top[k] for k in idxs]
        top_checks = [top_checks[k] for k in idxs]
        top_seq = [top_seq[k] for k in idxs]

    schedule_min_vertical_assumed_zero = schedule.min_vertical_kN is None
    schedule_min_vertical_kN_used = (
        schedule.min_vertical_kN if schedule.min_vertical_kN is not None else 0.0
    )

    zero_note_nf = (" (No minimum vertical load was stated -- 0 kN was assumed "
                    "for the Type B/Type C check.)" if schedule_min_vertical_assumed_zero else "")
    if timed_out and not top:
        return ScheduleOptimizationResult(
            schedule_label=schedule.label,
            combinations_evaluated=evaluated,
            feasible_count=feasible_count,
            geometries_in_envelope=len(geoms),
            timed_out=True,
            min_vertical_kN_used=schedule_min_vertical_kN_used,
            min_vertical_assumed_zero=schedule_min_vertical_assumed_zero,
            message=(
                f"The search stopped after {time_budget_s:.0f}s without finding a "
                f"design ({evaluated:,} of {len(geoms):,} geometries checked). Narrow "
                "the envelope (maximum plan dimensions and height) and try again."
                + zero_note_nf
            ),
        )
    if not top:
        return ScheduleOptimizationResult(
            schedule_label=schedule.label,
            combinations_evaluated=evaluated,
            feasible_count=feasible_count,
            geometries_in_envelope=len(geoms),
            min_vertical_kN_used=schedule_min_vertical_kN_used,
            min_vertical_assumed_zero=schedule_min_vertical_assumed_zero,
            message=(
                "No design in the catalog satisfies every combination in this "
                "schedule within its envelope. Widen the catalog (more ti/n/g "
                "options) or double-check the schedule values."
                + (" (No minimum vertical load was stated -- 0 kN was assumed "
                   "for the Type B/Type C check.)" if schedule_min_vertical_assumed_zero else "")
            ),
        )

    return ScheduleOptimizationResult(
        schedule_label=schedule.label,
        best=top[0],
        best_check=top_checks[0],
        alternatives=top[1:],
        combinations_evaluated=evaluated,
        feasible_count=feasible_count,
        geometries_in_envelope=len(geoms),
        timed_out=timed_out,
        min_vertical_kN_used=schedule_min_vertical_kN_used,
        min_vertical_assumed_zero=schedule_min_vertical_assumed_zero,
        message=(
            (f"Search stopped after {time_budget_s:.0f}s -- this is the best design "
             f"found so far, not a proven optimum. Narrowing the envelope will let "
             f"the search finish. " if timed_out else "")
            + f"Checked {evaluated:,} of {len(geoms):,} geometries in the envelope "
            f"(smallest first; the rest could not beat the designs found); "
            f"{feasible_count} satisfied all {len(schedule.combinations)} combinations."
            + (" No minimum vertical load was stated -- 0 kN was assumed for the "
               "Type B/Type C check." if schedule_min_vertical_assumed_zero else "")
        ),
    )
