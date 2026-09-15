"""
Renders a ``CalculationDocument`` (see ``calc_document.py``) as a single
self-contained, branded HTML string.

Colors/font are the same tokens already sampled from assaflex.co.uk for
``webapp/static/design-request-form.html`` (deep green + lime accent,
Poppins) -- reused here rather than re-derived, so the request form and this
report look like the same product.

Everything (logo, capacity-surface plot) is inlined as base64 data URIs so
the same HTML string is portable across three very different hosts: a
Streamlit sandboxed component iframe (``st.components.v1.html``), a FastAPI
HTTP response, and as the source for the ReportLab PDF's plot image -- none
of which can be relied on to resolve a relative/static file path the same
way.
"""

from __future__ import annotations

import base64
import io
from html import escape
from pathlib import Path

from .calc_document import TESTS_CONDUCTED_INTRO, CalculationDocument
from .surface import plot_capacity_surface

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

AF_GREEN = "#004439"
AF_GREEN_DARK = "#00332a"
AF_LIME = "#6db942"
AF_INK = "#142420"
AF_BODY = "#2b3733"
AF_MUTED = "#5b6864"
AF_LINE = "#dbe3df"
AF_LINE_STRONG = "#b9c4bf"
AF_PAGE_BG = "#f2f6f4"


