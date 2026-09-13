# AssaFlex Bearing Design Tool

Python port of the AssaFlex reinforced elastomeric bearing pad solver
(`des_reinf_bearing_bsi_test_2.m`, to BS EN 1337-3), plus a new optimal-design
search module, with a Streamlit UI for internal engineering use (also
packaged as a double-click Windows app — see `desktop/`) and a
public-facing web form (see `webapp/`) for assaflex.com.

## What's here

- `bearing_tool/solver.py` — the ported solver (`evaluate_bearing`). Given a
  geometry, either computes its performance envelope (max load / rotation /
  shear deflection) or checks it against a stated design demand. Validated
  line-for-line against the original MATLAB file running under Octave 8.4 —
  see the docstring and `tests/test_solver.py`.
- `bearing_tool/catalog.py` — the editable manufacturing catalog (`Catalog`):
  the discrete plan dimensions, layer thicknesses, shim thicknesses, elastomer
  grades and bearing types the optimizer is allowed to choose from. **All
  values are placeholders** — replace them with AssaFlex's real manufacturing
  constraints before trusting the optimizer's output.
- `bearing_tool/optimizer.py` — new: given a client's performance requirement
  (design load / rotation / displacement), searches the catalog for the
  smallest-total-volume design that satisfies EN 1337-3. See its docstring
  for the search method and its limits.
- `bearing_tool/en1337_tables.py` — EN 1337-3 Table 4 (restoring moment
  factor Ks for rectangular bearings, by b/a) and Annex A's Table A.1
  (elliptical/circular bearing factors), transcribed from the standard.
  Table 4 is wired into the solver; Table A.1 is transcribed and ready but
  unused (see Known issues below).
- `bearing_tool/schedule.py` — new: models a real client bearing schedule
  (EN 1337-1:2000 Table 1 format) as a set of coincident load/displacement/
  rotation combinations plus a maximum bearing envelope, and checks a
  candidate geometry against **every** combination (not an independent-maxima
  envelope — see the module docstring for why that would be unsafe/unfair).
  This includes the schedule's own governing "Max Displacement" and "Max
  Rotation" rows (each with their own coincident loads, distinct from the
  Max Vertical/Longitudinal/Transverse rows) — these are commonly the actual
  worst case and are easy to miss. A combination's displacement can be
  nonzero in both axes at once; per EN 1337-3 5.3.3.3 these are meant as
  *totals* (irreversible + reversible already summed) that the solver itself
  vector-sums (`sqrt(dd1**2+dd2**2)`) — `schedule.py` only carries them
  through, it doesn't recombine them. A stated secondary (transverse)
  rotation is reproduced via a ratio (`transverse_rotation_mrad`), since the
  solver's own rotation-strain formula weights the two rotation components
  by different plan dimensions rather than combining them as a vector — see
  the module docstring for why. `find_optimal_design_for_schedule` (in
  `optimizer.py`) searches the catalog for the smallest design that passes
  the whole schedule.
- `schedules/H3428_A0_A5_bearing_1.1.json` — a real client bearing schedule
  (Immingham Eastern Ro-Ro Terminal, Robinson Bridge), hand-transcribed from
  a scanned drawing (`reference/H3428_Bridge_Bearing_Drawings_1.pdf`,
  `schedules/source_images/`) as a worked example. **Two transcription
  points are flagged in the JSON's own notes and should be confirmed against
  the original drawing before this schedule is used for anything real:**
  the drawing labels its first two SLS rotation figures "[rad]" and the rest
  "[mrad]" — given the magnitudes (~3–5) these were read as all `mrad` (a
  likely typo in the original), not a mix of units; and the "reversible
  …,i" displacement/rotation rows were read as the *total* design value
  (irreversible + reversible), not an amount to add on top of the
  irreversible component.
