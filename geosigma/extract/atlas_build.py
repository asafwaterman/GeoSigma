"""Build the 1982 Geoelectric Atlas records: Wenner profiles repeated in time.

``python -m geosigma.extract.atlas_build`` digitises every plot page listed in
PAGES with ``atlas_profiles``, assigns overlaid lines to their survey dates and
writes the stations as sites (placed along each line as drawn on the location
maps) and one L1 profile per line, spacing and date.

Assumptions, stated in each record: readings are 50 m apart (the a1 spacing) and
reading 0 is the western (coastal) end of the line; the reports describe the
profiles from west to east and the low, saline readings sit at the low numbers.
"""
from __future__ import annotations

import json
import math
from datetime import date

import pymupdf
import yaml

from ..store import ROOT, SURVEYS_DIR
from .atlas_profiles import link_joint, read_panels, render, style_masks

SURVEY = "paparo-1982-geoelectric-atlas"
PDF = ROOT / "data" / "sources" / "pdf" / (
    "Paparo-H-Geoelectric-Atlas-Israel-Determining-Geoelectric-Measurements-IPRG Rep-VO-875-80-1982.pdf")
STEP_M = 50.0

# Line ends (west, east) in Old Israel Grid km, read from the location maps
# (PDF pages 12, 19 and 28; map frames labelled every 1 or 2 km, 1:50,000).
LINES = {
    ("Ashkelon", 1): ((106.53, 118.81), (107.54, 118.50)),
    ("Ashkelon", 2): ((107.19, 119.80), (108.18, 119.29)),
    ("Ashkelon", 3): ((107.63, 120.34), (109.07, 120.29)),
    ("Ashkelon", 4): ((108.34, 121.49), (109.41, 121.49)),
    ("Ashkelon", 5): ((109.23, 122.88), (110.11, 122.51)),
    ("Givat Olga", 1): ((138.00, 202.27), (139.21, 202.00)),
    ("Givat Olga", 2): ((138.30, 203.43), (139.46, 203.22)),
    ("Givat Olga", 3): ((138.56, 204.58), (139.68, 204.19)),
    ("Givat Olga", 4): ((138.67, 205.08), (139.63, 205.24)),
    ("Givat Olga", 5): ((138.77, 205.68), (140.07, 205.68)),
    ("Givat Olga", 6): ((138.75, 206.03), (140.62, 205.87)),
    ("Givat Olga", 7): ((138.91, 206.63), (140.13, 206.43)),
    ("Rishpon-Yakum", 1): ((132.43, 178.42), (133.11, 178.27)),
    ("Rishpon-Yakum", 2): ((132.34, 179.27), (133.19, 178.89)),
    ("Rishpon-Yakum", 3): ((132.48, 179.66), (133.24, 179.42)),
    ("Rishpon-Yakum", 4): ((132.58, 180.06), (133.77, 179.74)),
    ("Rishpon-Yakum", 5): ((132.77, 180.51), (133.89, 180.19)),
    ("Rishpon-Yakum", 6): ((132.89, 181.24), (134.21, 180.96)),
    ("Rishpon-Yakum", 7): ((133.05, 181.55), (134.21, 181.26)),
    ("Rishpon-Yakum", 8): ((133.32, 182.29), (134.35, 181.94)),
    ("Rishpon-Yakum", 9): ((133.60, 183.38), (134.48, 182.95)),
    ("Rishpon-Yakum", 10): ((133.72, 183.74), (134.54, 183.58)),
    ("Rishpon-Yakum", 11): ((133.79, 184.13), (134.58, 183.98)),
    ("Rishpon-Yakum", 12): ((133.95, 184.81), (134.68, 184.58)),
}
MAP_PAGE = {"Ashkelon": 12, "Givat Olga": 19, "Rishpon-Yakum": 28}

