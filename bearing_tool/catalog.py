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
    n_min: int = 2
    n_max: int = 30

    # Standard inner elastomer layer thicknesses (mm) -- PLACEHOLDER, confirm
    # against AssaFlex's actual sheet/mold stock.
    ti_options: List[float] = field(default_factory=lambda: [8, 10, 12, 14, 16, 20])

    # Standard steel shim thicknesses (mm) available to satisfy the 5.3.3.5
    # minimum-thickness check -- PLACEHOLDER, confirm against actual steel
    # plate stock.
    ts_options: List[float] = field(default_factory=lambda: [2, 3, 4, 5, 6, 8, 10, 12])

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
    msf: float = 0.7
    esl: int = 0

    # Safety valve: hard cap on how many (w, l, ti, n, g, type) combinations
    # the optimizer will evaluate in one run, so a very loose catalog can't
    # make a search hang. ~1e6 combinations run in well under a minute.
    max_combinations: int = 3_000_000

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