def _logo_data_uri() -> str:
    data = (ASSETS_DIR / "assaflex_logo.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _font_data_uri(filename: str) -> str:
    data = (FONTS_DIR / filename).read_bytes()
    return "data:font/ttf;base64," + base64.b64encode(data).decode("ascii")


def _font_face_css() -> str:
    # Embedded (not linked from Google Fonts) so the report renders
    # identically offline and inside Streamlit's sandboxed component iframe,
    # which may not have network access to fonts.googleapis.com.
    weights = [
        ("Poppins-Regular.ttf", 400),
        ("Poppins-Medium.ttf", 500),
        ("Poppins-SemiBold.ttf", 600),
        ("Poppins-Bold.ttf", 700),
    ]
    return "\n".join(
        f"""@font-face {{
      font-family: "Poppins"; font-weight: {weight}; font-style: normal;
      src: url({_font_data_uri(filename)}) format("truetype");
    }}"""
        for filename, weight in weights
    )


def _figure_data_uri(doc: CalculationDocument) -> str:
    fig = plot_capacity_surface(
        doc.surface,
        title=f"Illustration of Relation of Fz,design vs alpha_a,d vs Vx,d",
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    import matplotlib.pyplot as plt

    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _fmt(value, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}{unit}"


def _param_row(symbol: str, value: str, description: str) -> str:
    return (
        f'<div class="af-param-row">'
        f'<span class="af-param-symbol">{symbol}</span>'
        f'<span class="af-param-value">{escape(value)}</span>'
        f'<span class="af-param-desc">{escape(description)}</span>'
        f"</div>"
    )


def render_calculation_document_html(doc: CalculationDocument) -> str:
    logo_uri = _logo_data_uri()
    plot_uri = _figure_data_uri(doc)

    header_lines = []
    if doc.client_name or doc.project_name:
        bits = []
        if doc.client_name:
            bits.append(f"To be announced to {escape(doc.client_name)}")
        if doc.project_name:
            bits.append(f"for the project {escape(doc.project_name)}")
        header_lines.append(", ".join(bits))
    header_lines.append(escape(doc.title))

    basic_params = "".join([
        _param_row("a", f"{doc.w:.0f} mm", "width (longitudinal direction)"),
        _param_row("b", f"{doc.l:.0f} mm", "length (transverse direction)"),
        _param_row("n", f"{doc.n}", "number of internal elastomer layers"),
        _param_row("t_si", f"{doc.ts:.1f} mm", "thickness of internal steel reinforcements"),
        _param_row("t_i", f"{doc.ti:.1f} mm", "thickness of each internal elastomer layer"),
        _param_row("g", f"{doc.g:g} N/mm²", "shear modulus"),
        _param_row("mu", f"{doc.mu:g}", "friction coefficient"),
        _param_row("msf", f"{doc.msf:g}", "manufacturing safety factor"),
        _param_row("type", doc.bearing_type_label, "bearing type"),
    ])

    mech_props = "".join([
        _param_row("V_x,d", f"±{_fmt(doc.max_vectorial_shear_deflection, ' mm')}",
                   "Maximum Vectorial Shear Deflection"),
        _param_row("F_z,design", f"{_fmt((doc.max_load_design or 0)/1000, ' kN', 0)}",
                   "Maximum Vertical Load Combined with Full Shear Deflection and Rotation"),
        _param_row("F_z,max", f"{_fmt((doc.max_load_buckling or 0)/1000, ' kN', 0)}",
                   "Maximum Vertical Load With no rotation and full shear deflection, "
                   "considering buckling stability criteria"),
        _param_row("F_z,min", f"{_fmt((doc.min_load_no_slip or 0)/1000, ' kN', 0)}",
                   "Minimum Vertical Load to prevent slipping of the bearing pad when "
                   "in maximum shear deflection"),
        _param_row("alpha_a,d", f"{_fmt(doc.max_rotation, ' rad', 5)}",
                   "Maximum Rotation along the width in Full Vertical Load and Shear Deflection"),
        _param_row("sum v_z,d", f"{_fmt(doc.max_vertical_deflection, ' mm')}",
                   "Maximum Vertical Deflection"),
        _param_row("R_xy", f"{_fmt((doc.max_horizontal_load or 0)/1000, ' kN', 1)}",
                   "Maximum horizontal load exerted by the bearing on the foundation "
                   "to resist translatory movement, to be considered on structural design"),
    ])

    tests_bullets = "".join(f"<li>{escape(b)}</li>" for b in doc.tests_conducted)
    notes_bullets = "".join(f"<li>{escape(b)}</li>" for b in doc.general_notes)

    return f"""
<div class="af-doc">
<style>
  {_font_face_css()}
  .af-doc {{
    --af-green: {AF_GREEN}; --af-lime: {AF_LIME}; --af-ink: {AF_INK};
    --af-body: {AF_BODY}; --af-muted: {AF_MUTED}; --af-line: {AF_LINE};
    --af-line-strong: {AF_LINE_STRONG}; --af-page-bg: {AF_PAGE_BG};
    font-family: "Poppins", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--af-body); background: var(--af-page-bg);
  }}
  .af-doc * {{ box-sizing: border-box; }}
  .af-doc .af-hero {{
    background: var(--af-green); padding: 22px 28px; display: flex; align-items: center; gap: 18px;
  }}
  .af-doc .af-hero img {{ height: 40px; }}
  .af-doc .af-hero-text h1 {{ color: #fff; font-size: 1.15rem; margin: 0 0 2px; font-weight: 700; }}
  .af-doc .af-hero-text p {{ color: var(--af-lime); margin: 0; font-size: 0.8rem; }}
  .af-doc .af-page {{ max-width: 900px; margin: 0 auto; padding: 24px 28px 48px; background: #fff; }}
  .af-doc h2 {{ color: var(--af-ink); font-size: 1rem; border-top: 3px solid var(--af-green);
              padding-top: 8px; margin: 28px 0 12px; }}
  .af-doc .af-header-lines p {{ margin: 2px 0; color: var(--af-muted); font-size: 0.85rem; }}
  .af-doc .af-header-lines p.af-title {{ color: var(--af-green); font-weight: 700; font-size: 1.02rem; }}
  .af-doc .af-param-row {{
    display: grid; grid-template-columns: 90px 130px 1fr; gap: 10px;
    padding: 5px 0; border-bottom: 1px solid var(--af-line); font-size: 0.86rem;
  }}
  .af-doc .af-param-symbol {{ font-weight: 600; color: var(--af-green); font-style: italic; }}
  .af-doc .af-param-value {{ font-weight: 600; }}
  .af-doc .af-param-desc {{ color: var(--af-muted); }}
  .af-doc .af-plot {{ text-align: center; margin: 12px 0; }}
  .af-doc .af-plot img {{ max-width: 100%; border: 1px solid var(--af-line-strong); }}
  .af-doc ul {{ margin: 0 0 12px; padding-left: 20px; font-size: 0.82rem; color: var(--af-body); }}
  .af-doc ul li {{ margin-bottom: 8px; line-height: 1.5; }}
  .af-doc .af-footer {{ color: var(--af-muted); font-size: 0.72rem; margin-top: 32px;
                        border-top: 1px solid var(--af-line); padding-top: 8px; }}
</style>
<div class="af-hero">
  <img src="{logo_uri}" alt="AssaFlex logo">
  <div class="af-hero-text">
    <h1>AssaFlex Calculation Document</h1>
    <p>Manufacturer of Bridge Components</p>
  </div>
</div>
<div class="af-page">
  <div class="af-header-lines">
    {"".join(f'<p>{line}</p>' if i < len(header_lines) - 1 else f'<p class="af-title">{line}</p>' for i, line in enumerate(header_lines))}
  </div>

  <h2>Basic Design Parameters</h2>
  {basic_params}

  <h2>Mechanical Properties</h2>
  {mech_props}

  <h2>Graphical Illustration of All Possible Operating Mechanical Properties</h2>
  <div class="af-plot"><img src="{plot_uri}" alt="Capacity surface plot"></div>
  <ul>
    <li>Every point of the surface plotted above shows a possible three dimensional Maximum capacity of this bearing.</li>
    <li>All the points beneath the plotted surface can also be operational points of this bearing.</li>
  </ul>

  <h2>Tests Being Conducted</h2>
  <ul>
    <li>{escape(TESTS_CONDUCTED_INTRO)}
        In case of the bearing pad(s) needed for this project, the bearing pads are tested up to the load
        of {_fmt((doc.test_load or 0)/1000, ' kN', 0)} based on standard test format of compression test
        level-3 in EN-1337-3 Annex G.</li>
    {tests_bullets}
  </ul>

  <h2>General Notes</h2>
  <ul>
    {notes_bullets}
  </ul>

  <p class="af-footer">Generated by the AssaFlex Bearing Design Tool. This computed document is
  preliminary and requires engineering sign-off before being issued to a client.</p>
</div>
</div>
""".strip()
