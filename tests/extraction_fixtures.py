"""A model answer for the H3428 drawing in the extraction tool's schema,
built from the hand transcription in schedules/ -- i.e. what a perfect
extraction should return. Used to test everything downstream of the API call."""

import json
from pathlib import Path

H3428_PATH = Path(__file__).resolve().parent.parent / "schedules" / "H3428_A0_A5_bearing_1.1.json"


def h3428_model_answer() -> dict:
    d = json.loads(H3428_PATH.read_text())
    combos = []
    for c in d["combinations"]:
        row = {"limit_state": c["limit_state"], "case": c["case"],
               "vertical_kN": c.get("vertical_kN", c.get("coincident_vertical_kN")),
               "transverse_kN": c.get("transverse_kN", c.get("coincident_transverse_kN")),
               "longitudinal_kN": c.get("longitudinal_kN", c.get("coincident_longitudinal_kN")),
               "coincident_displacement_mm": c.get("coincident_displacement_mm"),
               "coincident_rotation_mrad": c.get("coincident_rotation_mrad")}
        combos.append(row)
    strip = lambda block: {k: v for k, v in block.items() if not k.startswith("_") and isinstance(v, dict)}
    env = d["maximum_bearing_dimensions_mm"]
    return {
        "found_schedule": True,
        "project_name": "H3428 - Immingham Eastern Ro-Ro Terminal, Robinson Bridge",
        "drawing_ref": d["drawing_ref"],
        "bearing_mark": "1.1",
        "other_bearing_marks": [],
        "maximum_bearing_dimensions_mm": {"longitudinal": env["upper_surface"]["longitudinal"],
                                          "transverse": env["upper_surface"]["transverse"],
                                          "overall_height": env["overall_height"]},
        "stated_min_vertical_kN": 365,
        "combinations": combos,
        "displacement_mm": strip(d["displacement_mm"]),
        "rotation_mrad": {k: v for k, v in d["rotation_mrad"].items() if k in ("SLS", "ULS", "ALS")},
        "warnings": ["SLS Max Vertical and Min Vertical: rotation labelled [rad] on the drawing; read as mrad."],
    }