ASH = {"spacings": [50, 150], "styles": ("dashed", "thin", "thick")}
GO = {"spacings": [50, 150], "styles": ("thin", "dashed")}
SHE = {"spacings": [50, 100, 150], "styles": ("thin",)}
# page: (region, line, layout, dates in the order of layout styles)
PAGES = {
    13: ("Ashkelon", 1, ASH, ["1980-06-30", "1981-04-30", "1981-12-23"]),
    14: ("Ashkelon", 2, ASH, ["1980-06-29", "1981-04-29", "1981-12-22"]),
    15: ("Ashkelon", 3, ASH, ["1980-06-22", "1981-04-28", "1981-12-21"]),
    16: ("Ashkelon", 4, ASH, ["1980-06-23", "1981-04-27", "1981-12-20"]),
    17: ("Ashkelon", 5, ASH, ["1980-06-21", "1981-05-03", "1981-12-20"]),
    20: ("Givat Olga", 1, GO, ["1980-06-19", "1981-12-08"]),
    21: ("Givat Olga", 2, GO, ["1980-06-11", "1981-12-09"]),
    22: ("Givat Olga", 3, GO, ["1980-06-10", "1981-12-10"]),
    23: ("Givat Olga", 4, GO, ["1980-06-18", "1981-12-16"]),
    24: ("Givat Olga", 5, GO, ["1980-06-09", "1981-12-13"]),
    25: ("Givat Olga", 6, GO, ["1980-06-08", "1981-12-14"]),
    26: ("Givat Olga", 7, GO, ["1980-06-17", "1981-12-15"]),
    33: ("Rishpon-Yakum", 1, SHE, ["1982-01-10"]),
    34: ("Rishpon-Yakum", 2, SHE, ["1982-01-07"]),
    35: ("Rishpon-Yakum", 3, SHE, ["1982-01-03"]),
    36: ("Rishpon-Yakum", 4, SHE, ["1982-01-11"]),
    37: ("Rishpon-Yakum", 5, SHE, ["1981-12-31"]),
    38: ("Rishpon-Yakum", 6, SHE, ["1981-12-27"]),
    39: ("Rishpon-Yakum", 7, SHE, ["1981-12-29"]),
    40: ("Rishpon-Yakum", 8, SHE, ["1981-12-28"]),
    41: ("Rishpon-Yakum", 9, SHE, ["1981-12-30"]),
    42: ("Rishpon-Yakum", 10, SHE, ["1981-12-30"]),
    43: ("Rishpon-Yakum", 11, SHE, ["1982-01-11"]),
    44: ("Rishpon-Yakum", 12, SHE, ["1982-01-12"]),
}
STYLE_WORD = {"dashed": "dashed", "thin": "thin solid", "thick": "thick solid"}


def slug(region: str) -> str:
    return region.lower().replace(" ", "-")


def station_xy(region: str, line: int, station: float) -> tuple[float, float]:
    (e0, n0), (e1, n1) = LINES[(region, line)]
    L = math.hypot(e1 - e0, n1 - n0) * 1000
    t = station * STEP_M / L
    return round((e0 + t * (e1 - e0)) * 1000), round((n0 + t * (n1 - n0)) * 1000)


def digitise(pn: int, layout: dict) -> list[dict]:
    """[{spacing, style, points:[(station, rho)]}] for one page."""
    page = PDF_DOC[pn - 1]
    panels = read_panels(page)
    if len(panels) != len(layout["spacings"]):
        raise ValueError(f"page {pn}: {len(panels)} panels, expected {len(layout['spacings'])}")
    dk = render(page) < 140
    out = []
    for p, a in zip(panels, layout["spacings"]):
        if len(layout["styles"]) == 1:
            seen = {}
            for x, y in p.dots:
                seen.setdefault(p.grid_station(x), (x, y))
            series = {layout["styles"][0]: [(s, x, y) for s, (x, y) in sorted(seen.items())]}
        else:
            series = link_joint(p, style_masks(dk, p.dots), layout["styles"])
        for style, chain in series.items():
            out.append({"spacing": a, "style": style, "panel_axis_y": p.axis_y,
                        "points": [(s, float(f"{p.rho(y):.3g}")) for s, x, y in chain],
                        "pixels": [(round(x, 1), round(y, 1)) for s, x, y in chain],
                        "calibration": {"axis_x": p.axis_x, "px_per_station": p.px_per_station,
                                        "log10_rho": p.y_fit, "labels": [(round(y, 1), v) for y, v in p.y_ticks]}})
    return out


