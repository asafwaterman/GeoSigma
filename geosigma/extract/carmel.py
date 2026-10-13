"""Rotstein (1979) Carmel geoelectric measurements: one Schlumberger sounding (S1)
and two equatorial dipole soundings (E2, E3), read from the field sheets (PDF
pages 6-8, rendered at 150 dpi). Points are pixel centres read by eye; axes are
log-log with about 496 px per decade.

Run: ``python -m geosigma.extract.carmel``.
"""
from __future__ import annotations

import json
from datetime import date

import yaml

from ..store import SURVEYS_DIR

SURVEY = "rotstein-1979-carmel"
SDIR = SURVEYS_DIR / SURVEY
DEC = 496.0

SHEETS = {
    "S1": {"page": 6, "x0": (62, 0), "y0": (105, 3), "xq": "ab2", "coords": (157900, 233050),
           "note": "Sheet prints E-1579000; read as 157900 (one extra zero), matching the location map.",
           "pts": [(153, 682), (218, 636), (265, 602), (302, 578), (364, 535), (409, 502), (448, 487), (508, 458),
                   (558, 429), (600, 407), (642, 379), (706, 331), (755, 313), (777, 320), (797, 311), (857, 309),
                   (904, 315), (946, 330), (991, 280), (992, 321), (1057, 266), (1096, 263), (1142, 258), (1198, 260),
                   (1251, 267), (1283, 262), (1290, 285), (1348, 306), (1398, 356), (1443, 359), (1501, 351),
                   (1548, 334), (1575, 334)]},
    "E2": {"page": 7, "x0": (45, 2), "y0": (110, 2), "xq": "effective separation", "coords": (157800, 232350),
           "elev": 450,
           "pts": [(399, 322), (401, 381), (412, 244), (432, 291), (491, 360), (568, 241), (603, 530), (634, 237),
                   (639, 724), (778, 485)]},
    "E3": {"page": 8, "x0": (60, 2), "y0": (103, 2), "xq": "effective separation", "coords": (154650, 237750),
           "elev": 500,
           "pts": [(367, 661), (380, 743), (392, 759), (414, 856), (467, 749), (489, 708), (538, 931), (570, 740),
                   (607, 884), (643, 853), (668, 778), (715, 717), (762, 866)]},
}


def curve(s):
    (xp, xe), (yp, ye) = s["x0"], s["y0"]
    pts = [(float(f"{10 ** (xe + (x - xp) / DEC):.3g}"), float(f"{10 ** (ye - (y - yp) / DEC):.3g}")) for x, y in s["pts"]]
    return [{"x": x, "rho_a": r} for x, r in sorted(pts)]


def run():
    sfile = SDIR / "survey.yaml"
    sv = yaml.safe_load(sfile.read_text())
    sv["methods"] = ["VES", "DIPOLE"]
    sv["sites"] = [{"id": k, "name": f"{'Schlumberger' if k == 'S1' else 'Equatorial dipole'} sounding {k}",
                    "coords": {"x": s["coords"][0], "y": s["coords"][1], "crs": "EPSG:28193", "source": "table"},
                    "elevation_m": s.get("elev"), "notes": s.get("note")} for k, s in SHEETS.items()]
    sv["extraction_status"] = "complete"
    sfile.write_text(yaml.safe_dump(sv, sort_keys=False, allow_unicode=True, width=110))
    today = date.today().isoformat()
    ds = []
    for k, s in SHEETS.items():
        ds.append({
            "id": f"rotstein1979-carmel-{k}-curve", "survey": SURVEY, "site": k,
            "method": "VES" if k == "S1" else "DIPOLE", "level": "L1", "representation": "sounding_curve",
            "measured_on": "1979", "confidence": "B", "status": "draft", "x_quantity": s["xq"], "curve": curve(s),
            "digitisation_error": "+-0.01 log10 (point centres read by eye)",
            "provenance": {"document": "main", "pages": [s["page"]], "figure": f"Field sheet {k}",
                           "method": "digitised_manual", "tool": "geosigma.extract.carmel", "extracted_on": today},
        })
    # S1 interpretation drawn on the sheet: two alternatives A and B.
    common = {"survey": SURVEY, "site": "S1", "method": "VES", "level": "L2", "representation": "model_1d",
              "measured_on": "1979", "confidence": "C", "status": "draft", "model_type": "layered",
              "depth_max_m": 400, "digitisation_error": "+-10 m on interface depths",
              "provenance": {"document": "main", "pages": [6], "method": "digitised_manual",
                             "tool": "geosigma.extract.carmel", "extracted_on": today}}
    ds.append({**common, "id": "rotstein1979-carmel-S1-model-A",
               "layers": [{"top_m": 0, "bottom_m": 350, "rho_ohmm": 480},
                          {"top_m": 350, "bottom_m": None, "note": "LOW (no value given)"}],
               "provenance": {**common["provenance"], "figure": "Field sheet S1, model A"},
               "notes": "Near-surface low-resistivity cover seen at AB/2 < 20 m is not part of the drawn model."})
    ds.append({**common, "id": "rotstein1979-carmel-S1-model-B", "reinterprets": "rotstein1979-carmel-S1-model-A",
               "layers": [{"top_m": 0, "bottom_m": 250, "rho_ohmm": 480},
                          {"top_m": 250, "bottom_m": 310, "note": "LOW (no value given)"},
                          {"top_m": 310, "bottom_m": None, "note": "HIGH (no value given)"}],
               "provenance": {**common["provenance"], "figure": "Field sheet S1, model B"},
               "notes": "Alternative interpretation drawn on the same sheet."})
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "soundings.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    for d in run():
        print(d["id"], d.get("curve", d.get("layers"))[:3])
