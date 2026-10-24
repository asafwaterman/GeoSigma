"""Iso-resistivity maps of the Southern Arava reinterpretation (Paparo 1969, Figs PDF).

Twenty map sheets (pages 20-40, page 35 blank) give, at every sounding, the resistivity
interpreted at 50, 100 and 200 m depth and at 25 m below sea level, in ohm.cm. Each
sounding is drawn as a small circle with its label (file-point) above and the value
below. Most soundings here have no field sheet in the report (files 224, 806, 807, 844
and others), so these maps are the only record of them.

``extraction/map_points.json`` holds, per page, the circle positions (200 dpi page
pixels; found by script or, where the script missed them, by eye), the labels and
values read by eye, and the page's pixel-to-grid calibration. The calibration is an
affine fit to the soundings that also have a field sheet with printed coordinates
where a page has at least 10 of them, and otherwise the fitted 1 km grid lines and
their printed km labels. Old Israel Grid km; northings here are printed as 880-960
and stored with the false origin, as on the sheets.

Points whose label prints only the point number (runs following a "224-..." label)
are taken as file 224. Soundings that have a field sheet are skipped. Values are divided
by 100 to ohm.m.

What the map values are: although each map is titled "depth 50 m" (etc.), its values are
not read off the layered models. At the 81 soundings that have both a field sheet and map
values, the map value equals the sheet model's resistivity at that depth in about two
thirds of 213 comparisons (where layers are thick), but differs by up to 4x elsewhere, and
where checked it follows the measured apparent-resistivity curve at AB/2 = the map depth
(e.g. 400-12: maps 2440 and 2810 ohm.cm at 50 and 100 m, curve about 2500 and 2900, model
6200 and 640). So they are stored as measured data (L1): apparent resistivity against
AB/2, one curve per sounding. The 25 m below sea level maps cannot be placed on the AB/2
axis without the sounding's elevation, so their value is kept in the dataset notes.

Run: ``python -m geosigma.extract.arava_maps``.
"""
from __future__ import annotations

import json
import re
from datetime import date

import numpy as np
import yaml

from ..store import SURVEYS_DIR

SURVEY = "paparo-1969-southern-arava"
SDIR = SURVEYS_DIR / SURVEY
# page -> (depth below ground m, or None) and (depth below sea level m, or None)
SLICES = {**{p: ("below_ground", 50) for p in range(20, 25)}, **{p: ("below_ground", 100) for p in range(25, 30)},
          **{p: ("below_ground", 200) for p in range(30, 35)}, **{p: ("below_sea_level", 25) for p in range(36, 41)}}


def norm_label(label: str) -> str | None:
    label = str(label).strip()
    if re.fullmatch(r"\d{3}-\d+[A-Z]?", label):
        f, n = label.split("-")
        return f"{'224' if f == '244' else f}-{n}"  # "244-199" sits in a 224 run: a drafting slip
    if re.fullmatch(r"\d+", label):
        return f"224-{label}"
    return None


def to_grid(cal: dict, x: float, y: float) -> tuple[float, float]:
    e = cal["E"][0] * x + cal["E"][1] * y + cal["E"][2]
    n = cal["N"][0] * x + cal["N"][1] * y + cal["N"][2]
    return e, n


def run() -> list[dict]:
    mp = json.loads((SDIR / "extraction" / "map_points.json").read_text())
    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    have_sheet = {s["id"] for s in survey.get("sites", []) if s["id"].startswith("625-")}
    obs: dict[str, dict] = {}
    for p, page in mp["pages"].items():
        ref, depth = SLICES[int(p)]
        for q in page["points"]:
            lab = norm_label(q["label"]) if q.get("label") is not None else None
            if not lab:
                continue
            sid = f"map-{lab}"
            if f"625-{lab}" in have_sheet:
                continue
            e, n = to_grid(page["calib"], q["x"], q["y"])
            o = obs.setdefault(sid, {"label": lab, "pos": [], "vals": {}, "unsure": set(), "bare": True})
            o["bare"] &= "-" not in str(q["label"])
            o["pos"].append((e, n))
            if q.get("value") is not None:
                o["vals"].setdefault((ref, depth), []).append(float(q["value"]))
                if not q.get("sure", True):
                    o["unsure"].add(depth)
    today = date.today().isoformat()
    sites, ds = [s for s in survey.get("sites", []) if not s["id"].startswith("map-")], []
    for sid, o in sorted(obs.items()):
        pos = np.array(o["pos"])
        e, n = np.median(pos, 0)
        spread = float(np.max(np.hypot(*(pos - [e, n]).T))) * 1000 if len(pos) > 1 else None
        if spread is not None and spread > 300:  # the same label in different places: keep the first sheet's
            e, n = pos[0]
        sites.append({"id": sid, "name": f"Sounding {o['label']} (Southern Arava maps)",
                      "coords": {"x": round(e * 1000), "y": round(n * 1000), "crs": "EPSG:28193", "source": "map",
                                 "accuracy_m": 50},
                      "notes": "Position read from the 1:20,000 iso-resistivity maps."
                               + (" File number not printed; taken as 224." if o["bare"] else "")})
        bg = sorted((d, float(np.median(v)) / 100) for (r, d), v in o["vals"].items() if r == "below_ground")
        bsl = [float(np.median(v)) / 100 for (r, d), v in o["vals"].items() if r == "below_sea_level"]
        if not bg and not bsl:
            continue
        bsl_note = (f" The 25 m below sea level map gives {bsl[0]:.4g} ohm.m here (not plotted: the AB/2 it "
                    "corresponds to depends on the sounding's elevation, which the maps do not give).") if bsl else ""
        ds.append({
            "id": f"{SURVEY}-maps-{o['label']}", "survey": SURVEY, "site": sid, "method": "VES", "level": "L1",
            "representation": "sounding_curve" if bg else "qualitative", "x_quantity": "ab2" if bg else None,
            "measured_on": None,
            "confidence": "C" if o["unsure"] else "B", "status": "draft",
            "curve": [{"x": d, "rho_a": float(f"{r:.4g}")} for d, r in bg],
            "summary": None if bg else (f"Printed only on the 25 m below sea level iso-resistivity map: {bsl[0]:.4g} ohm.m "
                                        "(apparent resistivity, not a model value)."),
            "provenance": {"document": "figs", "pages": sorted(int(p) for p in mp["pages"]),
                           "figure": "Iso-resistivity maps at 50, 100 and 200 m 'depth' and at 25 m below sea level",
                           "method": "manual", "tool": "geosigma.extract.arava_maps (positions by script, values by eye)",
                           "extracted_on": today, "notes": "Values printed in ohm.cm at each sounding; divided by 100."},
            "notes": ("Values printed on the iso-resistivity maps, placed at AB/2 = the map's depth. They follow the "
                      "measured apparent-resistivity curve, not the interpreted layered model (see "
                      "geosigma.extract.arava_maps), so they are not used as model values at depth; a depth missing "
                      "here had no value printed." + bsl_note
                      + (" Some digits were hard to read." if o["unsure"] else "")),
        })
    survey["sites"] = sites
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    (SDIR / "datasets" / "map_slices.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    ds = run()
    print(len(ds), "datasets,", len({d["site"] for d in ds}), "sites")
