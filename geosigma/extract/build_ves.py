"""Turn reviewed VES sheet readings into sites and layered models for a survey.

``python -m geosigma.extract.build_ves <survey-id> <pdf filename> <document id>``
reads ``data/surveys/<id>/extraction/ves_readings.yaml``, detects the model-box edges
on each listed page and writes the survey's sites and ``datasets/ves_models.json``.
"""
from __future__ import annotations

import json
import sys
from datetime import date

import pymupdf
import yaml

from ..store import ROOT, SURVEYS_DIR
from .ves_sheet import read_sheet


def coord(v: float) -> float:
    return v * 10 if v < 100000 else v


def build(survey: str, pdf: str, doc_id: str) -> int:
    sdir = SURVEYS_DIR / survey
    readings = yaml.safe_load((sdir / "extraction" / "ves_readings.yaml").read_text())
    d = pymupdf.open(ROOT / "data" / "sources" / "pdf" / pdf)
    sv = yaml.safe_load((sdir / "survey.yaml").read_text())
    sites, ds, problems = {s["id"]: s for s in sv.get("sites", [])}, [], []
    for r in readings:
        page = d[r["page"] - 1]
        if r.get("rotate"):  # sheet scanned upside down or sideways
            page.set_rotation(r["rotate"])
        sh = read_sheet(page, r["page"], ocr=False)
        if r.get("x_one"):  # axis fit overridden where the grid is too faint (from the printed labels)
            sh.x_one, sh.dec_x = r["x_one"], r.get("dec_x", sh.dec_x)
        if r.get("edges_px"):  # box edges read by eye (200 dpi pixels) where detection fails
            edges = [round(float(sh.ab2(x)), 1) for x in r["edges_px"]]
        else:
            edges = sh.interfaces_m
        r["edges_ab2_m"] = edges
        if len(edges) != len(r["rho"]) - 1:
            problems.append(f"page {r['page']}: {len(r['rho'])} boxes read but {len(edges)} edges detected")
            continue
        sid = f"{r['job']}-{r['dp']}".replace("/", "-")
        sites[sid] = {"id": sid, "name": f"VES {r['dp']} (job {r['job']})", "elevation_m": r.get("elev"),
                      "coords": {"x": coord(r["x"]), "y": coord(r["y"]), "crs": "EPSG:28193", "source": "table"}}
        tops = [0.0] + edges
        layers = []
        for i, rho in enumerate(r["rho"]):
            bottom = edges[i] if i < len(edges) else None
            lay = {"top_m": tops[i], "bottom_m": bottom, "rho_ohmm": rho}
            if r.get("units"):
                lay["note"] = r["units"][i]
            if rho is None:
                lay["note"] = ((lay.get("note") or "") + " drawn as infinity (resistive basement)").strip()
            elif rho == 0:  # printed "0": below the sheet's resolution, brine-saturated ground
                lay.update(rho_ohmm=0.5, rho_max=1.0)
                lay["note"] = ((lay.get("note") or "") + " printed as 0 (below 1 ohm.m); 0.5 used as a nominal value").strip()
            layers.append(lay)
        conf = r.get("confidence", "B")
        ds.append({
            "id": f"{survey}-ves-{sid}", "survey": survey, "site": sid, "method": "VES", "level": "L2",
            "representation": "model_1d", "measured_on": r.get("measured_on"), "confidence": conf, "status": "draft", "model_type": "layered",
            "depth_max_m": round(max(edges) * 1.5) if edges else None, "layers": layers,
            "digitisation_error": "interfaces +-5% (box edges read on the AB/2 axis)",
            "provenance": {"document": doc_id, "pages": [r["page"]], "figure": f"VES sheet D.P. {r['dp']}, job {r['job']}",
                           "method": "digitised_manual", "tool": "geosigma.extract.ves_sheet (edges) + reading by eye",
                           "extracted_on": date.today().isoformat(),
                           "notes": "Interface depths taken as the AB/2 of the box edges under the curve."},
            "notes": " ".join(filter(None, [r.get("note"), "The last layer is open-ended; the model does not state a DOI."])),
        })
    sv["sites"] = list(sites.values())
    (sdir / "survey.yaml").write_text(yaml.safe_dump(sv, sort_keys=False, allow_unicode=True, width=110))
    (sdir / "datasets").mkdir(exist_ok=True)
    (sdir / "datasets" / "ves_models.json").write_text(json.dumps(ds, indent=1))
    (sdir / "extraction" / "ves_edges.json").write_text(
        json.dumps({r["page"]: r.get("edges_ab2_m") for r in readings}, indent=1))
    for p in problems:
        print("PROBLEM:", p)
    return len(ds)


if __name__ == "__main__":
    print(build(*sys.argv[1:4]), "models")
