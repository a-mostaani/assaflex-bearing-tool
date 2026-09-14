"""
AssaFlex Bearing Design Tool -- Streamlit UI.

Run with:
    streamlit run app.py

Two tools in one app:
  1. Performance Solver -- the direct port of the original MATLAB tool: given
     a geometry, find its capacity, or check it against a stated demand.
  2. Optimal Design -- new: given a client's performance requirements, search
     the manufacturing catalog for the smallest-volume design that satisfies
     EN 1337-3.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from bearing_tool.catalog import Catalog, default_catalog
from bearing_tool.optimizer import (
    DesignRequirement,
    find_optimal_design,
    find_optimal_design_for_schedule,
)
from bearing_tool.schedule import BearingSchedule, LoadCombination
from bearing_tool.solver import evaluate_bearing

if "catalog" not in st.session_state:
    st.session_state.catalog = default_catalog()

REPO_ROOT = Path(__file__).resolve().parent
EXAMPLE_SCHEDULE_PATH = REPO_ROOT / "schedules" / "H3428_A0_A5_bearing_1.1.json"

SCHEDULE_COLUMNS = [
    "limit_state", "case", "vertical_kN", "transverse_kN", "longitudinal_kN",
    "long_displacement_mm", "trans_displacement_mm", "rotation_mrad",
    "transverse_rotation_mrad",
]


def _example_schedule_df() -> pd.DataFrame:
    sched = BearingSchedule.from_client_schedule_json(EXAMPLE_SCHEDULE_PATH)
    return pd.DataFrame([
        {col: getattr(c, col) for col in SCHEDULE_COLUMNS} for c in sched.combinations
    ])

st.set_page_config(page_title="AssaFlex Bearing Design Tool", layout="wide")

st.title("AssaFlex Bearing Design Tool")
st.caption(
    "Reinforced elastomeric bearing pads to BS EN 1337-3 -- Python port of the "
    "original MATLAB solver, plus a new optimal-design search."
)

with st.expander("⚠️ Known issues / limitations", expanded=False):
    st.markdown(
        """
- **Rotational stiffness factor `Ks`** now uses the real EN 1337-3 Table 4
  (restoring moment factor vs b/a), interpolated -- see
  `bearing_tool/en1337_tables.py`. It's transcribed by hand from a supplied
  image; double-check it against your copy of the standard. **Elliptical /
  circular bearings are still not supported** by this solver at all (it
  assumes a rectangular plan throughout) -- Annex A's Table A.1 is
  transcribed and ready in the same file, but wiring it in needs a parallel
  set of geometry formulas, not just a different Ks.
- **Bearing type 2.5 (type B/C) is not available.** Its overall-height formula in
  the original MATLAB file references a variable that is never defined
  (`n1`) -- selecting it would error in MATLAB too. It needs a confirmed
  formula from AssaFlex before it can be added.
