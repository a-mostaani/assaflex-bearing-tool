"""
Capacity surface: the "how much load can this bearing take at every possible
displacement/rotation combination" plot.

Python port of ``reference/lrd_surface.m``'s main loop (the trailing steel-shim
thickness check at the bottom of that file is NOT ported here -- it uses a
different, inconsistent plan-area formula and a hardcoded steel reinforcement
thickness than the one already reconciled into ``solver.evaluate_bearing``'s
own ``min_ts`` (see that module's docstring); it reads as leftover scratch
code from a separate derivation, not the final formula, so reproducing it here
would just reintroduce an inconsistency this codebase already resolved once).

The original MATLAB function calls its own solver
(``des_reinf_bearing_bsi_test_2``) in a nested loop over displacement and
rotation, with the load left free at every grid point ("load_free" mode --
``dl=0``, ``dr``/``dd1`` swept, ``dd2=0``, single-direction ``ndd=nrd=1``,
exactly as the ``.m`` file hardcodes). Here that solver is
``bearing_tool.solver.evaluate_bearing`` -- already validated line-for-line
against the same original MATLAB file (see ``solver.py``'s docstring and
``tests/test_solver.py``), so this module doesn't re-derive any physics, it
only re-creates the sweep.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .solver import evaluate_bearing

DEFAULT_RESOLUTION = 100


@dataclass
class CapacitySurface:
    """The grid: ``load[i, j]`` is the max load (N) at
    ``displacement[i]`` mm shear deflection and ``rotation[j]`` rad rotation.
    """

    displacement: np.ndarray  # shape (resolution,), mm
    rotation: np.ndarray  # shape (resolution,), rad
    load: np.ndarray  # shape (resolution, resolution), N

    # The single-point envelope this grid was swept up to (from the
    # dl=dr=dd1=dd2=0 "both free" call) -- the same numbers reported as
    # Vx,d / alpha_a,d on the calculation document, so the grid's own axis
    # limits are self-describing.
    max_displacement: float
    max_rotation: float


def capacity_surface(
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
    resolution: int = DEFAULT_RESOLUTION,
) -> CapacitySurface:
    """Sweep max load over the full displacement x rotation envelope.

    Mirrors ``lrd_surface.m``: first finds the bearing's own full-envelope
    displacement/rotation bounds (a ``dl=dr=dd1=dd2=0`` "both free" call),
    then re-evaluates the solver at a ``resolution`` x ``resolution`` grid
    spanning those bounds, with load left free ("load_free" mode) at each
    point.
    """
    envelope = evaluate_bearing(
        w=w, l=l, n=n, ti=ti, ts=ts, g=g, mu=mu, bearing_type=bearing_type,
        esl=esl, ndd=1, nrd=1, perc1=0.0, perc2=0.0, msf=msf,
        dl=0, dr=0, dd1=0, dd2=0,
    )
    if envelope.disp_upperbound is None or envelope.max_ang_w is None:
        raise ValueError(
            "Could not establish this bearing's displacement/rotation "
            "envelope (infeasible even at zero rotation/displacement) -- "
            f"failure_reason={envelope.failure_reason}"
        )

    max_displacement = envelope.disp_upperbound
    max_rotation = envelope.max_ang_w

    displacement = np.linspace(
        max_displacement / resolution, max_displacement, resolution
    )
    rotation = np.linspace(max_rotation / resolution, max_rotation, resolution)
    load = np.empty((resolution, resolution))

    for i, dd1 in enumerate(displacement):
        for j, dr in enumerate(rotation):
            point = evaluate_bearing(
                w=w, l=l, n=n, ti=ti, ts=ts, g=g, mu=mu, bearing_type=bearing_type,
                esl=esl, ndd=1, nrd=1, perc1=0.0, perc2=0.0, msf=msf,
                dl=0, dr=dr, dd1=dd1, dd2=0,
            )
            load[i, j] = point.max_load if point.max_load is not None else np.nan

    return CapacitySurface(
        displacement=displacement,
        rotation=rotation,
        load=load,
        max_displacement=max_displacement,
        max_rotation=max_rotation,
    )


def plot_capacity_surface(surface: CapacitySurface, *, title: str | None = None):
    """Renders the 3D surface (displacement x rotation x max load), styled to
    match the AssaFlex calculation-document plot: viridis colormap + colorbar,
    same axis labels/order as the original MATLAB ``surf`` plot.

    Returns a ``matplotlib.figure.Figure`` (caller decides how to display/
    save it -- e.g. ``st.pyplot(fig)`` in Streamlit, or ``fig.savefig(...)``
    for embedding in an HTML/PDF report).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    disp_grid, rot_grid = np.meshgrid(surface.displacement, surface.rotation, indexing="ij")

    fig = plt.figure(figsize=(9, 6.5))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(
        disp_grid, rot_grid, surface.load, cmap="viridis",
        linewidth=0, antialiased=True, rcount=surface.load.shape[0], ccount=surface.load.shape[1],
    )
    ax.set_xlabel("Displacement (mm)")
    ax.set_ylabel("Rotation (Rad)")
    ax.set_zlabel("Maximum Load (N)")
    if title:
        ax.set_title(title, fontsize=10)

    # Visual match for the PDF's oblique view -- MATLAB's `view(65,10)` uses a
    # different azimuth/elevation convention than matplotlib, so this is
    # chosen to look similar rather than to match numerically.
    ax.view_init(elev=18, azim=-125)

    fig.colorbar(surf, ax=ax, shrink=0.65, pad=0.08, label="Maximum Load (N)")
    fig.tight_layout()
    return fig