def run():
    global PDF_DOC
    PDF_DOC = pymupdf.open(PDF)
    sdir = SURVEYS_DIR / SURVEY
    sv = yaml.safe_load((sdir / "survey.yaml").read_text())
    sites, ds, raw = {}, [], {}
    for pn, (region, line, layout, dates) in PAGES.items():
        series = digitise(pn, layout)
        raw[pn] = series
        multi = len(layout["styles"]) > 1
        for sr in series:
            when = dates[layout["styles"].index(sr["style"])]
            lname = f"{region} line {line}"
            pts = []
            for st, rho in sr["points"]:
                sid = f"{slug(region)}-{line}-{st:g}"
                if sid not in sites:
                    x, y = station_xy(region, line, st)
                    sites[sid] = {"id": sid, "name": f"{lname}, reading {st:g}", "line": lname,
                                  "coords": {"x": x, "y": y, "crs": "EPSG:28193", "source": "map", "accuracy_m": 150}}
                pts.append({"station": st, "rho_a": rho, "site": sid})
            ds.append({
                "id": f"{SURVEY}-{slug(region)}-{line}-a{sr['spacing']}-{when}",
                "survey": SURVEY, "line": lname, "method": "PROFILING", "level": "L1",
                "representation": "profile", "measured_on": when, "array": "Wenner",
                "spacing_m": sr["spacing"], "confidence": "C" if multi else "B", "status": "draft",
                "profile": pts,
                "digitisation_error": "+-0.02 log10 rho_a; station positions +-150 m",
                "provenance": {
                    "document": "main", "pages": [pn, MAP_PAGE[region]],
                    "figure": f"Continuous geoelectric section {line}, {region}, a = {sr['spacing']} m"
                              + (f", {STYLE_WORD[sr['style']]} curve" if multi else ""),
                    "method": "digitised_auto", "tool": "geosigma.extract.atlas_profiles",
                    "extracted_on": date.today().isoformat(),
                    "notes": "Dots found on the plot and calibrated on the printed axis labels."
                             + (" Overlaid survey dates were separated by line style automatically;"
                                " where lines cross, readings can be assigned to the wrong date." if multi else ""),
                },
                "notes": f"Readings assumed {STEP_M:g} m apart from the western (coastal) end of the line.",
            })
    sv["methods"] = ["PROFILING"]
    sv["sites"] = list(sites.values())
    sv["extraction_status"] = "partial"
    sv["notes"] = ("Plot pages 13-17 (Ashkelon, 3 dates), 20-26 (Givat Olga, 2 dates) and 33-44 (Rishpon-Yakum, "
                   "1 date) digitised. Page 46 (Caesarea, a = 25/50/75 m) is not located on any map in the report "
                   "and is not extracted. Pages 29-32 hold maps not yet extracted.")
    (sdir / "survey.yaml").write_text(yaml.safe_dump(sv, sort_keys=False, allow_unicode=True, width=110))
    (sdir / "datasets").mkdir(exist_ok=True)
    (sdir / "datasets" / "profiles.json").write_text(json.dumps(ds, indent=1))
    (sdir / "extraction").mkdir(exist_ok=True)
    (sdir / "extraction" / "plot_readings.json").write_text(json.dumps(raw, indent=1))
    return ds


if __name__ == "__main__":
    out = run()
    print(len(out), "profiles,", sum(len(d["profile"]) for d in out), "readings")
