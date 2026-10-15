"""Klang (1970), MT soundings on the Afiq-Lot traverse (Report 1044, MT/665/69).

The appendix (PDF pages 38-57) has the field sheets of soundings 1, 2, 4-17 and 19-22,
measured March-November 1969. Each sheet's CALC. RES. band prints the interpreted
layered model: one resistivity per complex (ohm.cm, divided by 100 here) and the depth
of each boundary below ground. Coordinates (Old Israel Grid) and elevation are typed
from the sheet. Figure 9 (page 33), the interpreted section along the traverse, shows
the same models against sea level and was used to check the typing. A last complex
printed as infinity is stored as a lower bound equal to the complex above.

On sheet 10 the two deep boundary labels are written over the band lines; they are
read from Figure 9 to the nearest 100 m. The curves are not traced yet.

Run: ``python -m geosigma.extract.klang_general``.
"""
from __future__ import annotations

import json
from datetime import date

import yaml

from ..store import SURVEYS_DIR

SURVEY = "klang-1970-mt-general"
SDIR = SURVEYS_DIR / SURVEY
INF = None  # printed as infinity

# page, sounding, location, x, y (Old Israel Grid m as printed), elevation m,
# rho (ohm.cm), boundary depths (m), note.
SHEETS = [
    (38, "1", "Gilat", 115250, 89600, 140, [300, 15000, 100, INF], [160, 3400, 3900], None),
    (39, "2", "Gilat", 112500, 87950, 128, [400, 10000, 100, INF], [200, 4200, 5000], None),
    (40, "4", "Sharsheret", 109160, 87430, 91, [200, 10000, 200, INF], [150, 4000, 5200], None),
    (41, "5", "Sharsheret", 108415, 88735, 103, [400, 4000, 400, 100000], [280, 2520, 4300], None),
    (42, "6", "Sharsheret", 107100, 89850, 105, [230, 11500, 230, INF], [250, 2750, 4400], None),
    (43, "7", "Gerar", 117200, 89650, 140, [600, 120000, 600, INF], [310, 4350, 5350], None),
    (44, "8", "Gerar", 116600, 91600, 155, [600, 60000, 200, INF], [350, 4000, 5200], None),
    (45, "9", "Afiq", 103386, 94304, 87, [900, 200, 22500], [840, 2650], None),
    (46, "10", "Shoval", 125750, 88700, 225, [320, 1600, 8000, 1000, 8000], [20, 720, 2800, 5700],
     "The 2800 and 5700 m boundaries are written over the band lines and read from Figure 9 (+-100 m)."),
    (47, "11", "Ziqlag", 135940, 90555, 340, [800, 2400, 800, INF], [150, 1350, 6750], None),
    (48, "12", "Lahav", 139100, 80750, 370, [220, 5500, 1500, 137500], [55, 1700, 8500], None),
    (49, "13", "Shoket", 142800, 75700, 370, [240, 12000, 240, 12000], [60, 660, 2000], None),
    (50, "14", "Shoket", 149800, 74200, 485, [7500, 15000, 750, 375000], [360, 2600, 4500], None),
    (51, "15", "Kasif", 156300, 72750, 475, [1600, 23300, 1600, INF], [150, 900, 4500], None),
    (52, "16", "Arad", 164850, 74900, 510, [700, 7000, 700, INF], [150, 750, 5250], None),
    (53, "17", "Tamrur", 180850, 65250, 105, [1500, 22500, 300, 337500], [770, 2310, 3400], None),
    (54, "19", "Kidod", 171900, 76750, 600, [1700, 340, 42500, 30, INF], [200, 500, 5000, 5300], None),
    (55, "20", "Lot", 185300, 59650, -360, [450, 45, 6750, 45, INF], [80, 140, 3000, 3600], None),
    (56, "21", "Shoval", 121150, 90450, 170, [300, 1500, 30000, 60, INF], [140, 1000, 7000, 7500], None),
    (57, "22", "Lahav", 132050, 90000, 290, [450, 2700, 100, INF], [160, 4500, 5100], None),
]
SHA256 = "1774b3265979683d6a820267b286d8b3db881a83ccdb0869d90b27273dcbea85"


def site_id(no: str) -> str:
    return f"AL-{no}"


def datasets() -> list[dict]:
    today = date.today().isoformat()
    out = []
    for page, no, _loc, _x, _y, _z, rho, depths, note in SHEETS:
        tops = [0.0] + [float(d) for d in depths]
        layers = []
        for i, r in enumerate(rho):
            lay = {"top_m": tops[i], "bottom_m": tops[i + 1] if i + 1 < len(tops) else None}
            if r is None:
                lay.update(rho_min=rho[i - 1] / 100, note="printed as infinity")
            else:
                lay["rho_ohmm"] = r / 100
            layers.append(lay)
        out.append({
            "id": f"klang1970-afiqlot-{no}-layered", "survey": SURVEY, "site": site_id(no), "method": "MT",
            "level": "L2", "representation": "model_1d", "measured_on": "1969", "model_type": "layered",
            "depth_max_m": float(depths[-1]), "confidence": "C" if note else "B", "status": "draft",
            "layers": layers, "line": "Afiq-Lot",
            "provenance": {"document": "main", "pages": [page, 33], "figure": f"M.T.P. No. {no} field sheet; Figure 9",
                           "table": "CALC. RES. band", "method": "manual", "tool": "geosigma.extract.klang_general",
                           "extracted_on": today,
                           "notes": "Printed in ohm.cm; divided by 100. Depths below ground."},
            "notes": note or "",
        })
    return out


def run() -> list[dict]:
    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    survey["sites"] = [{
        "id": site_id(no), "name": f"MT sounding {no} ({loc})", "line": "Afiq-Lot",
        "coords": {"x": x, "y": y, "crs": "EPSG:28193", "source": "table", "accuracy_m": 50},
        "elevation_m": float(z)} for _p, no, loc, x, y, z, *_ in SHEETS]
    survey["documents"][0].update(sha256=SHA256, pages=59)
    survey["extraction_status"] = "partial"
    survey["notes"] = ("20 MT soundings along the Afiq-Lot traverse, 1969. Layered models typed from the field "
                       "sheets (ohm.cm, stored in ohm.m) and checked against Figure 9. Soundings 3, 18 and 23 have "
                       "no sheet in the appendix. Apparent-resistivity curves not traced yet.")
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    ds = datasets()
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "models.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    for d in run():
        print(d["id"], [(l["top_m"], l.get("rho_ohmm") or l.get("rho_min")) for l in d["layers"]])
