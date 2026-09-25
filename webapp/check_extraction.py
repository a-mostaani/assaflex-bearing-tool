"""
Run the real AI extraction on a drawing and compare it with a hand
transcription -- the accuracy check for webapp/extract.py.

    ANTHROPIC_API_KEY=... python -m webapp.check_extraction \\
        reference/H3428_Bridge_Bearing_Drawings_1.pdf \\
        schedules/H3428_A0_A5_bearing_1.1.json

Prints every load-combination value that differs, the envelope, and what the
model and the plain-code checks flagged. Exit code 0 only if every value
matches. Makes one paid API call per run.
"""

from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path

from bearing_tool.schedule import BearingSchedule

from .extract import extract_schedule

FIELDS = ["vertical_kN", "transverse_kN", "longitudinal_kN", "long_displacement_mm",
          "trans_displacement_mm", "rotation_mrad", "transverse_rotation_mrad"]


def main(pdf_path: str, reference_json: str, bearing_mark: str = "") -> int:
    ref_schedule = BearingSchedule.from_client_schedule_json(reference_json)
    ref = {(c.limit_state, c.case): asdict(c) for c in ref_schedule.combinations}

    media_type = "application/pdf" if pdf_path.lower().endswith(".pdf") else (
        "image/png" if pdf_path.lower().endswith(".png") else "image/jpeg")
    t0 = time.time()
    result = extract_schedule(Path(pdf_path).read_bytes(), media_type, bearing_mark)
    print(f"Model {result.model}, {time.time() - t0:.0f}s, "
          f"{len(result.combinations)} rows (reference: {len(ref)})\n")

    got = {(r["limit_state"], r["case"]): r for r in result.combinations}
    mismatches = 0
    for key in sorted(set(ref) | set(got)):
        if key not in got:
            print(f"MISSING   {key[0]} {key[1]}"); mismatches += 1; continue
        if key not in ref:
            print(f"EXTRA     {key[0]} {key[1]}: {got[key]}"); mismatches += 1; continue
        for f in FIELDS:
            if abs(got[key][f] - ref[key][f]) > 1e-6:
                print(f"DIFF      {key[0]} {key[1]} {f}: got {got[key][f]}, expected {ref[key][f]}")
                mismatches += 1

    env_got = (result.max_longitudinal_mm, result.max_transverse_mm, result.max_height_mm)
    env_ref = (ref_schedule.max_longitudinal_mm, ref_schedule.max_transverse_mm, ref_schedule.max_height_mm)
    if env_got != env_ref:
        print(f"DIFF      envelope: got {env_got}, expected {env_ref}"); mismatches += 1

    values = len(ref) * len(FIELDS) + 3
    print(f"\n{values - mismatches} of {values} values match.")
    print("\nModel warnings:"); [print("  -", w) for w in result.warnings]
    print("Checks:"); [print("  -", c) for c in result.checks]
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
