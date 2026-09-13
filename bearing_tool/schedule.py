"""
Client bearing schedules (EN 1337-1:2000 Table 1 format).

A real client schedule states several coincident (vertical load, transverse
load, longitudinal load, displacement, rotation) design points -- typically
one per limit state (SLS/ULS/ALS) per governing direction (Max Vertical, Min
Vertical, Max Longitudinal, Max Transverse, Max Displacement, Max Rotation)
-- plus a maximum bearing envelope. A design must satisfy EVERY one of those
points, not just the independent maximum of each quantity: taking
independent maxima produces an envelope that is neither a safe substitute (a
real combination's numbers combine differently) nor a fair one (it can look
infeasible when every real combination would actually pass, or vice versa in
scenarios with non-trivial coupling). See ``BearingSchedule.check_all``.

DISPLACEMENT AND ROTATION: reversible + irreversible, then vector sum
-----------------------------------------------------------------------
EN 1337-3's shear-strain check (5.3.3.3) wants, for each combination, the
*total* design displacement in each direction (irreversible + reversible
already summed -- see the per-row "coincident_displacement_mm"/breakdown
figures, which the client's drawing already gives as totals), combined
across directions as a vector magnitude. ``LoadCombination`` carries both
axis totals (``long_displacement_mm``, ``trans_displacement_mm``) and
``evaluate_bearing`` itself computes that vector magnitude internally
(``max_vec_shear_def = sqrt(dd1**2 + dd2**2)`` in ``solver.py``) -- this
module's job is only to hand both totals through, never to re-derive or
re-combine them itself.

Rotation is NOT combined the same way. The strain formula weights the two
rotation components by *different* plan dimensions
(``max_ang_w * ap**2 + max_ang_l * bp**2``), so a Euclidean vector magnitude
of the two rotations would not match EN 1337-3's own combination. The solver
also doesn't accept two independent rotation values directly -- only a
dominant rotation (``dr``) plus a *ratio* (``perc2``) applied to it when
``nrd=2``. Because that relationship is linear (``max_ang_l = max_ang_w *
perc2``), any known (dominant, secondary) rotation pair can still be fed in
exactly by setting ``perc2 = secondary / dominant`` -- which is what
``LoadCombination.transverse_rotation_mrad`` is for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional

from .solver import BearingResult, evaluate_bearing

LimitState = Literal["SLS", "ULS", "ALS"]
_LIMIT_STATES: tuple = ("SLS", "ULS", "ALS")


@dataclass
class LoadCombination:
    """One coincident design point from a client's bearing schedule.

    ``long_displacement_mm``/``trans_displacement_mm`` are the *total*
    (irreversible + reversible already summed) design displacement in each
    direction, coincident at this design point -- both may be nonzero at
    once (e.g. a schedule's "Max Rotation" row commonly states a small
    coincident displacement in both directions). ``evaluate_bearing`` itself
    vector-sums them; this class just carries both through.

    ``rotation_mrad`` is the dominant (longitudinal-bending) rotation --
    this tool's ``dr``. ``transverse_rotation_mrad`` is an optional, much
    smaller coincident rotation about the other axis, when the schedule
    states one (most rows don't). See the module docstring for why this is
    handled as a ratio (``perc2``) rather than a second vector component.
    """

    limit_state: LimitState
    case: str  # e.g. "Max Vertical", "Min Vertical", "Max Longitudinal", "Max Transverse", "Max Displacement", "Max Rotation"
    vertical_kN: float
    transverse_kN: float = 0.0
    longitudinal_kN: float = 0.0
    long_displacement_mm: float = 0.0
    trans_displacement_mm: float = 0.0
    rotation_mrad: float = 0.0
    transverse_rotation_mrad: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.limit_state} / {self.case}"

    def to_solver_kwargs(self, msf: float) -> dict:
        dl = self.vertical_kN * 1000.0  # kN -> N
        dr = self.rotation_mrad / 1000.0  # mrad -> rad
        dd1 = self.long_displacement_mm
        dd2 = self.trans_displacement_mm
        ndd = 2 if (dd1 and dd2) else 1

        # A stated secondary rotation is reproduced exactly via the ratio
        # perc2 = secondary / dominant, since max_ang_l = max_ang_w * perc2
        # is linear (see module docstring). Not applicable if there's no
        # dominant rotation to scale from.
        if self.transverse_rotation_mrad and self.rotation_mrad:
            nrd = 2
            perc2 = self.transverse_rotation_mrad / self.rotation_mrad
        else:
            nrd = 1
            perc2 = 0.0

        return dict(dl=dl, dr=dr, dd1=dd1, dd2=dd2, ndd=ndd, nrd=nrd,
                    perc1=0.0, perc2=perc2, msf=msf)


@dataclass
class CombinationCheck:
    combination: LoadCombination
    result: BearingResult

    @property
    def passed(self) -> bool:
        return self.result.feasible


@dataclass
class ScheduleCheckResult:
    feasible: bool
    checks: List[CombinationCheck] = field(default_factory=list)
    required_min_ts: Optional[float] = None  # max over all combinations' min_ts

    @property
    def failures(self) -> List[CombinationCheck]:
        return [c for c in self.checks if not c.passed]


@dataclass
class BearingSchedule:
    label: str = ""
    combinations: List[LoadCombination] = field(default_factory=list)

    # Maximum envelope from the schedule (mm). None = no limit from the
    # schedule (fall back to the manufacturing catalog's own range).
    max_longitudinal_mm: Optional[float] = None  # bounds w
    max_transverse_mm: Optional[float] = None  # bounds l
    max_height_mm: Optional[float] = None

    # Process parameters this schedule was written against.
    mu: float = 0.3
    msf: float = 0.7
    esl: int = 0

    def check_all(self, w: float, l: float, n: int, ti: float, ts: float,
                   g: float, bearing_type: float) -> ScheduleCheckResult:
        """Check a candidate geometry against every combination. All must pass."""
        checks: List[CombinationCheck] = []
        min_ts_values: List[float] = []
        for combo in self.combinations:
            kwargs = combo.to_solver_kwargs(self.msf)
            r = evaluate_bearing(w=w, l=l, n=n, ti=ti, ts=ts, g=g, mu=self.mu,
                                  bearing_type=bearing_type, esl=self.esl, **kwargs)
            checks.append(CombinationCheck(combination=combo, result=r))
            if r.min_ts is not None:
                min_ts_values.append(r.min_ts)

        feasible = all(c.passed for c in checks) and bool(checks)
        required_min_ts = max(min_ts_values) if min_ts_values else None
        return ScheduleCheckResult(feasible=feasible, checks=checks,
                                    required_min_ts=required_min_ts)

    def as_dict(self) -> dict:
        """Plain-dict form of this schedule, in the shape from_json() reads back."""
        return {
            "label": self.label,
            "max_longitudinal_mm": self.max_longitudinal_mm,
            "max_transverse_mm": self.max_transverse_mm,
            "max_height_mm": self.max_height_mm,
            "mu": self.mu,
            "msf": self.msf,
            "esl": self.esl,
            "combinations": [
                {
                    "limit_state": c.limit_state, "case": c.case,
                    "vertical_kN": c.vertical_kN, "transverse_kN": c.transverse_kN,
                    "longitudinal_kN": c.longitudinal_kN,
                    "long_displacement_mm": c.long_displacement_mm,
                    "trans_displacement_mm": c.trans_displacement_mm,
                    "rotation_mrad": c.rotation_mrad,
                    "transverse_rotation_mrad": c.transverse_rotation_mrad,
                }
                for c in self.combinations
            ],
        }

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.as_dict(), indent=2))

    @classmethod
    def from_json(cls, path: str | Path) -> "BearingSchedule":
        data = json.loads(Path(path).read_text())
        combos = [LoadCombination(**c) for c in data.get("combinations", [])]
        return cls(
            label=data.get("label", ""), combinations=combos,
            max_longitudinal_mm=data.get("max_longitudinal_mm"),
            max_transverse_mm=data.get("max_transverse_mm"),
            max_height_mm=data.get("max_height_mm"),
            mu=data.get("mu", 0.3), msf=data.get("msf", 0.7), esl=data.get("esl", 0),
        )

    @classmethod
    def from_client_schedule_json(cls, path: str | Path) -> "BearingSchedule":
        """Load the richer client-schedule JSON shape (see schedules/*.json,
        transcribed directly from a client's EN 1337-1 Table 1 drawing) and
        flatten it to the simpler combinations list this class works with.

        Two kinds of rows become combinations:

        1. The main ``combinations`` list -- one governing row per limit
           state per force direction (Max/Min Vertical, Max Longitudinal,
           Max Transverse). Each carries a single displacement figure,
           which is assigned to whichever axis that row is named for.
        2. The schedule's separate ``displacement_mm``/``rotation_mrad``
           blocks -- the drawing's own "Max Displacement" and "Max
           Rotation" governing rows, each with its own coincident loads
           and (for "Max Rotation") a small coincident transverse rotation.
           These are NOT restatements of the rows above -- their coincident
           loads differ -- and skipping them would mean never checking a
           design against the schedule's actual worst displacement/rotation
           demand. Only added for whichever limit states the schedule
           actually states them for (this format often omits ALS here).
        """
        data = json.loads(Path(path).read_text())
        combos: List[LoadCombination] = []
        for c in data.get("combinations", []):
            case = c["case"]
            if case == "Permanent" or "coincident_rotation_mrad" not in c:
                # A bare sustained-load reference value, not a full coincident
                # (load, displacement, rotation) design point -- nothing to
                # check it against here. (It still matters for e.g. a creep
                # calculation, just not for this solver's feasibility check.)
                continue
            vertical = c.get("vertical_kN", c.get("coincident_vertical_kN", 0.0))
            transverse = c.get("transverse_kN", c.get("coincident_transverse_kN", 0.0))
            longitudinal = c.get("longitudinal_kN", c.get("coincident_longitudinal_kN", 0.0))
            disp = c.get("coincident_displacement_mm", 0.0)
            is_transverse_case = case == "Max Transverse"
            combos.append(LoadCombination(
                limit_state=c["limit_state"], case=case,
                vertical_kN=vertical, transverse_kN=transverse,
                longitudinal_kN=longitudinal,
                long_displacement_mm=0.0 if is_transverse_case else disp,
                trans_displacement_mm=disp if is_transverse_case else 0.0,
                rotation_mrad=c.get("coincident_rotation_mrad", 0.0),
            ))

        for ls in _LIMIT_STATES:
            disp_row = data.get("displacement_mm", {}).get(ls)
            if isinstance(disp_row, dict) and "total_max_longitudinal_incl_irreversible" in disp_row:
                combos.append(LoadCombination(
                    limit_state=ls, case="Max Displacement",
                    vertical_kN=disp_row.get("coincident_vertical_kN", 0.0),
                    transverse_kN=disp_row.get("coincident_transverse_kN", 0.0),
                    longitudinal_kN=disp_row.get("coincident_longitudinal_kN", 0.0),
                    long_displacement_mm=disp_row["total_max_longitudinal_incl_irreversible"],
                    trans_displacement_mm=disp_row.get("coincident_transverse", 0.0),
                    rotation_mrad=disp_row.get("coincident_rotation_mrad", 0.0),
                ))

            rot_row = data.get("rotation_mrad", {}).get(ls)
            if isinstance(rot_row, dict) and "total_max_longitudinal_incl_irreversible" in rot_row:
                combos.append(LoadCombination(
                    limit_state=ls, case="Max Rotation",
                    vertical_kN=rot_row.get("coincident_vertical_kN", 0.0),
                    transverse_kN=rot_row.get("coincident_transverse_kN", 0.0),
                    longitudinal_kN=rot_row.get("coincident_longitudinal_kN", 0.0),
                    long_displacement_mm=rot_row.get("coincident_longitudinal_disp_mm", 0.0),
                    trans_displacement_mm=rot_row.get("coincident_transverse_disp_mm", 0.0),
                    rotation_mrad=rot_row["total_max_longitudinal_incl_irreversible"],
                    transverse_rotation_mrad=rot_row.get("coincident_transverse", 0.0),
                ))

        env = data.get("maximum_bearing_dimensions_mm", {})
        upper = env.get("upper_surface", {})
        return cls(
            label=data.get("job", data.get("bearing_mark", "")),
            combinations=combos,
            max_longitudinal_mm=upper.get("longitudinal"),
            max_transverse_mm=upper.get("transverse"),
            max_height_mm=env.get("overall_height"),
        )
