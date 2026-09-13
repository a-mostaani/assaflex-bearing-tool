"""
EN 1337-3 reinforced elastomeric bearing pad solver.

This is a line-by-line Python port of the MATLAB function
``des_reinf_bearing_bsi_test_2.m`` (Assamrof / AssaFlex, see
``reference/des_reinf_bearing_bsi_test_2.m``). Clause references (e.g. "5.3.3.3")
refer to BS EN 1337-3.

WHAT THIS FUNCTION DOES
------------------------
Given a bearing pad geometry and material properties, it either:

1. Computes the bearing's performance envelope (max load / max rotation / max
   shear deflection it can sustain) when the corresponding design demand
   (``dl``, ``dr``, ``dd1``/``dd2``) is left at 0 ("capacity mode"), or
2. Checks whether a given geometry satisfies a *stated* design load, rotation
   and/or displacement demand ("check mode", when ``dl``/``dr``/``dd1``/``dd2``
   are all supplied) -- this is the mode the optimizer in ``optimizer.py`` uses
   as its feasibility test.

DELIBERATE DEVIATIONS FROM THE ORIGINAL MATLAB
-----------------------------------------------
Everything else is translated as-is, including known gaps, and flagged inline
with "KNOWN ISSUE" so they are easy to find. Two behavioral changes were made,
both purely for robustness (they do not change the result of any case that
converges in the original):

* The MATLAB convergence loop resets its iteration counter to 0 on every pass
  (it is declared *inside* the while-loop body), so its ">100 / >200" runaway
  guard can never actually trigger -- a genuinely non-convergent input would
  hang MATLAB forever. Here the counter lives outside the loop, so a
  non-convergent case ends cleanly with ``feasible=False`` and a warning
  instead of hanging.
* Bearing type ``2.5`` (type B/C) computes ``overal_height`` using a variable
  (``n1``) that is never defined anywhere in the original MATLAB file --
  selecting this type would error out in MATLAB too. Rather than guess the
  intended formula for a structural dimension, this port raises a clear
  ``NotImplementedError`` asking for the correct clause/formula from
  AssaFlex before type 2.5 can be used.
* When a supplied design load exceeds the buckling capacity, MATLAB prints a
  warning and returns with several output arguments genuinely unassigned --
  which errors in MATLAB the moment a caller asks for those outputs (verified
  against Octave). Here the same case returns a normal ``BearingResult`` with
  ``feasible=False``, ``failure_reason="load_exceeds_buckling_capacity"``, and
  only the fields the original actually computes before returning -- needed
  so the optimizer can treat this as "infeasible" rather than crash.

All four evaluation modes (capacity-mode with load and/or rotation free, and
full check-mode) plus a type-3 bearing and the overload early-return above
have been cross-checked line-for-line against the original .m file running
under Octave 8.4 -- see ``tests/test_solver.py``.

RESOLVED -- Ks (restoring moment factor): the original hardcoded
``Ks = 78.4`` with the comment "For a/b" instead of looking up EN 1337-3's
own Table 4. As of 2026-09-13, Ash supplied that table (and Annex A's Table
A.1 for elliptical/circular bearings) and it is now wired in via
``bearing_tool.en1337_tables.rectangular_ks`` -- see that module for the
transcribed data and interpolation. Note 78.4 is exactly Table 4's value at
b/a=1.3, which is almost certainly how the placeholder was produced in the
first place (a one-off calculation for a test geometry, left in as a
constant). Elliptical/circular bearings are still not supported by this
solver at all (it assumes a rectangular plan throughout: A=a*b, perimeter
2*(a+b), etc.) -- that would need a parallel geometry path, not just a
different Ks, so Table A.1 is transcribed and ready but unused for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Optional

from .en1337_tables import rectangular_ks


# Original MATLAB hardcoded `Ks=78.4 %For a/b` (line 452/392) instead of
# looking up EN 1337-3 Table 4. Kept only as a fallback label for messages;
# the actual value used is now bearing_tool.en1337_tables.rectangular_ks().
_LEGACY_PLACEHOLDER_KS = 78.4

# Hardcoded in the original tool (line 146): thickness of outer elastomer layers (mm).
OUTER_ELASTOMER_THICKNESS_TO = 2.5

# Hardcoded in the original tool (line 376/423/436): steel yield stress (N/mm^2),
# assumes St-37-0 steel with <16% sulphur.
STEEL_YIELD_STRESS = 235.0

_MAX_ITERATIONS = 500  # robustness fix -- see module docstring


@dataclass
class BearingResult:
    """Everything the solver can report for one geometry/loading combination."""

    feasible: bool = True
    warnings: list = field(default_factory=list)
    failure_reason: Optional[str] = None  # short machine-readable code, or None

    # Core outputs (mirror the MATLAB function's return signature)
    max_ver_def_alwd: Optional[float] = None
    max_vec_shear_def: Optional[float] = None
    disp_upperbound: Optional[float] = None
    max_load: Optional[float] = None
    min_load: Optional[float] = None
    load_upperbound: Optional[float] = None
    max_ang_w: Optional[float] = None
    rot_upperbound: Optional[float] = None
    Max_force_exerted: Optional[float] = None
    Max_moment: Optional[float] = None
    overal_height: Optional[float] = None

    # Extra diagnostics not returned by the MATLAB function but useful for the
    # UI / optimizer (they are what actually decides pass/fail).
    total_strain_i: Optional[float] = None
    total_strain_o: Optional[float] = None
    strain_limit: Optional[float] = None  # msf * 7
    min_ts: Optional[float] = None  # required steel shim thickness
    ts_ok: Optional[bool] = None
    plan_area: Optional[float] = None  # w * l
    total_volume: Optional[float] = None  # plan_area * overal_height
    ks_used: Optional[float] = None  # EN 1337-3 Table 4 restoring moment factor actually used


def evaluate_bearing(
    w: float,
    l: float,
    n: int,
    ti: float,
    ts: float,
    g: float,
    mu: float,
    bearing_type: float,
    esl: int,
    ndd: int,
    nrd: int,
    perc1: float,
    perc2: float,
    msf: float,
    dl: float = 0,
    dr: float = 0,
    dd1: float = 0,
    dd2: float = 0,
) -> BearingResult:
    """Evaluate a reinforced elastomeric bearing against EN 1337-3.

    Parameters mirror the MATLAB function's argument list (``type`` is renamed
    ``bearing_type`` since ``type`` is a Python builtin). See the MATLAB file's
    header comments (also reproduced in ``docs/parameter_reference.md``) for
    the full description of each parameter and its units.

    Set ``dl``/``dr``/``dd1``/``dd2`` to 0 to ask "what is the maximum this
    bearing can take", or to a nonzero design demand to ask "does this bearing
    satisfy this demand".
    """
    res = BearingResult()

    # --- normalize perc1 / perc2 (lines 69-83) ---
    if ndd == 1:
        perc1 = 0
    elif perc1 == 0:
        perc1 = 0.3

    if nrd == 1:
        perc2 = 0
    elif perc2 == 0:
        perc2 = 0.3

    # --- initial max_load / max_ang_w (lines 85-95) ---
    max_load = dl if dl != 0 else 0.0
    max_ang_w = dr if dr != 0 else 0.0

    # --- shear-deflection demand setup (lines 97-113); two independent
    # if/elif statements exactly as in the original, using None sentinels for
    # "not yet decided" so a later stage (below) fills them in. ---
    max_shear_def_w: Optional[float] = None
    max_shear_def_l: Optional[float] = None
    max_vec_shear_def: Optional[float] = None

    if dd1 != 0 and dd2 == 0:
        max_vec_shear_def = dd1
        max_shear_def_w = dd1
        max_shear_def_l = 0.0
    elif dd1 == 0 and dd2 == 0:
        max_vec_shear_def = 0.0

    if dd2 != 0 and dd1 == 0:
        max_vec_shear_def = dd2
        max_shear_def_l = dd2
        max_shear_def_w = 0.0
    elif dd1 != 0 and dd2 != 0:
        max_shear_def_w = dd1
        max_shear_def_l = dd2
        max_vec_shear_def = sqrt(dd1 ** 2 + dd2 ** 2)

    # --- geometry & effective section properties (lines 139-161) ---
    a = w
    b = l
    ap = a - 20
    bp = b - 20
    A = a * b
    A1 = ap * bp
    ip = 2 * (ap + bp)
    to = OUTER_ELASTOMER_THICKNESS_TO

    if esl == 1:
        Tq = n * ti
    elif to <= 2.5:
        # NOTE: `to` is hardcoded to 2.5 above, so this branch is always the
        # one taken when esl != 1 -- the `else` below is unreachable with the
        # current hardcoded `to`, exactly as in the original MATLAB.
        Tq = n * ti
    else:
        Tq = n * ti + 2 * to

    te_i = ti
    te_o = 1.4 * to
    sti3 = n * (ti ** 3) + 2 * (2.5 ** 3)

    s_i = A1 / (ip * te_i)
    s_o = A1 / (ip * te_o)

    # --- 5.3.3.3 design strain due to shear force (lines 184-200) ---
    disp_upperbound = msf * Tq
    if ndd == 1 and dd1 == 0 and dd2 == 0:
        max_shear_def_w = 1 * msf * Tq
        max_vec_shear_def = max_shear_def_w
        max_shear_def_l = 0.0
    elif ndd == 2 and dd1 == 0 and dd2 == 0:
        max_vec_shear_def = 1 * msf * Tq
        max_shear_def_w = max_vec_shear_def / sqrt(perc1 ** 2 + 1)
        max_shear_def_l = perc1 * max_shear_def_w
    elif dd1 != 0 and dd2 != 0:
        if max_vec_shear_def > msf:
            res.warnings.append("Design displacement(s) are above standard value!")

    max_hor_f = A * g * max_vec_shear_def / Tq
    min_load = max_hor_f / mu

    Ar = A1 * (1 - (max_shear_def_w / a) - (max_shear_def_l / b))
    shear_strain_o = max_vec_shear_def / Tq
    shear_strain_i = max_vec_shear_def / Tq

    # --- 5.3.3.6.b stability regarding buckling (lines 212-221) ---
    if dl == 0:
        max_load = max(
            2 * ap * g * s_i * Ar / (3 * (n * ti + 2 * to)),
            min(6 * msf * g * Ar * s_i / 1.5, 6 * msf * g * Ar * s_o / 1.5),
        )
    else:
        load_upperbound = max(
            2 * ap * g * s_i * Ar / (3 * (n * ti + 2 * to)),
            min(6 * msf * g * Ar * s_i / 1.5, 6 * msf * g * Ar * s_o / 1.5),
        )
        if dl >= load_upperbound:
            res.warnings.append(
                "The Designed Load is higher than capacity of this bearing"
            )
            res.feasible = False
            res.failure_reason = "load_exceeds_buckling_capacity"
            res.load_upperbound = load_upperbound
            res.min_load = min_load
            res.disp_upperbound = disp_upperbound
            res.max_vec_shear_def = max_vec_shear_def
            res.plan_area = A
            return res  # matches the MATLAB `return` at line 219 -- several
            # outputs are genuinely never computed on this path in the
            # original either.

    # --- 5.3.3.6.a stability regarding rotation (lines 222-234) ---
    max_ver_def = n * max_load * ti * (1 / (5 * g * s_i ** 2) + 1 / 2000) / A1
    min_ver_def = n * min_load * ti * (1 / (5 * g * s_i ** 2) + 1 / 2000) / A1
    if dr == 0:
        max_ang_w = 3 * max_ver_def / (ap + bp * perc2)
    else:
        rot_upperbound = 3 * max_ver_def / (ap + bp * perc2)
        if dr >= rot_upperbound:
            # Soft warning only in the original -- no early return.
            res.warnings.append(
                "The Designed Rotation would make the bearing unstable"
            )

    max_ang_l = max_ang_w * perc2

    # --- 5.3.3.2 / 5.3.3.4 iterative strain check (lines 236-413) ---
    mode = (
        "both_free" if dl == 0 and dr == 0 else
        "load_free" if dl == 0 and dr != 0 else
        "rotation_free" if dl != 0 and dr == 0 else
        "check"  # dl != 0 and dr != 0
    )

    strain_limit = msf * 7
    total_strain_i = 0.0
    total_strain_o = 0.0
    comp_strain_i = comp_strain_o = rot_strain_i = rot_strain_o = 0.0
    iterations = 0

    while True:
        comp_strain_i = 1.5 * max_load / (g * Ar * s_i)  # 5.3.3.2
        comp_strain_o = 1.5 * max_load / (g * Ar * s_o)
        rot_strain_i = (max_ang_w * ap ** 2 + max_ang_l * bp ** 2) * ti / (2 * sti3)
        rot_strain_o = (max_ang_w * ap ** 2 + max_ang_l * bp ** 2) * to / (2 * sti3)

        if mode == "both_free":
            total_strain_i = comp_strain_i + rot_strain_i + shear_strain_i
            total_strain_o = comp_strain_o + rot_strain_o + shear_strain_o
        else:
            total_strain_i = comp_strain_i + rot_strain_i + (max_vec_shear_def / Tq)
            total_strain_o = comp_strain_o + rot_strain_o + (max_vec_shear_def / Tq)

        if mode == "check":
            # Single-pass check -- no adjustment, matches the dl!=0 & dr!=0
            # branch (lines 343-409): report and stop, whether or not it
            # passes.
            if total_strain_i > strain_limit or total_strain_o > strain_limit:
                res.warnings.append(
                    "The total strain due to combination of Max Load, Max "
                    "Displacement and Max Rotation is above standard "
                    f"(inner={total_strain_i:.3f}, outer={total_strain_o:.3f}, "
                    f"limit={strain_limit:.3f})"
                )
                res.feasible = False
                res.failure_reason = "strain_exceeds_limit"
            else:
                res.warnings.append(
                    "The bearing is well chosen and capable of withstanding "
                    "the total strain in request."
                )
            break

        # modes both_free / load_free / rotation_free: converge via ratio scaling
        exceeded = total_strain_i > strain_limit or total_strain_o > strain_limit
        if mode == "load_free":
            # NOTE: original only tests total_strain_i here (asymmetric quirk
            # of the source, preserved as-is).
            exceeded = total_strain_i > strain_limit

        if not exceeded:
            break

        if total_strain_i > total_strain_o and total_strain_i - strain_limit > 0:
            ratio = total_strain_i / strain_limit
        elif total_strain_o > total_strain_i and total_strain_o - strain_limit > 0:
            ratio = total_strain_o / strain_limit
        else:
            ratio = 1.0

        if mode == "both_free":
            max_load = max_load / ratio
            max_ang_w = max_ang_w / ratio
        elif mode == "rotation_free":  # dl != 0, dr == 0: only rotation adjusted
            max_ang_w = max_ang_w / ratio
        elif mode == "load_free":  # dl == 0, dr != 0: only load adjusted
            max_load = max_load / ratio

        max_ang_l = max_ang_w * perc2

        iterations += 1
        if iterations > _MAX_ITERATIONS:
            res.warnings.append(
                f"Algorithm did not converge after {_MAX_ITERATIONS} iterations "
                f"(mode={mode}, last ratio={ratio:.4f})"
            )
            res.feasible = False
            res.failure_reason = "did_not_converge"
            break

    # --- finalization, common to all modes (lines 415-466) ---
    max_ver_def_alwd = n * max_load * ti * (1 / (5 * g * s_i ** 2) + 1 / 2000) / A1

    load_upperbound = min(
        2 * ap * g * s_i * Ar / (3 * (n * ti + 2 * to)),
        7 * msf * (g * Ar * s_i) / 1.5,
        7 * msf * (g * Ar * s_o) / 1.5,
    )
    rot_upperbound = min(
        3 * max_ver_def_alwd / (ap + bp * perc2),
        7 * msf * (2 * sti3) / ti * ap ** 2,
        7 * msf * (2 * sti3) / to * ap ** 2,
    )

    # Required steel shim thickness (5.3.3.5). The original computes this
    # twice with different formulas (once with an extra *1.4 factor) and the
    # second, simpler formula silently overwrites the first -- only the
    # second one is actually used by the time the function returns, so that
    # is the only one reproduced here.
    min_ts = 1.3 * max_load * (2 * ti) * 2 / (Ar * STEEL_YIELD_STRESS)
    ts_ok = ts >= min_ts
    if ts_ok:
        res.warnings.append(
            f"Steel reinforcement thickness OK (>= required minimum {min_ts:.3f} mm)"
        )
    else:
        res.warnings.append(
            f"Steel reinforcement thickness BELOW required minimum {min_ts:.3f} mm"
        )

    Max_force_exerted = A * g * max_vec_shear_def / (ti * n)

    # EN 1337-3 Table 4 restoring moment factor Ks, by b/a (see
    # en1337_tables.py). Uses the same effective dimensions (ap, bp) already
    # used elsewhere in this Max_moment formula, rather than the raw w/l --
    # a modeling choice inherited from how the original code was structured,
    # not something stated explicitly in the standard; flag it if this ever
    # needs reconciling against a hand calc.
    ks, ks_warning = rectangular_ks(bp / ap)
    if ks_warning:
        res.warnings.append(ks_warning)
    Max_moment = max_ang_w * bp ** 5 * ap / (n * ti ** 3 * ks)

    if bearing_type == 2:
        overal_height = n * ti + (n + 1) * ts + 2 * 2.5
    elif bearing_type == 3:
        res.warnings.append(
            "Make sure that the bearing plate thicknesses are chosen correctly (type C)"
        )
        overal_height = n * ti + (n - 1) * ts + 2 * 20
    elif bearing_type == 2.5:
        raise NotImplementedError(
            "Bearing type 2.5 (type B/C) is not supported: the original MATLAB tool's "
            "overal_height formula for this type references an undefined variable "
            "(`n1`), so it cannot be ported faithfully. Please confirm the correct "
            "EN 1337-3 clause/formula for this type's overall height before it can "
            "be added."
        )
    else:
        raise ValueError("bearing_type should be one of: 2 (type B), 3 (type C).")

    res.max_ver_def_alwd = max_ver_def_alwd
    res.max_vec_shear_def = max_vec_shear_def
    res.disp_upperbound = disp_upperbound
    res.max_load = max_load
    res.min_load = min_load
    res.load_upperbound = load_upperbound
    res.max_ang_w = max_ang_w
    res.rot_upperbound = rot_upperbound
    res.Max_force_exerted = Max_force_exerted
    res.Max_moment = Max_moment
    res.overal_height = overal_height
    res.ks_used = ks

    res.total_strain_i = total_strain_i
    res.total_strain_o = total_strain_o
    res.strain_limit = strain_limit
    res.min_ts = min_ts
    res.ts_ok = ts_ok
    res.plan_area = A
    res.total_volume = A * overal_height

    if res.failure_reason is None and (
        total_strain_i > strain_limit or total_strain_o > strain_limit
    ):
        res.feasible = False
        res.failure_reason = "strain_exceeds_limit"

    return res