- The **Optimal Design** search below is a grid search over the manufacturing
  catalog, not a certified global optimum -- see `bearing_tool/optimizer.py`
  for the method.
        """
    )

tab_solver, tab_optimizer, tab_schedule = st.tabs(
    ["🔎 Performance Solver", "📐 Optimal Design", "📋 Design to Bearing Schedule"]
)


# ----------------------------------------------------------------------------
# Tab 1: direct performance solver (mirrors the original MATLAB tool)
# ----------------------------------------------------------------------------
with tab_solver:
    st.subheader("Evaluate one geometry")
    st.caption(
        "Leave a design demand (load / rotation / displacement) at 0 to compute "
        "the bearing's maximum capacity for it instead of checking a stated value."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Geometry**")
        w = st.number_input("w — width, longitudinal (mm)", min_value=1.0, value=400.0, step=5.0,
                             help="Along the direction with the bigger rotation, per standard installation.")
        l = st.number_input("l — length, transverse (mm)", min_value=1.0, value=500.0, step=5.0)
        n = st.number_input("n — number of inner elastomer layers", min_value=1, value=6, step=1,
                             help="n+1 steel reinforcement plates.")
        ti = st.number_input("ti — inner elastomer layer thickness (mm)", min_value=0.1, value=10.0, step=0.5)
        ts = st.number_input("ts — steel reinforcement thickness (mm)", min_value=0.1, value=3.0, step=0.5)
        bearing_type = st.selectbox("type — bearing pad type", options=[2, 3],
                                     format_func=lambda t: {2: "2 = type B", 3: "3 = type C"}[t])

    with col2:
        st.markdown("**Material & installation**")
        g = st.number_input("g — shear modulus G (N/mm²)", min_value=0.01, value=1.0, step=0.05)
        mu = st.number_input("μ — friction coefficient", min_value=0.01, value=0.3, step=0.05,
                              help="~0.3 for steel-steel / steel-elastomer / elastomer-concrete; ~0.4 for wood-elastomer.")
        esl = st.selectbox("esl — external steel layers present?", options=[0, 1],
                            format_func=lambda v: "Yes" if v else "No")
        ndd = st.selectbox("ndd — displacement directions", options=[1, 2])
        nrd = st.selectbox("nrd — rotation directions", options=[1, 2])
        perc1 = st.number_input("perc1 — transverse/longitudinal displacement ratio", min_value=0.0, max_value=1.0,
                                 value=0.3 if ndd == 2 else 0.0, step=0.05, disabled=(ndd == 1))
        perc2 = st.number_input("perc2 — transverse/longitudinal rotation ratio", min_value=0.0, max_value=1.0,
                                 value=0.3 if nrd == 2 else 0.0, step=0.05, disabled=(nrd == 1))
        msf = st.number_input("msf — manufacturing safety factor", min_value=0.01, max_value=1.0, value=0.7, step=0.05)

    with col3:
        st.markdown("**Design demand (0 = solve for it)**")
        dl = st.number_input("dl — design load (N)", min_value=0.0, value=0.0, step=1000.0)
        dr = st.number_input("dr — design rotation (rad)", min_value=0.0, value=0.0, step=0.001, format="%.4f")
        dd1 = st.number_input("dd1 — design longitudinal displacement (mm)", min_value=0.0, value=0.0, step=1.0)
        dd2 = st.number_input("dd2 — design transverse displacement (mm)", min_value=0.0, value=0.0, step=1.0)

    if st.button("Evaluate", type="primary"):
        try:
            r = evaluate_bearing(
                w=w, l=l, n=int(n), ti=ti, ts=ts, g=g, mu=mu, bearing_type=bearing_type,
                esl=esl, ndd=ndd, nrd=nrd, perc1=perc1, perc2=perc2, msf=msf,
                dl=dl, dr=dr, dd1=dd1, dd2=dd2,
            )
        except (NotImplementedError, ValueError) as e:
            st.error(str(e))
        else:
            if r.feasible:
                st.success(f"Feasible — {r.failure_reason or 'within all checked limits'}")
            else:
                st.error(f"Not feasible — {r.failure_reason}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Max load", f"{r.max_load:,.0f} N" if r.max_load is not None else "—")
            m2.metric("Max rotation (w)", f"{r.max_ang_w:.5f} rad" if r.max_ang_w is not None else "—")
            m3.metric("Max shear deflection", f"{r.max_vec_shear_def:.1f} mm" if r.max_vec_shear_def is not None else "—")
            m4.metric("Overall height", f"{r.overal_height:.1f} mm" if r.overal_height is not None else "—")

            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Load upper bound", f"{r.load_upperbound:,.0f} N" if r.load_upperbound is not None else "—")
            m6.metric("Rotation upper bound", f"{r.rot_upperbound:.5f} rad" if r.rot_upperbound is not None else "—")
            m7.metric("Min load (no slip)", f"{r.min_load:,.0f} N" if r.min_load is not None else "—")
            m8.metric("Plan area", f"{r.plan_area:,.0f} mm²" if r.plan_area is not None else "—")

            if r.total_strain_i is not None:
                st.progress(
                    min(1.0, max(r.total_strain_i, r.total_strain_o) / r.strain_limit),
                    text=f"Total strain: inner {r.total_strain_i:.3f} / outer {r.total_strain_o:.3f}  "
                         f"(limit {r.strain_limit:.3f})",
                )

            if r.min_ts is not None:
                st.write(
                    f"Required steel shim thickness: **{r.min_ts:.3f} mm** — "
                    f"{'✅ satisfied' if r.ts_ok else '❌ NOT satisfied'} by ts={ts} mm"
                )

            if r.Max_force_exerted is not None:
                st.write(f"Max horizontal force exerted on structure: **{r.Max_force_exerted:,.0f} N**")
            if r.Max_moment is not None:
                st.write(
                    f"Max resisting moment on structure: **{r.Max_moment:,.0f} N·mm** "
                    f"(EN 1337-3 Table 4, Ks={r.ks_used:.2f})"
                )

            if r.warnings:
                with st.expander("Messages", expanded=False):
                    for msg in r.warnings:
                        st.write("• " + msg)


# ----------------------------------------------------------------------------
# Tab 2: optimal design search
# ----------------------------------------------------------------------------
with tab_optimizer:
    st.subheader("Find the smallest bearing that meets a performance requirement")
    st.caption(
        "Enter the client's design criteria, tune the manufacturing catalog if "
        "needed, then search. Objective: minimum total material volume "
        "(plan area × overall height)."
    )

    if "catalog" not in st.session_state:
        st.session_state.catalog = default_catalog()

    req_col, cat_col = st.columns([1, 1.3])

    with req_col:
        st.markdown("**Client performance requirement**")
        label = st.text_input("Label (optional)", value="", placeholder="e.g. Pier 3 support")
        req_dl = st.number_input("Design load, dl (N)", min_value=0.0, value=300000.0, step=10000.0)
        req_dr = st.number_input("Design rotation, dr (rad)", min_value=0.0, value=0.008, step=0.001, format="%.4f")
        req_dd1 = st.number_input("Design longitudinal displacement, dd1 (mm)", min_value=0.0, value=15.0, step=1.0)
        req_dd2 = st.number_input("Design transverse displacement, dd2 (mm)", min_value=0.0, value=0.0, step=1.0)
        req_ndd = st.selectbox("Displacement directions (ndd)", options=[1, 2], key="opt_ndd")
        req_nrd = st.selectbox("Rotation directions (nrd)", options=[1, 2], key="opt_nrd")
        req_perc1 = st.number_input("perc1", min_value=0.0, max_value=1.0,
                                     value=0.3 if req_ndd == 2 else 0.0, step=0.05,
                                     disabled=(req_ndd == 1), key="opt_perc1")
        req_perc2 = st.number_input("perc2", min_value=0.0, max_value=1.0,
                                     value=0.3 if req_nrd == 2 else 0.0, step=0.05,
                                     disabled=(req_nrd == 1), key="opt_perc2")

    with cat_col:
        st.markdown("**Manufacturing catalog** (editable — keep these matched to your real process)")
        cat: Catalog = st.session_state.catalog

        c1, c2, c3 = st.columns(3)
        cat.plan_min = c1.number_input("Plan dim min (mm)", value=float(cat.plan_min), step=25.0)
        cat.plan_max = c2.number_input("Plan dim max (mm)", value=float(cat.plan_max), step=25.0)
        cat.plan_step = c3.number_input("Plan dim step (mm)", value=float(cat.plan_step), step=5.0, min_value=1.0)

        c4, c5 = st.columns(2)
        cat.n_min = c4.number_input("n min", value=int(cat.n_min), step=1, min_value=1)
        cat.n_max = c5.number_input("n max", value=int(cat.n_max), step=1, min_value=int(cat.n_min))

        ti_text = st.text_input("ti options, mm (comma-separated)", value=", ".join(str(v) for v in cat.ti_options))
        cat.ti_options = [float(x) for x in ti_text.split(",") if x.strip()]

        ts_text = st.text_input("ts options, mm (comma-separated)", value=", ".join(str(v) for v in cat.ts_options))
        cat.ts_options = [float(x) for x in ts_text.split(",") if x.strip()]

        g_text = st.text_input("g options, N/mm² (comma-separated)", value=", ".join(str(v) for v in cat.g_options))
        cat.g_options = [float(x) for x in g_text.split(",") if x.strip()]

        msf_text = st.text_input(
            "msf options (comma-separated) — how much of EN 1337-3's max "
            "permitted strain/movement capacity to allow; the optimizer "
            "tries these smallest-first and uses the smallest one that "
            "makes each candidate geometry feasible",
            value=", ".join(str(v) for v in cat.msf_options),
        )
        cat.msf_options = [float(x) for x in msf_text.split(",") if x.strip()]

        type_opts = st.multiselect("Bearing types to consider", options=[2, 3], default=cat.bearing_types)
        cat.bearing_types = type_opts or [2]

        cc1, cc2 = st.columns(2)
        cat.mu = cc1.number_input("μ (process default)", value=float(cat.mu), step=0.05)
        cat.esl = cc2.selectbox("esl (process default)", options=[0, 1], index=int(cat.esl))

        st.caption(f"Grid size: **{cat.estimated_combinations():,}** combinations "
                   f"(≈ {cat.estimated_combinations() / 90000:.0f}–{cat.estimated_combinations() / 45000:.0f} s to search)")

        dl_col, ul_col = st.columns(2)
        with dl_col:
            uploaded = st.file_uploader("Load catalog from JSON", type="json", key="catalog_upload")
            if uploaded is not None:
                st.session_state.catalog = Catalog(**json.load(uploaded))
                st.rerun()
        with ul_col:
            st.download_button("Save catalog as JSON", data=json.dumps(cat.__dict__, indent=2),
                                file_name="assaflex_catalog.json", mime="application/json")

    st.divider()

    if st.button("🔍 Run optimization", type="primary"):
        req = DesignRequirement(
            dl=req_dl, dr=req_dr, dd1=req_dd1, dd2=req_dd2,
            ndd=req_ndd, nrd=req_nrd, perc1=req_perc1, perc2=req_perc2, label=label,
        )
        with st.spinner(f"Searching {cat.estimated_combinations():,} candidate designs…"):
            result = find_optimal_design(req, cat)

        st.write(result.message)

        if result.best is None:
            st.error("No feasible design found in this catalog for this requirement.")
        else:
            b = result.best
            total_ti = b.n * b.ti
            st.success(
                f"Best design: **w={b.w:.0f} mm × l={b.l:.0f} mm × h={b.result.overal_height:.1f} mm** "
                f"(total internal elastomer thickness = {total_ti:.1f} mm) — "
                f"n={b.n}, ti={b.ti} mm, ts={b.ts} mm, g={b.g} N/mm², type {b.bearing_type}, msf={b.msf}"
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Plan area", f"{b.plan_area:,.0f} mm²")
            m2.metric("Overall height", f"{b.result.overal_height:.1f} mm")
            m3.metric("Total volume", f"{b.total_volume:,.0f} mm³")
            m4.metric("Feasible / evaluated", f"{result.feasible_count:,} / {result.combinations_evaluated:,}")

            with st.expander("Full result detail for the best design"):
                st.json({k: v for k, v in b.result.__dict__.items() if k != "warnings"})
                for msg in b.result.warnings:
                    st.write("• " + msg)

            if result.alternatives:
                st.markdown("**Next-best alternatives**")
                st.table([
                    {
                        "w (mm)": c.w, "l (mm)": c.l, "n": c.n, "ti (mm)": c.ti,
                        "ts (mm)": c.ts, "g": c.g, "type": c.bearing_type,
                        "volume (mm³)": f"{c.total_volume:,.0f}",
                        "height (mm)": f"{c.result.overal_height:.1f}",
                    }
                    for c in result.alternatives
                ])


# ----------------------------------------------------------------------------
# Tab 3: design against a full client bearing schedule (EN 1337-1 Table 1)
# ----------------------------------------------------------------------------
with tab_schedule:
    st.subheader("Design the smallest bearing that satisfies a full client schedule")
    st.caption(
        "A real client schedule states several coincident (load, displacement, "
        "rotation) design points across SLS/ULS/ALS — including the schedule's "
        "own governing \"Max Displacement\" and \"Max Rotation\" rows, which can "
        "have different coincident loads than the Max Vertical/Longitudinal/"
        "Transverse rows. The winning design must satisfy **every row**, not "
        "just the worst value of each quantity independently. Uses the same "
        "manufacturing catalog as the Optimal Design tab (edit it there)."
    )

    if "schedule_df" not in st.session_state:
        st.session_state.schedule_df = _example_schedule_df()

    top_row1, top_row2, top_row3 = st.columns([1, 1, 1])
    with top_row1:
        if st.button("Load H3428 example"):
            st.session_state.schedule_df = _example_schedule_df()
            st.rerun()
    with top_row2:
        uploaded_schedule = st.file_uploader("Load schedule JSON", type="json",
                                              key="schedule_upload", label_visibility="collapsed")
    with top_row3:
        st.caption("Upload a schedule saved from this tab, or a client-schedule JSON "
                   "like `schedules/H3428_A0_A5_bearing_1.1.json`.")

    if uploaded_schedule is not None:
        raw = json.load(uploaded_schedule)
        try:
            if "combinations" in raw and raw["combinations"] and "case" in raw["combinations"][0] \
                    and "long_displacement_mm" not in raw["combinations"][0]:
                # Richer client-schedule shape -- write to a temp file and reuse the loader.
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                    json.dump(raw, f)
                    tmp_path = f.name
                sched = BearingSchedule.from_client_schedule_json(tmp_path)
            else:
                sched = BearingSchedule(
                    label=raw.get("label", ""),
                    combinations=[LoadCombination(**c) for c in raw.get("combinations", [])],
                    max_longitudinal_mm=raw.get("max_longitudinal_mm"),
                    max_transverse_mm=raw.get("max_transverse_mm"),
                    max_height_mm=raw.get("max_height_mm"),
                    mu=raw.get("mu", 0.3), msf=raw.get("msf", 0.7), esl=raw.get("esl", 0),
                )
            st.session_state.schedule_df = pd.DataFrame([
                {col: getattr(c, col) for col in SCHEDULE_COLUMNS} for c in sched.combinations
            ])
            st.session_state.schedule_envelope = (
                sched.max_longitudinal_mm, sched.max_transverse_mm, sched.max_height_mm,
                sched.mu, sched.msf, sched.esl,
            )
            st.success(f"Loaded schedule: {sched.label or '(no label)'} — "
                       f"{len(sched.combinations)} combination(s)")
        except Exception as e:  # noqa: BLE001 -- surface any parse error to the user
            st.error(f"Couldn't parse this file as a bearing schedule: {e}")

    schedule_label = st.text_input("Schedule label", value="", placeholder="e.g. H3428 A0/A5, mark 1.1")

    st.markdown("**Load combinations** — one row per coincident design point (add/remove rows as needed)")
    edited_df = st.data_editor(
        st.session_state.schedule_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "limit_state": st.column_config.SelectboxColumn(options=["SLS", "ULS", "ALS"]),
            "vertical_kN": st.column_config.NumberColumn(format="%.1f"),
            "transverse_kN": st.column_config.NumberColumn(format="%.1f"),
            "longitudinal_kN": st.column_config.NumberColumn(format="%.1f"),
            "long_displacement_mm": st.column_config.NumberColumn(
                "long. disp. (mm)", format="%.1f",
                help="Total design displacement (irreversible + reversible), longitudinal axis."),
            "trans_displacement_mm": st.column_config.NumberColumn(
                "trans. disp. (mm)", format="%.1f",
                help="Total design displacement (irreversible + reversible), transverse axis. "
                     "Combined with the longitudinal figure as a vector magnitude, not added."),
            "rotation_mrad": st.column_config.NumberColumn(
                "rotation (mrad)", format="%.2f",
                help="Dominant (longitudinal-bending) design rotation."),
            "transverse_rotation_mrad": st.column_config.NumberColumn(
                "trans. rotation (mrad)", format="%.2f",
                help="Optional small coincident rotation about the other axis. "
                     "Leave 0 unless the schedule states one."),
        },
        key="schedule_editor",
    )

    default_env = st.session_state.get("schedule_envelope", (450.0, 600.0, 100.0, 0.3, 0.7, 0))
    e1, e2, e3, e4, e5, e6 = st.columns(6)
    env_max_long = e1.number_input("Max longitudinal (mm)", value=float(default_env[0] or 0), min_value=0.0)
    env_max_trans = e2.number_input("Max transverse (mm)", value=float(default_env[1] or 0), min_value=0.0)
    env_max_height = e3.number_input("Max height (mm)", value=float(default_env[2] or 0), min_value=0.0)
    env_mu = e4.number_input("μ", value=float(default_env[3]), step=0.05)
    search_msf = e6.checkbox(
        "Search msf too", value=False,
        help="Instead of one fixed msf, try every value in the catalog's "
             "msf options (smallest-first) and use the smallest one that "
             "makes each candidate geometry feasible -- see the Catalog "
             "tab. Off by default so an explicit contract value below is "
             "used exactly as given.",
    )
    env_msf = e5.number_input("msf", value=float(default_env[4]), step=0.05, disabled=search_msf)
    env_esl = st.selectbox("esl", options=[0, 1], index=int(default_env[5]))

    dl_col, ul_col = st.columns(2)
    with ul_col:
        def _current_schedule() -> BearingSchedule:
            combos = [
                LoadCombination(
                    limit_state=row["limit_state"], case=row["case"],
                    vertical_kN=row["vertical_kN"], transverse_kN=row.get("transverse_kN", 0.0) or 0.0,
                    longitudinal_kN=row.get("longitudinal_kN", 0.0) or 0.0,
                    long_displacement_mm=row.get("long_displacement_mm", 0.0) or 0.0,
                    trans_displacement_mm=row.get("trans_displacement_mm", 0.0) or 0.0,
                    rotation_mrad=row.get("rotation_mrad", 0.0) or 0.0,
                    transverse_rotation_mrad=row.get("transverse_rotation_mrad", 0.0) or 0.0,
                )
                for _, row in edited_df.iterrows() if row.get("case")
            ]
            return BearingSchedule(
                label=schedule_label, combinations=combos,
                max_longitudinal_mm=env_max_long or None, max_transverse_mm=env_max_trans or None,
                max_height_mm=env_max_height or None, mu=env_mu,
                msf=None if search_msf else env_msf, esl=env_esl,
            )

        schedule_json_bytes = (
            json.dumps(_current_schedule().as_dict(), indent=2) if not edited_df.empty else "{}"
        )
        st.download_button("Save schedule as JSON", data=schedule_json_bytes,
                            file_name="bearing_schedule.json", mime="application/json")

    st.divider()

    if st.button("🔍 Design to this schedule", type="primary"):
        schedule = _current_schedule()
        if not schedule.combinations:
            st.error("Add at least one load combination first.")
        else:
            cat = st.session_state.catalog
            with st.spinner(f"Checking every candidate against all {len(schedule.combinations)} "
                             f"combination(s)…"):
                result = find_optimal_design_for_schedule(schedule, cat)

            st.write(result.message)

            if result.best is None:
                st.error("No design in the catalog satisfies every combination in this schedule.")
            else:
                b = result.best
                total_ti = b.n * b.ti
                st.success(
                    f"Best design: **w={b.w:.0f} mm (longitudinal) × l={b.l:.0f} mm (transverse) × "
                    f"h={b.result.overal_height:.1f} mm** (total internal elastomer thickness = "
                    f"{total_ti:.1f} mm) — n={b.n}, ti={b.ti} mm, ts={b.ts} mm, g={b.g} N/mm², "
                    f"type {b.bearing_type}, msf={b.msf}"
                )
                if search_msf:
                    st.caption(f"msf was searched (catalog options: "
                               f"{', '.join(str(v) for v in cat.msf_options)}) — "
                               f"{b.msf} was the smallest value that made this design feasible.")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Plan area", f"{b.plan_area:,.0f} mm²")
                m2.metric("Overall height", f"{b.result.overal_height:.1f} mm")
                m3.metric("Total volume", f"{b.total_volume:,.0f} mm³")
                m4.metric("Geometries tried", f"{result.combinations_evaluated:,}")

                st.markdown("**Per-combination check for the winning design**")
                # Use the msf actually used for this design (not env_msf,
                # which is ignored/disabled when "Search msf too" is on).
                strain_limit = b.msf * 7
                st.dataframe([
                    {
                        "Combination": c.combination.label,
                        "Pass": "✅" if c.passed else "❌",
                        "Strain inner": f"{c.result.total_strain_i:.3f}" if c.result.total_strain_i is not None else "—",
                        "Strain outer": f"{c.result.total_strain_o:.3f}" if c.result.total_strain_o is not None else "—",
                        "Limit": f"{strain_limit:.3f}",
                    }
                    for c in result.best_check.checks
                ], use_container_width=True)

                if result.alternatives:
                    st.markdown("**Next-best alternatives**")
                    st.table([
                        {
                            "w (mm)": c.w, "l (mm)": c.l, "n": c.n, "ti (mm)": c.ti,
                            "ts (mm)": c.ts, "g": c.g, "type": c.bearing_type,
                            "volume (mm³)": f"{c.total_volume:,.0f}",
                            "height (mm)": f"{c.result.overal_height:.1f}",
                        }
                        for c in result.alternatives
                    ])
