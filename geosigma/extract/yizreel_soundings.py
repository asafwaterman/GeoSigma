"""Modified Schlumberger and monopole soundings, Yizreel-Harod 1977 (main report appendix).

PDF pages 48-81 are 34 field sheets with plotted apparent-resistivity points ("x" for
modified Schlumberger, dots for monopole) against distance, usually with no model; the
report says these soundings could in general not be interpreted. Points were read by
eye from 260 dpi crops (x to the nearest grid line, rho_a to 2 significant figures) into
``extraction/soundings.json``.

Footers print one or two coordinate pairs (Old Israel Grid m). With two pairs, the first
is shared by the two soundings of each source (the report: "two for each source"), so it
is taken as the source and the second as the sounding point, where the site is put. Each array on a sheet becomes its own L1 sounding curve.

Run: ``python -m geosigma.extract.yizreel_soundings``.
"""
from __future__ import annotations

import json
import re
from datetime import date

import yaml

from ..store import SURVEYS_DIR

SURVEY = "rotstein-1977-yizreel-harod"
SDIR = SURVEYS_DIR / SURVEY


def pair(s: str) -> tuple[float, float] | None:
    nums = [int(n) for n in re.findall(r"\d{5,6}", s or "")]
    return (nums[0], nums[1]) if len(nums) >= 2 else None


def run() -> list[dict]:
    sheets = json.loads((SDIR / "extraction" / "soundings.json").read_text())
    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    sites = [s for s in survey.get("sites", []) if not s["id"].startswith("DS-")]
    today, ds = date.today().isoformat(), []
    for sh in sorted(sheets, key=lambda s: s["page"]):
        pts = [p for p in (pair(c) for c in sh.get("coords", [])) if p]
        if not pts:
            print("no coordinates, skipped: page", sh["page"])
            continue
        x, y = pts[-1]
        sid = f"DS-{sh['dp']}"
        if any(s["id"] == sid for s in sites):
            sid = f"{sid}-p{sh['page']}"
        sites.append({"id": sid, "name": f"Depth sounding D.P. {sh['dp']}",
                      "coords": {"x": round(x), "y": round(y), "crs": "EPSG:28193", "source": "table",
                                 "accuracy_m": 100},
                      "notes": ("Second coordinate pair on the sheet; the first (shared with the other sounding "
                                "of the same source) is taken as the source: " if len(pts) > 1 else "As printed: ")
                               + "; ".join(sh.get("coords", []))})
        for key, array in (("schlumberger", "modified Schlumberger"), ("monopole", "monopole")):
            curve = [{"x": float(a), "rho_a": float(b)} for a, b in sh.get(key) or [] if a and b]
            if len(curve) < 3:
                continue
            ds.append({
                "id": f"{SURVEY}-ds-{sh['dp']}-{key}" + ("" if sid == f"DS-{sh['dp']}" else f"-p{sh['page']}"),
                "survey": SURVEY, "site": sid, "method": "VES", "level": "L1", "representation": "sounding_curve",
                "array": array, "x_quantity": "distance OB (m)", "measured_on": None,
                "curve": sorted(curve, key=lambda c: c["x"]), "confidence": "C" if not sh.get("sure", True) else "B",
                "status": "draft", "digitisation_error": "rho_a +-5 % (read by eye on log paper)",
                "provenance": {"document": "main", "pages": [sh["page"]], "figure": f"D.P. {sh['dp']} sounding sheet",
                               "method": "digitised_manual", "tool": "geosigma.extract.yizreel_soundings (read by eye)",
                               "extracted_on": today},
                "notes": " ".join(filter(None, ["Report: these soundings could in general not be interpreted.",
                                                sh.get("note")])),
            })
        m = sh.get("model")
        if m and m.get("rho") and len(m.get("edges_m") or []) == len(m["rho"]) - 1:
            tops = [0.0] + [float(e) for e in m["edges_m"]]
            ds.append({
                "id": f"{SURVEY}-ds-{sh['dp']}-model" + ("" if sid == f"DS-{sh['dp']}" else f"-p{sh['page']}"),
                "survey": SURVEY, "site": sid, "method": "VES", "level": "L2", "representation": "model_1d",
                "model_type": "layered", "measured_on": None, "confidence": "C", "status": "draft",
                "depth_max_m": round(tops[-1] * 1.5),
                "layers": [{"top_m": tops[i], "bottom_m": tops[i + 1] if i + 1 < len(tops) else None,
                            "rho_ohmm": float(r)} for i, r in enumerate(m["rho"]) if r is not None],
                "digitisation_error": "interface +-15 % (box edge read on the distance axis)",
                "provenance": {"document": "main", "pages": [sh["page"]], "figure": f"D.P. {sh['dp']} sounding sheet",
                               "table": "CAL. RES. band", "method": "digitised_manual",
                               "tool": "geosigma.extract.yizreel_soundings (read by eye)", "extracted_on": today,
                               "notes": "Interface depth taken as the distance of the box edge, as on the other IPRG sheets."},
                "notes": "One of the few soundings the report says could be interpreted.",
            })
    survey["sites"] = sites
    main = next(d for d in survey["documents"] if d["id"] == "main")
    main.update(sha256="562f029aef8835ec6ad46e6427f879adc9b36bf532da63f941867b5f1f9ae1c4", pages=83)
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    (SDIR / "datasets" / "soundings.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    ds = run()
    print(len(ds), "curves")
