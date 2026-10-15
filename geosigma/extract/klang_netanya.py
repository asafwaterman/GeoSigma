"""Klang (1974), South Netanya MT survey, first phase (MT/118/74, for Sonol).

Four soundings, May 1974. Each field sheet (PDF pages 18-21) prints the interpreted
layered model in its CALC. RES. band, here in ohm.m, with boundary depths in m, and
the sheet's coordinates (Old Israel Grid) and elevation. Sounding 1 has two models,
A and B, drawn as two curves. Figure 3 (page 16) repeats the same models as a cross
section and was used to check the typing. The report gives errors of about 15-20 %
in resistivities and depths because of poor data quality.

The apparent-resistivity curves are faint on a coloured scan and are not traced.

Run: ``python -m geosigma.extract.klang_netanya``.
"""
from __future__ import annotations

import json
from datetime import date

import yaml

from ..store import SURVEYS_DIR

SURVEY = "klang-1974-mt-south-netanya"
SDIR = SURVEYS_DIR / SURVEY

# page, sounding, model, x, y (Old Israel Grid m as printed), elevation m,
# layers as (rho ohm.m, rho_min, note) with None for an unknown value, boundary depths m.
SHEETS = [
    (18, "1", "A", 135200, 188700, 40, [(10, None, None), (3.3, None, None), (26.0, None, None), (2.4, None, None),
                                        (140, None, "printed as '140 probably high'")], [1200, 2400, 8400, 12600]),
    (18, "1", "B", 135200, 188700, 40, [(7, None, None), (35, None, None), (2.6, None, None), (33.6, None, None),
                                        (2.6, None, None), (None, 90, "printed as '>90.0 probably high'")],
     [480, 1200, 2300, 9100, 13600]),
    (19, "2", None, 138700, 189950, 30, [(2.8, None, None), (70, None, None), (0.40, None, None),
                                         (None, 30, "printed as '>30 probably high'")], [630, 5700, 6900]),
    (20, "3", None, 140400, 190400, 40, [(1.8, None, None), (55.0, None, None), (1.0, None, None),
                                         (None, 1.0, "printed as 'probably high', no value")], [550, 6650, 8200]),
    (21, "4", None, 143050, 189150, 50, [(2, None, None), (40, None, None)], [560]),
]
NOTES = {
    "3": "Deepest boundary printed as '8200 ?'.",
    "4": "Second layer marked '(?)' in Figure 3; the model stops at about 6.3 km there.",
}


def site_id(no: str) -> str:
    return f"SN-{no}"


def datasets() -> list[dict]:
    today = date.today().isoformat()
    out = []
    for page, no, model, *_xyz, layers, depths in SHEETS:
        tops = [0.0] + [float(d) for d in depths]
        lays = []
        for i, (rho, rmin, note) in enumerate(layers):
            lay = {"top_m": tops[i], "bottom_m": tops[i + 1] if i + 1 < len(tops) else None}
            if rho is not None:
                lay["rho_ohmm"] = float(rho)
            if rmin is not None:
                lay["rho_min"] = float(rmin)
            if note:
                lay["note"] = note
            lays.append(lay)
        ds = {
            "id": f"klang1974-netanya-{no}{'-model-' + model if model else ''}", "survey": SURVEY, "site": site_id(no),
            "method": "MT", "level": "L2", "representation": "model_1d", "measured_on": "1974-05",
            "model_type": "layered", "depth_max_m": float(depths[-1]), "confidence": "C", "status": "draft", "line": "S-Netanya",
            "layers": lays,
            "provenance": {"document": "main", "pages": [page, 16], "figure": f"M.T.P. No. {no} field sheet; Figure 3",
                           "table": "CALC. RES. band" + (f", model {model}" if model else ""), "method": "manual",
                           "tool": "geosigma.extract.klang_netanya", "extracted_on": today,
                           "notes": "Printed in ohm.m. Depths in m below ground as on the sheet."},
            "notes": " ".join(x for x in [
                "Report: errors of about 15-20 % in resistivity and depth (poor data).",
                NOTES.get(no, ""),
                "Alternative interpretation drawn on the same sheet." if model == "B" else ""] if x),
        }
        if model == "B":
            ds["reinterprets"] = f"klang1974-netanya-{no}-model-A"
        out.append(ds)
    return out


def run() -> list[dict]:
    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    seen, sites = set(), []
    for _p, no, _m, x, y, z, *_ in SHEETS:
        if no in seen:
            continue
        seen.add(no)
        sites.append({"id": site_id(no), "name": f"MT sounding {no} (South Netanya)",
                      "coords": {"x": x, "y": y, "crs": "EPSG:28193", "source": "table", "accuracy_m": 50},
                      "elevation_m": float(z), "line": "S-Netanya"})
    survey["sites"] = sites
    survey["documents"][0].update(sha256="7c3faf70f05ba9b5c6070b7ed9fd13241b3e27118af93122344d25d0fc939cd0", pages=23)
    survey["extraction_status"] = "complete"
    survey["notes"] = ("4 soundings, 12-17 May 1974, along a line south of Netanya. Layered models typed from the "
                       "field sheets (ohm.m) and checked against Figure 3; sounding 1 has models A and B. "
                       "Curves not traced.")
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    ds = datasets()
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "models.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    for d in run():
        print(d["id"], [(l["top_m"], l.get("rho_ohmm"), l.get("rho_min")) for l in d["layers"]])
