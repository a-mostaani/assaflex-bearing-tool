"""
Assembles the "Calculation Document" -- content matching AssaFlex's own
mechanical-properties report format (see the reference PDF this was modeled
on: a basic-design-parameters block, a mechanical-properties block, the
capacity surface plot, and standard test/notes boilerplate).

Everything here is derived from a single ``evaluate_bearing`` call in "both
free" mode (``dl=dr=dd1=dd2=0``, single-direction ``ndd=nrd=1``) -- exactly
how ``lrd_surface.m`` itself calls the solver -- plus the capacity surface
from ``surface.py``. See ``bearing_tool/solver.py``'s ``BearingResult`` for
where each figure below actually comes from.

Deliberately NOT reproduced: the reference document's damping ratio (xi).
Nothing in this codebase models a lead core/hysteretic behavior, so there is
no real figure to put there -- omitted rather than fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .solver import BearingResult, evaluate_bearing
from .surface import CapacitySurface, capacity_surface

DEFAULT_PRODUCT_LABEL = "Reinforced Elastomeric Bearing"

# AssaFlex's own standard boilerplate for their calculation documents
# (transcribed verbatim from the reference document this format is modeled
# on). The only case-specific number in the first bullet -- the test load --
# is computed per document, not hardcoded (see `build_calculation_document`).
TESTS_CONDUCTED_INTRO = (
    "All the manufactured bearings are tested up to 120% of the Maximum "
    "design load announced by Assamrof official documents regarding the "
    "bearing pad in request."
)
TESTS_CONDUCTED_BULLETS = [
    "The bearing pads have been visually tested and observed when being "
    "under the 120% of Maximum design load and they have remained free of "
    "any kind of cracks, deformations, splits, bonding failure or misplaced "
    "reinforcements which are considered to be defects based on "
    "EN-1337-3-4.3.3.3.",
    "10% of samples of bearing pads will be tested under shear force in "
    "case of buyer's request. The bearing pads have been tested under "
    "standard format of EN-1337-3 shear modulus test method (Annex F). "
    "Based on this test the G modulus of Assamrof Elastomer and bearing "
    "pads is calculated and given in official documents. In this test "
    "enough force to deform bearing pad up to maximum vectorial shear "
    "deflection and the bearing pad samples should remain defect free "
    "based on the definitions of defect for this type of test mentioned in "
    "EN-1337-3-4.3.1.1.",
]

GENERAL_NOTES = [
    "All the given values are only valid for AssaFlex products where the "
    "mechanical properties of their ingredients and special manufacturing "
    "procedures completely make changes in calculations and their results.",
    "Vertical Deflection any assumption made in the procedure of "
    "calculations are mentioned for each type of bearing. The Modulus of "
    "Elasticity is considered to be 2000MPa for all type of bearings and "
    "the plan area of steel reinforcements for each bearing is deemed to "
    "be (a-30)*(b-30) mm² which means that in each bearing a "
    "side-Elastomer-cover with 15 mm thickness is considered.",
    "Total Vertical Deflection of a bearing may vary minus or plus 15% of "
    "the Estimation which is given above and where this parameter is "
    "critical to design of the structure, the stiffness of the bearing "
    "should be ascertained by tests.",
    "Maximum allowable rotation in the above table is calculated to avoid "
    "the uplift even in the minimum permitted vertical load.",
    "AssaFlex Engineering Department will be pleased to tailor Bearings to "
    "meet your needs and requirements in a more cost effective manner, if "
    "it has access enough details of your project.",
]

BEARING_TYPE_LABELS = {2: "Type B", 3: "Type C"}


@dataclass
class CalculationDocument:
    # Header
    client_name: str
    project_name: str
    product_label: str
    w: float
    l: float
    h: Optional[float]

    # Basic design parameters (as given)
    n: int
    ts: float
    ti: float
    g: float
    mu: float
    msf: float
    bearing_type: float

    # Mechanical properties (computed)
    envelope: BearingResult
    max_vectorial_shear_deflection: Optional[float]  # Vx,d (mm)
    max_load_design: Optional[float]  # Fz,design (N)
    max_load_buckling: Optional[float]  # Fz,max (N)
    min_load_no_slip: Optional[float]  # Fz,min (N)
    max_rotation: Optional[float]  # alpha_a,d (rad)
    max_vertical_deflection: Optional[float]  # vz,d = vc (mm)
    max_horizontal_load: Optional[float]  # Rxy (N)

    test_load: Optional[float]  # 120% of Fz,design (N)

    surface: CapacitySurface

    tests_conducted: list = field(default_factory=lambda: list(TESTS_CONDUCTED_BULLETS))
    general_notes: list = field(default_factory=lambda: list(GENERAL_NOTES))

    @property
    def bearing_type_label(self) -> str:
        return BEARING_TYPE_LABELS.get(self.bearing_type, str(self.bearing_type))

    @property
    def title(self) -> str:
        dims = f"{self.w:.0f}x{self.l:.0f}" + (f"x{self.h:.0f}" if self.h else "")
        return f"The Mechanical Properties of {self.product_label} {dims}"


def build_calculation_document(
    w: float,
    l: float,
    n: int,
    ti: float,
    ts: float,
    g: float,
    mu: float,
    bearing_type: float,
    msf: float,
    *,
    esl: int = 0,
    client_name: str = "",
    project_name: str = "",
    product_label: str = DEFAULT_PRODUCT_LABEL,
    resolution: int = 100,
) -> CalculationDocument:
    """Builds the full calculation-document content for one bearing geometry.

    ``client_name``/``project_name`` are free text for the header (e.g. "To be
    announced to <client_name>, for the project <project_name>" on the
    reference document) -- leave blank to omit that line.
    """
    envelope = evaluate_bearing(
        w=w, l=l, n=n, ti=ti, ts=ts, g=g, mu=mu, bearing_type=bearing_type,
        esl=esl, ndd=1, nrd=1, perc1=0.0, perc2=0.0, msf=msf,
        dl=0, dr=0, dd1=0, dd2=0,
    )

    surface = capacity_surface(
        w=w, l=l, n=n, ti=ti, ts=ts, g=g, mu=mu, bearing_type=bearing_type,
        msf=msf, esl=esl, resolution=resolution,
    )

    test_load = (
        1.2 * envelope.max_load if envelope.max_load is not None else None
    )

    return CalculationDocument(
        client_name=client_name,
        project_name=project_name,
        product_label=product_label,
        w=w, l=l, h=envelope.overal_height,
        n=n, ts=ts, ti=ti, g=g, mu=mu, msf=msf, bearing_type=bearing_type,
        envelope=envelope,
        max_vectorial_shear_deflection=envelope.max_vec_shear_def,
        max_load_design=envelope.max_load,
        max_load_buckling=envelope.buckling_load_capacity,
        min_load_no_slip=envelope.min_load,
        max_rotation=envelope.max_ang_w,
        max_vertical_deflection=envelope.max_ver_def_alwd,
        max_horizontal_load=envelope.max_hor_f,
        test_load=test_load,
        surface=surface,
    )
