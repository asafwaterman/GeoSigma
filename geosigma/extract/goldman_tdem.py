"""Goldman (2000) coastal-aquifer TDEM survey: parse the PROTEM inversion printouts.

Each station has a one-page printout (Geonics PROTEM, central loop) with the
layered model: resistivity, thickness, bottom elevation, conductance. Pages were
OCR'd with tesseract (``data/work/goldman/ocr.json``, rebuilt by
``scripts/goldman_ocr.py``). Rows are checked against conductance = thickness /
resistivity, which catches most OCR digit errors.

Besides the layered model, each station gets an interface_depth record: the depth
to the first layer below 3 ohm.m, the report's seawater criterion.
"""
from __future__ import annotations

import json
import re
from datetime import date

import yaml

from ..store import ROOT, SURVEYS_DIR

SURVEY = "goldman-2000-tdem-coastal"
SDIR = SURVEYS_DIR / SURVEY
OCR = ROOT / "data" / "work" / "goldman" / "ocr.json"
SEAWATER = 3.0

F = r"-?~?\d+(?:\.\d+)?"


def _num(s: str) -> float:
    return float(s.replace("~", ""))


def parse(page: int, text: str) -> dict | None:
    if "DATA SET" not in text:
        return None
    rec: dict = {"page": page, "problems": []}
    m = re.search(r"DATA SET:\s*(\S+)", text)
    rec["name"] = m.group(1).strip(".") if m else f"p{page}"
    m = re.search(r"LOCATION:\s*(.+?)\s+SOUNDING", text)
    rec["location"] = m.group(1).strip() if m else None
    m = re.search(r"COUNTY:\s*(\d{6})\s*/\s*(\d{6})", text)
    rec["xy"] = (int(m.group(1)), int(m.group(2))) if m else None
    m = re.search(r"DATE[;:]\s*(\d{1,2}-\w{3}-\d{2})", text)
    rec["date"] = m.group(1) if m else None
    m = re.search(r"ELEVATION:?\s*(" + F + r")\s*m", text)
    rec["elev"] = _num(m.group(1)) if m else None
    m = re.search(r"LOOP SIZE:\s*(\d+(?:\.\d+)?)\s*m by\s*(\d+(?:\.\d+)?)", text)
    rec["loop"] = f"{float(m.group(1)):g}x{float(m.group(2)):g} m" if m else None
    m = re.search(r"FITTING ERROR:\s*(\d+(?:\.\d+)?)\s*PERCENT", text)
    rec["fit_pct"] = float(m.group(1)) if m else None
    layers = []
    for line in text.splitlines():
        t = re.sub(r"[;:|\"'_“”~]", " ", line.replace(",", ".").replace("..", "."))
        t = re.sub(r"(\d) \.(\d)", r"\1.\2", t)
        t = " ".join(w for w in t.split() if w not in (".", "-")).lstrip("-. ")
        m = re.fullmatch(r"(\d)\s+(" + F + r")(?:\s+(" + F + r")\s+(" + F + r")\s+(" + F + r"))?", t)
        if m:
            n = int(m.group(1))
            if n != len(layers) + 1:
                continue
            rho = _num(m.group(2))
            if m.group(3):
                th, el, cond = (_num(m.group(i)) for i in (3, 4, 5))
                if th > 0 and rho > 0 and abs(th / rho - cond) > 0.06 * cond + 0.02:
                    rec["problems"].append(f"layer {n}: thickness/rho {th / rho:.3g} != conductance {cond}")
                layers.append({"rho": rho, "thick": th})
            else:
                layers.append({"rho": rho, "thick": None})
                break
    rec["layers"] = layers
    if not layers or layers[-1]["thick"] is not None:
        rec["problems"].append("layer table incomplete")
    return rec


def run() -> None:
    ocr = json.loads(OCR.read_text())
    recs = [r for p, t in sorted(ocr.items(), key=lambda kv: int(kv[0])) if (r := parse(int(p), t))]
    sv = yaml.safe_load((SDIR / "survey.yaml").read_text())
    sites, ds, bad = [], [], []
    today = date.today().isoformat()
    for r in recs:
        if r["xy"] is None or not r["layers"]:
            bad.append((r["page"], r["name"], "no coordinates or layers"))
            continue
        sites.append({"id": r["name"], "name": f"{r['name']} {r['location'] or ''}".strip(),
                      "elevation_m": r["elev"],
                      "coords": {"x": r["xy"][0], "y": r["xy"][1], "crs": "EPSG:28193", "source": "table"}})
        layers, top = [], 0.0
        for lay in r["layers"]:
            bottom = None if lay["thick"] is None else round(top + lay["thick"], 2)
            layers.append({"top_m": round(top, 2), "bottom_m": bottom, "rho_ohmm": lay["rho"]})
            top = bottom if bottom is not None else top
        when = None
        if r["date"]:
            from datetime import datetime
            try:
                when = datetime.strptime(r["date"].title(), "%d-%b-%y").date().isoformat()
            except ValueError:
                when = r["date"]
        conf = "A" if not r["problems"] else "B"
        prov = {"document": "main", "pages": [r["page"]], "table": f"PROTEM inversion printout {r['name']}",
                "method": "ocr", "tool": "tesseract 5 psm 6 + geosigma.extract.goldman_tdem", "extracted_on": today,
                "notes": "; ".join(r["problems"]) or None}
        common = {"survey": SURVEY, "site": r["name"], "method": "TEM", "level": "L2", "measured_on": when,
                  "confidence": conf, "status": "draft"}
        ds.append({**common, "id": f"goldman2000-{r['name']}-layered", "representation": "model_1d",
                   "model_type": "layered", "layers": layers, "depth_max_m": round(top * 1.5, 0) if top else None,
                   "provenance": prov,
                   "notes": f"Loop {r['loop']}; fitting error {r['fit_pct']}%. Last layer is the half-space."})
        sw = next((l for l in layers if l["rho_ohmm"] < SEAWATER), None)
        if sw:
            ds.append({**common, "id": f"goldman2000-{r['name']}-seawater", "representation": "interface_depth",
                       "interface_depth_m": sw["top_m"], "criterion": f"rho < {SEAWATER:g} ohm.m (seawater-saturated)",
                       "provenance": {**prov, "method": "manual", "tool": "derived from the layered model"},
                       "level": "L3", "reinterprets": f"goldman2000-{r['name']}-layered"})
    sv["sites"] = sites
    sv["extraction_status"] = "partial"
    (SDIR / "survey.yaml").write_text(yaml.safe_dump(sv, sort_keys=False, allow_unicode=True, width=110))
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "protem_models.json").write_text(json.dumps(ds, indent=1))
    print(len(sites), "stations;", sum(d["representation"] == "interface_depth" for d in ds), "seawater depths")
    for r in recs:
        if r["problems"]:
            print("CHECK", r["page"], r["name"], r["problems"])
    for b in bad:
        print("SKIPPED", b)


if __name__ == "__main__":
    run()