- `app.py` — the Streamlit UI, with three tabs: **Performance Solver**
  (mirrors the original MATLAB tool), **Optimal Design** (single load case,
  the catalog editable inline and savable/loadable as JSON), and **Design to
  Bearing Schedule** (a full client schedule — edit the load-combination
  table directly, load/save it as JSON, or load the H3428 example — checked
  row-by-row against the optimizer's candidates).
- `reference/des_reinf_bearing_bsi_test_2.m` — the original MATLAB file, kept
  for reference and as the source of truth the port was checked against.
- `webapp/` — new: a small FastAPI backend + a self-contained HTML/JS form,
  for embedding a "request a bearing design" form on assaflex.com itself
  (separate from the internal Streamlit tool above). A submission computes
  a design and emails it to engineering + sales for review — the website
  visitor only ever sees an acknowledgement, never the computed numbers,
  since the design is explicitly preliminary until an engineer signs off.
  See `webapp/README.md` for setup, deployment (including a step-by-step
  for Railway — see `railway.json` at the repo root), and how to embed the
  form in WordPress.
- `desktop/` — new: packages the Streamlit app above as a double-click
  Windows app for colleagues who shouldn't need to touch a terminal or
  install Python — a self-contained portable folder (a bundled Python
  runtime with Streamlit and its dependencies installed into it), not a
  single .exe (see `desktop/README.md` for why, and for the one-time
  build + sharing steps — building it needs internet access on that one
  machine; running it afterwards doesn't).
- `tests/` — pytest regression tests (golden values captured from Octave)
  plus tests for the optimizer, the schedule module, and the webapp API.
  Run with `python3 -m pytest tests/`.

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

This opens the tool in your default browser (typically `http://localhost:8501`).

## Known issues / things to fix before relying on this for real designs

1. **`Ks` (restoring moment factor) now uses the real EN 1337-3 Table 4**
   (interpolated by b/a) instead of the original's hardcoded 78.4 — see
   `bearing_tool/en1337_tables.py`. It was transcribed by hand from an image
   of the standard; double-check it against your own copy. **Elliptical /
   circular bearings are still entirely unsupported** — this solver assumes
   a rectangular plan throughout (area, perimeter, shape factors), so a
   circular design needs a parallel geometry path, not just a different Ks.
   Annex A's Table A.1 is transcribed and ready in the same file for when
   that's built — note the standard's own footnote that its b/a=1.0 column
   is for interpolation only, *not* the value to use for an actual circular
   bearing; the correct circular-specific value/formula still needs to be
   supplied.
2. **Bearing type 2.5 (type B/C) is not supported.** The original MATLAB
   file's height formula for it references an undefined variable (`n1`) —
   it would error in MATLAB too. It needs a confirmed formula from AssaFlex.
3. **The manufacturing catalog defaults are placeholders** (standard-ish
   elastomer thicknesses, steel shim thicknesses, and shear-modulus grades) —
   they are not AssaFlex's real stock/process constraints. Edit them in the
   UI or in `bearing_tool/catalog.py` and save your real catalog as JSON.
4. **The optimizer is a grid search**, not a certified global optimum —
   see `bearing_tool/optimizer.py`'s docstring for why, and for the natural
   next step (a local heuristic seeded from the grid result) if the catalog
   grows large enough that the grid becomes too coarse or too slow.
5. **Bearing schedules are entered by hand or as JSON** — there's no
   PDF/Excel auto-extraction yet (see the schedule tab's uploader, which
   currently expects a JSON file already in one of the two shapes
   `bearing_tool/schedule.py` reads). Planned as a follow-up.
6. **A stated secondary (transverse) rotation is applied as a ratio of the
   dominant one** (`transverse_rotation_mrad` → `perc2 = transverse /
   dominant`), reproducing the exact stated value since that relationship is
   linear in the solver — but it silently does nothing if a combination ever
   states a transverse rotation with a dominant rotation of exactly 0 (no
   ratio to compute). Not an issue for any row in the H3428 example.
7. **`webapp/` doesn't store submissions or authenticate who can submit** —
   each website request only exists in the notification email, and it's a
   public form like any "contact us" page (add a CAPTCHA if spam becomes an
   issue). It also uses the same placeholder catalog as the Streamlit tool
   unless `CATALOG_PATH` is set — see `webapp/README.md`.

## Deliberate behavior changes vs. the original MATLAB (robustness only)

Documented in full in `bearing_tool/solver.py`'s module docstring:
- A latent infinite-loop bug in the original's convergence check (its
  iteration counter reset every loop pass, so it could never actually stop a
  non-convergent case) is fixed — non-convergence now ends cleanly with
  `feasible=False` instead of hanging.
- A case where MATLAB would print a warning and then crash the moment a
  caller asks for its (unassigned) outputs — an overloaded design that
  exceeds buckling capacity — now returns a clean `feasible=False` result
  instead, which is what lets the optimizer treat it as "infeasible" rather
  than crash.

Neither change alters the numeric result of any case that converges/succeeds
in the original — both were verified against Octave (see `tests/test_solver.py`).
