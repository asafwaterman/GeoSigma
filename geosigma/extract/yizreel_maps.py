"""Roving-dipole apparent-resistivity maps, Yizreel and Harod valleys (Rotstein et al. 1977).

The Maps PDF (pages 3-36, Figures 3-36) has one map per transmitter ("source"): the
source dipole is drawn as a line, and every receiver station carries its number and the
apparent resistivity measured there (ohm.m). Station numbers belong to the survey, so
the same number on different maps is the same place.

``extraction/roving_dipole.json`` holds, per page, the station circles (200 dpi page
pixels; found by script or by eye), the numbers and values read by eye, the source
dipole ends, and an affine pixel-to-grid calibration. The calibration started from the
grid lines and their printed km labels, then was refined by fitting each page to the
median station positions over all maps. Old Israel Grid km. A reading more than 400 m
from its station's median position (a misread number, most likely) is flagged
``outlier`` and left out.

Run: ``python -m geosigma.extract.yizreel_maps``.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import yaml

from ..store import SURVEYS_DIR

SURVEY = "rotstein-1977-yizreel-harod"
SDIR = SURVEYS_DIR / SURVEY


def to_grid(cal: dict, x: float, y: float) -> tuple[float, float]:
    return (cal["E"][0] * x + cal["E"][1] * y + cal["E"][2], cal["N"][0] * x + cal["N"][1] * y + cal["N"][2])


def site_id(station: str) -> str:
    return f"RD-{station}"


def run() -> list[dict]:
    rd = json.loads((SDIR / "extraction" / "roving_dipole.json").read_text())
    pos: dict[str, list] = {}
    for page in rd["pages"].values():
        for q in page["points"]:
            if q.get("outlier"):
                continue
            pos.setdefault(q["station"], []).append(to_grid(page["calib"], q["x"], q["y"]))
    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    sites = [s for s in survey.get("sites", []) if not s["id"].startswith("RD-")]
    for st in sorted(pos, key=lambda s: (len(s), s)):
        e, n = np.median(np.array(pos[st]), 0)
        sites.append({"id": site_id(st), "name": f"Roving-dipole station {st}",
                      "coords": {"x": round(e * 1000), "y": round(n * 1000), "crs": "EPSG:28193", "source": "map",
                                 "accuracy_m": 100},
                      "notes": f"Median position over {len(pos[st])} map(s) at 1:50,000."})
    today = date.today().isoformat()
    ds = []
    for p, page in sorted(rd["pages"].items(), key=lambda kv: int(kv[0])):
        good = [q for q in page["points"] if not q.get("outlier")]
        pts = [{"station": float(q["station"]), "rho_a": float(q["value"]), "site": site_id(q["station"])}
               for q in good if q.get("value") is not None]
        if not pts:
            continue
        dip = [to_grid(page["calib"], x, y) for x, y in page.get("dipole_px", [])]
        unsure = sum(not q.get("sure", True) for q in good)
        ds.append({
            "id": f"{SURVEY}-roving-source-{page['source']}", "survey": SURVEY, "site": None, "line": f"Source {page['source']}",
            "method": "DIPOLE", "level": "L1", "representation": "map_grid", "array": "roving dipole",
            "measured_on": None, "confidence": "B" if unsure <= 3 else "C", "status": "draft", "profile": pts,
            "source_dipole": [{"x": round(e * 1000), "y": round(n * 1000), "crs": "EPSG:28193", "source": "map",
                               "accuracy_m": 100} for e, n in dip] or None,
            "provenance": {"document": "maps", "pages": [int(p)], "figure": f"Figure {page.get('figure') or p}, source {page['source']}",
                           "method": "manual", "tool": "geosigma.extract.yizreel_maps (positions by script, values by eye)",
                           "extracted_on": today},
            "notes": f"Apparent resistivity at {len(pts)} receiver stations for transmitter {page['source']}."
                     + (f" {unsure} readings were hard to read." if unsure else ""),
        })
    survey["sites"] = sites
    maps = next(d for d in survey["documents"] if d["id"] == "maps")
    maps.update(sha256="f801daad3e579ff8869044f9abe697638f9fbfb756b4194ea3fa1a0ff17079a0", pages=43)
    survey["extraction_status"] = "partial"
    survey["notes"] = (f"Roving-dipole apparent-resistivity maps (Maps PDF, Figures 3-36, {len(ds)} transmitters) "
                       "transcribed by eye, station positions by script. Not yet extracted: the pseudosections and "
                       "composite maps (Maps pages 37-42) and the main report (not supplied; over the connector limit).")
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "roving_dipole.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    ds = run()
    print(len(ds), "maps,", len({p["site"] for d in ds for p in d["profile"]}), "stations")
