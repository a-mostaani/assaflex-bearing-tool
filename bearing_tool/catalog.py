"""
Editable manufacturing catalog: the discrete/ranged choices the optimizer is
allowed to pick from when searching for a design.

Every value here is a placeholder default, not an AssaFlex manufacturing
spec -- correct them to match your actual process before trusting the
optimizer's output. They are deliberately kept in one small, JSON-loadable
place (rather than hardcoded in the optimizer) so they can be tightened or
loosened later without touching the search logic itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Catalog:
    # Plan dimensions (w = longitudinal, l = transverse), in mm.
    plan_min: float = 150.0
    plan_max: float = 1000.0
    plan_step: float = 25.0

    # Number of inner elastomer layers to try (n+1 steel reinforcements).
    # EN 1337-3 Table 3's "standard sizes" (bearing_tool.en1337_tables.
    # TABLE_3_TYPE_B_SIZES) top out at n=11 (for a 900x900 bearing) -- this
    # default range is deliberately wider than that (a real design between
    # standard sizes, or larger than the table's biggest row, can need more
    # layers), not narrower.
    n_min: int = 2
    n_max: int = 30

    # Standard inner elastomer layer thicknesses (mm). The four values that
    # appear in EN 1337-3 Table 3 (bearing_tool.en1337_tables.
    # TABLE_3_TYPE_B_SIZES) are 8/12/16/20mm -- 10 and 14mm are kept here too
    # as in-between options for a non-standard plan size, since the table's
    # exact (a, b) pairs are nominal reference sizes, not the only sizes a
    # real bearing may use (see that table's own docstring). Confirm against
    # AssaFlex's actual sheet/mold stock.
    ti_options: List[float] = field(default_factory=lambda: [8, 10, 12, 14, 16, 20])

    # Standard steel shim thicknesses (mm) available to satisfy the 5.3.3.5
    # minimum-thickness check. Per Ash: 10mm is already a rarely-needed
    # upper end in practice, so that's the default ceiling here -- PLACEHOLDER
    # otherwise, confirm against actual steel plate stock. (`ts` never
    # affects feasibility, only overall height/volume and the 5.3.3.5 check
    # itself -- see optimizer.py -- so this list only needs to reach as high
    # as a real job would ever require, not act as a safety margin.)
    ts_options: List[float] = field(default_factory=lambda: [2, 3, 4, 5, 6, 8, 10])

    # Elastomer shear modulus grades (N/mm^2) -- PLACEHOLDER values in the
    # range EN 1337-3 commonly uses for different IRHD hardness grades;
    # confirm which grade(s) AssaFlex actually stocks.
    g_options: List[float] = field(default_factory=lambda: [0.9, 1.0, 1.15])

    # Bearing types to consider. Type 2.5 (B/C) is excluded by default: the
    # original tool's overal_height formula for it references an undefined
    # variable (see solver.py docstring) and needs a confirmed formula first.
    bearing_types: List[float] = field(default_factory=lambda: [2, 3])

    # Fixed process parameters (rarely varied per-job, but still editable).
    mu: float = 0.3
    esl: int = 0

    # Candidate values for `msf` -- how much of EN 1337-3's maximum permitted
    # strain/movement capacity a design is allowed to use (see solver.py;
    # msf=1.0 uses the standard's full stated allowance, smaller values are
    # progressively more conservative). This used to be a single fixed
    # process constant (0.7) -- per Ash, that's not always the right amount
    # of margin to insist on, so it's now itself a search dimension: for
    # each candidate geometry, the optimizer (bearing_tool.optimizer) tries
    # these from smallest (safest) to largest and keeps the smallest one
    # that makes that geometry feasible, recording which value was actually
    # used on the returned Candidate so it's visible, not hidden, in the
    # result. A caller that still wants one fixed value everywhere (e.g. a
    # client contract that specifies it) can pass an explicit `msf=` to
    # find_optimal_design / set BearingSchedule.msf, which skips this search
    # entirely -- see optimizer.py and schedule.py. PLACEHOLDER range,
    # confirm against what AssaFlex is actually willing to sign off on.
    msf_options: List[float] = field(default_factory=lambda: [0.7, 0.8, 0.9, 1.0])

    # Safety valve: hard cap on how many (w, l, ti, n, g, type) combinations
    # the optimizer will evaluate in one run, so a very loose catalog can't
    # make a search hang. ~1e6 combinations run in well under a minute.
    max_combinations: int = 3_000_000

    def __post_init__(self) -> None:
        # msf > 1.0 exceeds EN 1337-3's own stated allowance (see solver.py,
        # which refuses it outright) -- clamped here too so a catalog loaded
        # from JSON, edited in the UI, or constructed directly in a script
        # can never smuggle one through to the optimizer. Per Ash: cap msf
        # at 1.0 everywhere.
        clamped = sorted({min(v, 1.0) for v in self.msf_options})
        self.msf_options = clamped

    def plan_values(self) -> List[float]:
        vals = []
        v = self.plan_min
        while v <= self.plan_max + 1e-9:
            vals.append(round(v, 3))
            v += self.plan_step
        return vals

    def n_values(self) -> List[int]:
        return list(range(self.n_min, self.n_max + 1))

    def estimated_combinations(self) -> int:
        p = len(self.plan_values())
        return p * p * len(self.ti_options) * len(self.n_values()) * \
            len(self.g_options) * len(self.bearing_types)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def from_json(cls, path: str | Path) -> "Catalog":
        data = json.loads(Path(path).read_text())
        return cls(**data)


def default_catalog() -> Catalog:
    return Catalog()
