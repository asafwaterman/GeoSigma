"""Layered models printed as tables or computer printouts, typed from the page.

For reports whose author's models are short printed tables (MT interval tables,
TDEM inversion printouts), each value was read by eye from the page rendered at
200 dpi and typed into ``data/surveys/<id>/extraction/transcription.yaml``. This
script turns that file into the survey's sites and model datasets, after checking:

- layers are contiguous and start at the surface;
- a printed thickness equals bottom - top (``thick``), and a printed conductance
  equals thickness / resistivity (``cond``), where the table gives them;
- the unit is converted to ohm.m (ohm.cm values are divided by 100, and the
  provenance says so).

Transcription format (one file per survey)::

    document: main          # SourceDocument id
    unit: ohm.m             # or ohm.cm
    method: MT
    prefix: weissbrod1974   # dataset id prefix
    measured_on: "1970"
    confidence: A
    table: Table 1          # what the values were read from
    crs: EPSG:28193
    xy_scale: 10            # printed coordinates times this give metres
    sites:
      - id: "41"
        xy: [14575, 98505]
        elev: 365
        page: 12
        box: [0.55, 0.37, 0.89, 0.40]   # page fractions of the site's rows
        layers:                         # [top, bottom or null, rho, note]
          - [0, 270, 33, "MT unit B"]
          - [2400, null, 105, "MT unit E"]

A layer row may carry ``{thick: ..}`` or ``{cond: ..}`` as a fifth element.

Run: ``python -m geosigma.extract.printed_tables <survey-id> [...]``.
"""
from __future__ import annotations

import json
import sys
from datetime import date

import yaml

from ..store import SURVEYS_DIR

UNIT_FACTOR = {"ohm.m": 1.0, "ohm.cm": 0.01}


def _layers(site: dict, factor: float) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    for i, row in enumerate(site["layers"]):
        top, bottom, rho = row[0], row[1], row[2]
        note = row[3] if len(row) > 3 else None
        extra = row[4] if len(row) > 4 else {}
        if i == 0 and top != 0:
            problems.append(f"first layer starts at {top} m, not at the surface")
        if out and out[-1]["bottom_m"] != top:
            problems.append(f"layer {i + 1}: top {top} != previous bottom {out[-1]['bottom_m']}")
        if bottom is None and i != len(site["layers"]) - 1:
            problems.append(f"layer {i + 1}: open-ended layer is not the last")
        if bottom is not None and bottom <= top:
            problems.append(f"layer {i + 1}: bottom {bottom} <= top {top}")
        if "thick" in extra and bottom is not None and abs((bottom - top) - extra["thick"]) > 0.02 * extra["thick"] + 0.6:
            problems.append(f"layer {i + 1}: printed thickness {extra['thick']} != {bottom - top:g}")
        if "cond" in extra and bottom is not None and rho:
            c = (bottom - top) / rho
            if abs(c - extra["cond"]) > 0.06 * extra["cond"] + 0.02:
                problems.append(f"layer {i + 1}: printed conductance {extra['cond']} != thickness/rho {c:.3g}")
        lay = {"top_m": round(top, 2), "bottom_m": None if bottom is None else round(bottom, 2)}
        if rho is not None:
            lay["rho_ohmm"] = round(rho * factor, 6)
        if note:
            lay["note"] = note
        out.append(lay)
    if out and out[-1]["bottom_m"] is not None:
        problems.append("last layer is not a half-space")
    return out, problems


def build(survey: str) -> list[dict]:
    sdir = SURVEYS_DIR / survey
    tr = yaml.safe_load((sdir / "extraction" / "transcription.yaml").read_text())
    factor = UNIT_FACTOR[tr["unit"]]
    sv = yaml.safe_load((sdir / "survey.yaml").read_text())
    today = date.today().isoformat()
    sites, ds, problems, boxes = [], [], [], {}
    scale = tr.get("xy_scale", 1)
    for s in tr["sites"]:
        if "xy" in s:
            site = {"id": s["id"], "name": s.get("name") or f"{tr.get('site_word', 'Station')} {s['id']}",
                    "coords": {"x": s["xy"][0] * scale, "y": s["xy"][1] * scale, "crs": s.get("crs", tr["crs"]),
                               "source": s.get("coord_source", tr.get("coord_source", "table"))}}
            acc = s.get("accuracy_m", tr.get("accuracy_m"))
            if acc:
                site["coords"]["accuracy_m"] = acc
            if s.get("elev") is not None:
                site["elevation_m"] = s["elev"]
            if s.get("site_notes"):
                site["notes"] = s["site_notes"]
            sites.append(site)
        if not s.get("layers"):
            continue
        layers, probs = _layers(s, factor)
        problems += [f"{s['id']}: {p}" for p in probs]
        notes = [tr.get("prov_notes"), s.get("prov_notes")]
        if factor != 1:
            notes.insert(0, f"Printed in {tr['unit']}; values divided by 100 to give ohm.m.")
        prov = {"document": s.get("document", tr["document"]), "pages": s.get("pages") or [s["page"]],
                "method": tr.get("extraction_method", "manual"),
                "tool": "typed from the page at 200 dpi; geosigma.extract.printed_tables", "extracted_on": today,
                "notes": " ".join(n for n in notes if n) or None}
        if s.get("figure") or tr.get("figure"):
            prov["figure"] = s.get("figure") or tr.get("figure")
        table = s.get("table") or tr.get("table")
        if table:
            prov["table"] = table
        deepest = max((l["bottom_m"] or l["top_m"]) for l in layers)
        d = {"id": f"{tr['prefix']}-{s.get('model_id', s['id'])}-{s.get('model_type', tr.get('model_type', 'layered'))}",
             "survey": survey, "site": s.get("site", s["id"]), "method": s.get("method", tr["method"]),
             "level": "L2", "representation": "model_1d", "measured_on": s.get("measured_on", tr.get("measured_on")),
             "depth_max_m": s.get("depth_max_m", deepest), "confidence": s.get("confidence", tr.get("confidence", "A")),
             "status": "draft", "model_type": s.get("model_type", tr.get("model_type", "layered")),
             "layers": layers, "provenance": prov}
        for k in ("doi_m", "digitisation_error", "reinterprets"):
            if s.get(k) is not None or tr.get(k) is not None:
                d[k] = s.get(k, tr.get(k))
        n = " ".join(x for x in (tr.get("notes"), s.get("notes")) if x)
        if n:
            d["notes"] = n
        ds.append(d)
        if s.get("box"):
            boxes[d["id"]] = {"page": prov["pages"][0], "box": s["box"]}
    if problems:
        raise SystemExit(f"{survey}: transcription problems:\n  " + "\n  ".join(problems))
    sv["sites"] = sites
    (sdir / "survey.yaml").write_text(yaml.safe_dump(sv, sort_keys=False, allow_unicode=True, width=110))
    (sdir / "datasets").mkdir(exist_ok=True)
    (sdir / "datasets" / "models.json").write_text(json.dumps(ds, indent=1, ensure_ascii=False))
    (sdir / "extraction" / "table_boxes.json").write_text(json.dumps(boxes, indent=1))
    print(f"{survey}: {len(sites)} sites, {len(ds)} models")
    return ds


if __name__ == "__main__":
    for sid in sys.argv[1:]:
        build(sid)
