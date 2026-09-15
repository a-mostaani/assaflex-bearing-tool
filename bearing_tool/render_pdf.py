"""
Renders a ``CalculationDocument`` (see ``calc_document.py``) as a downloadable
PDF, built directly with ReportLab (not an HTML->PDF converter).

ReportLab was chosen over WeasyPrint/xhtml2pdf because it has no native/
system library dependencies (no Cairo/Pango) -- this tool is also packaged as
a portable Windows app (``desktop/build_portable_app.*``) that installs pure
``pip`` wheels into a bundled embeddable Python with no system libs
available, so a converter that shells out to or links against native
rendering libraries isn't realistic to bundle there.

Same brand tokens as ``render_html.py`` (and the request form): deep green +
lime accent, Poppins (bundled under ``assets/fonts``, OFL-licensed).
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle

from .calc_document import CalculationDocument, TESTS_CONDUCTED_INTRO
from .surface import plot_capacity_surface

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

AF_GREEN = colors.HexColor("#004439")
AF_LIME = colors.HexColor("#6db942")
AF_INK = colors.HexColor("#142420")
AF_BODY = colors.HexColor("#2b3733")
AF_MUTED = colors.HexColor("#5b6864")
AF_LINE = colors.HexColor("#dbe3df")

_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("Poppins", str(FONTS_DIR / "Poppins-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Poppins-Medium", str(FONTS_DIR / "Poppins-Medium.ttf")))
    pdfmetrics.registerFont(TTFont("Poppins-SemiBold", str(FONTS_DIR / "Poppins-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("Poppins-Bold", str(FONTS_DIR / "Poppins-Bold.ttf")))
    _FONTS_REGISTERED = True


def _fmt(value, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}{unit}"


def _styles() -> dict:
    return {
        "title": ParagraphStyle("af-title", fontName="Poppins-Bold", fontSize=13,
                                 textColor=AF_GREEN, spaceAfter=2),
        "subtitle": ParagraphStyle("af-subtitle", fontName="Poppins", fontSize=9,
                                    textColor=AF_MUTED, spaceAfter=10),
        "h2": ParagraphStyle("af-h2", fontName="Poppins-SemiBold", fontSize=11,
                              textColor=AF_INK, spaceBefore=14, spaceAfter=6,
                              borderColor=AF_GREEN, borderWidth=0),
        "body": ParagraphStyle("af-body", fontName="Poppins", fontSize=8.5,
                                textColor=AF_BODY, leading=12.5),
        "footer": ParagraphStyle("af-footer", fontName="Poppins", fontSize=7,
                                  textColor=AF_MUTED),
    }


def _param_table(rows: list[tuple[str, str, str]]) -> Table:
    styles = _styles()
    data = [
        [
            Paragraph(f"<i>{sym}</i>", ParagraphStyle("sym", fontName="Poppins-SemiBold",
                                                        fontSize=8.5, textColor=AF_GREEN)),
            Paragraph(f"<b>{val}</b>", ParagraphStyle("val", fontName="Poppins-SemiBold",
                                                        fontSize=8.5, textColor=AF_INK)),
            Paragraph(desc, styles["body"]),
        ]
        for sym, val, desc in rows
    ]
    table = Table(data, colWidths=[22 * mm, 28 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, AF_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def render_calculation_document_pdf(doc: CalculationDocument) -> bytes:
    """Returns the PDF file's bytes."""
    _register_fonts()
    styles = _styles()

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )

    story = []

    logo = Image(str(ASSETS_DIR / "assaflex_logo.png"), width=32 * mm, height=32 * mm * 132 / 400)
    header_table = Table(
        [[logo, Paragraph(
            "<b>AssaFlex Calculation Document</b><br/>"
            "<font color='#6db942' size=8>Manufacturer of Bridge Components</font>",
            ParagraphStyle("hdr", fontName="Poppins-Bold", fontSize=13, textColor=colors.white, leading=16),
        )]],
        colWidths=[38 * mm, 130 * mm],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AF_GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    if doc.client_name or doc.project_name:
        bits = []
        if doc.client_name:
            bits.append(f"To be announced to {doc.client_name}")
        if doc.project_name:
            bits.append(f"for the project {doc.project_name}")
        story.append(Paragraph(", ".join(bits), styles["subtitle"]))
    story.append(Paragraph(doc.title, styles["title"]))

    story.append(Paragraph("Basic Design Parameters", styles["h2"]))
    story.append(_param_table([
        ("a", f"{doc.w:.0f} mm", "width (longitudinal direction)"),
        ("b", f"{doc.l:.0f} mm", "length (transverse direction)"),
        ("n", f"{doc.n}", "number of internal elastomer layers"),
        ("t_si", f"{doc.ts:.1f} mm", "thickness of internal steel reinforcements"),
        ("t_i", f"{doc.ti:.1f} mm", "thickness of each internal elastomer layer"),
        ("g", f"{doc.g:g} N/mm²", "shear modulus"),
        ("mu", f"{doc.mu:g}", "friction coefficient"),
        ("msf", f"{doc.msf:g}", "manufacturing safety factor"),
        ("type", doc.bearing_type_label, "bearing type"),
    ]))

    story.append(Paragraph("Mechanical Properties", styles["h2"]))
    story.append(_param_table([
        ("V_x,d", f"±{_fmt(doc.max_vectorial_shear_deflection, ' mm')}",
         "Maximum Vectorial Shear Deflection"),
        ("F_z,design", _fmt((doc.max_load_design or 0) / 1000, " kN", 0),
         "Maximum Vertical Load Combined with Full Shear Deflection and Rotation"),
        ("F_z,max", _fmt((doc.max_load_buckling or 0) / 1000, " kN", 0),
         "Maximum Vertical Load With no rotation and full shear deflection, "
         "considering buckling stability criteria"),
        ("F_z,min", _fmt((doc.min_load_no_slip or 0) / 1000, " kN", 0),
         "Minimum Vertical Load to prevent slipping of the bearing pad when in "
         "maximum shear deflection"),
        ("alpha_a,d", _fmt(doc.max_rotation, " rad", 5),
         "Maximum Rotation along the width in Full Vertical Load and Shear Deflection"),
        ("sum v_z,d", _fmt(doc.max_vertical_deflection, " mm"),
         "Maximum Vertical Deflection"),
        ("R_xy", _fmt((doc.max_horizontal_load or 0) / 1000, " kN", 1),
         "Maximum horizontal load exerted by the bearing on the foundation to "
         "resist translatory movement, to be considered on structural design"),
    ]))

    story.append(Paragraph("Graphical Illustration of All Possible Operating "
                            "Mechanical Properties", styles["h2"]))
    fig = plot_capacity_surface(doc.surface)
    plot_buf = io.BytesIO()
    fig.savefig(plot_buf, format="png", dpi=150)
    import matplotlib.pyplot as plt
    plt.close(fig)
    plot_buf.seek(0)
    story.append(Image(plot_buf, width=160 * mm, height=160 * mm * 6.5 / 9))
    story.append(ListFlowable([
        ListItem(Paragraph("Every point of the surface plotted above shows a possible "
                            "three dimensional Maximum capacity of this bearing.", styles["body"])),
        ListItem(Paragraph("All the points beneath the plotted surface can also be "
                            "operational points of this bearing.", styles["body"])),
    ], bulletType="bullet", start="•"))

    story.append(Paragraph("Tests Being Conducted", styles["h2"]))
    test_load_kn = _fmt((doc.test_load or 0) / 1000, " kN", 0)
    story.append(ListFlowable([
        ListItem(Paragraph(
            f"{TESTS_CONDUCTED_INTRO} In case of the bearing pad(s) needed for this "
            f"project, the bearing pads are tested up to the load of {test_load_kn} "
            "based on standard test format of compression test level-3 in "
            "EN-1337-3 Annex G.", styles["body"])),
        *[ListItem(Paragraph(b, styles["body"])) for b in doc.tests_conducted],
    ], bulletType="bullet", start="•"))

    story.append(Paragraph("General Notes", styles["h2"]))
    story.append(ListFlowable(
        [ListItem(Paragraph(n, styles["body"])) for n in doc.general_notes],
        bulletType="bullet", start="•",
    ))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Generated by the AssaFlex Bearing Design Tool. This computed document is "
        "preliminary and requires engineering sign-off before being issued to a client.",
        styles["footer"],
    ))

    pdf.build(story)
    return buf.getvalue()
