"""Klang (1970), MT soundings 24-29 in the Timna and Ramon areas (MT/665/69).

Each of the six field sheets (PDF pages 8-13) has a band under the plot, "CALC. RES.",
that prints the interpreted layered model: one resistivity per complex and the depth
of each boundary. These are typed from the sheets, along with the sheet's
coordinates (Old Israel Grid) and elevation. The sheets give resistivity in ohm.cm
(axis and band are both labelled that way), so all values are divided by 100.

The apparent-resistivity curve on each sheet is traced by script. The x axis is
sqrt(T) in s^1/2 from 10^-2 to 10^3, and the y axis spans three decades on log paper.
The grid is located by fitting a log-paper comb to the thin lines. The bottom decade
of each sheet is hand-labelled and hard to read, so it is set to whichever value
puts the start of the curve near the first-layer resistivity (100 or 1000 ohm.cm).

Run: ``python -m geosigma.extract.klang_timna`` (needs the PDF in data/sources/pdf).
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np

from ..store import SURVEYS_DIR

SURVEY = "klang-1970-mt-timna-ramon"
SDIR = SURVEYS_DIR / SURVEY
PDF = (SURVEYS_DIR.parent / "sources" / "pdf"
       / "Klang-A-Timna-Ramon-Area-Magneto-Telluric-Measurements-IPRG-MT-665-69-1970.pdf")
DPI = 120

# page, sounding, x, y (Old Israel Grid m), elevation, rho (ohm.cm, None = "very high"),
# boundary depths (m), bottom decade of the plot (ohm.cm), notes.
SHEETS = [
    (8, "24", 145850, 904850, 200, [3000, 18000, 5600, 10500, None], [195, 3300, 9900, 30000],
     1000, "Deepest boundary printed as '30000 ?'; the last complex is 'very high'."),
    (9, "25", 146094, 904973, 180, [3500, 18000, 4000, 16500, None], [300, 2200, 5500, 38500],
     1000, "Deepest boundary printed as '38500 ?'; the last complex is 'very high'."),
    (10, "26", 147150, 904100, 200, [1100, 8800], [200],
     100, "Report: low-frequency data insufficient, so the model stays in the sedimentary section."),
    (11, "27", 148950, 909150, 200, [8500, 25500, 5000, 55000], [460, 2760, 13800],
     1000, "Report: basement known at about 50-80 m here; the first complex mixes sediments and basement."),
    (12, "28", 148950, 909450, 205, [10000, 20000, 3400, 67500], [480, 2880, 10000],
     1000, "Report: basement known at about 50-80 m here; the first complex mixes sediments and basement."),
    (13, "29", 138650, 1150, 500, [1100, 7700, 70000], [500, 15500],
     100, "Near the Ramon 1 well (TD 3439 m in arkose). Report: no basement can be told apart under the arkose."),
]
LOCATION = {"29": "Ramon"}
# Grid of each sheet at 120 dpi: x of 10^-2 s^1/2, px per decade (x), y of the bottom
# decade, px per decade (y). Found with fit_grid() and checked on the page.
GRID = {8: (101.5, 353.0, 1141.5, 354.5), 9: (96.0, 353.5, 1138.5, 354.0), 10: (91.0, 353.0, 1139.0, 354.0),
        11: (102.5, 353.0, 1140.0, 354.0), 12: (104.0, 353.0, 1142.0, 353.5), 13: (99.0, 353.5, 1142.0, 354.5)}


def _render(page: int) -> np.ndarray:
    import pymupdf as fitz

    doc = fitz.open(PDF)
    pix = doc[page - 1].get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)


def fit_grid(img: np.ndarray, ndec: int, axis: int, s_rng=(340, 365), o_rng=None):
    """Fit log-paper lines (1..9 per decade) to the thin-line profile along one axis."""
    from scipy import ndimage as ndi

    a = img < 150
    thin = a & ~ndi.binary_dilation(ndi.binary_opening(a, np.ones((5, 5))), iterations=3)
    prof = ndi.uniform_filter1d(thin.sum(axis).astype(float), 3)
    prof /= prof.max()
    marks = np.log10([m * 10 ** k for k in range(ndec) for m in range(1, 10)] + [10 ** ndec])
    w = np.where(np.isclose(marks % 1, 0), 3.0, 1.0)
    best = (-1.0, 0.0, 0.0)
    for s in np.arange(*s_rng, 0.5):
        for o in np.arange(*o_rng, 0.5):
            idx = np.round(o + marks * s).astype(int)
            if idx.max() < len(prof):
                sc = float((w * prof[idx]).sum())
                if sc > best[0]:
                    best = (sc, s, o)
    return best[1], best[2]


def trace_curve(img: np.ndarray, grid: tuple) -> list[tuple[float, float]]:
    """(log10 sqrt T, decades above the bottom line) every 0.1 along the thick curve."""
    from scipy import ndimage as ndi

    x0, sx, yb, sy = grid
    a = img < 150
    a[int(yb) + 3:] = 0
    a[:60] = 0
    a[:, :int(x0) + 3] = 0
    a[:, int(x0 + 5 * sx) - 3:] = 0
    th = ndi.binary_opening(a, np.ones((5, 5)))
    lab, _ = ndi.label(th)
    keep = np.zeros_like(th)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if (lab[sl] == i).sum() >= 60 and not hh > 6 * ww and not (ww > 12 * hh and hh < 9):
            keep[sl] |= lab[sl] == i
    # The curve is one chain of dashes; keep the biggest chain.
    dl, nd = ndi.label(ndi.binary_dilation(keep, iterations=20))
    keep &= dl == (np.argmax(ndi.sum(keep, dl, range(1, nd + 1))) + 1)
    cols = np.where(keep.any(0))[0]
    lx = (cols - x0) / sx - 2
    ly = np.array([(yb - np.where(keep[:, c])[0].mean()) / sy for c in cols])
    xs = np.arange(np.ceil(lx.min() * 10) / 10, lx.max() + 1e-9, 0.1)
    return [(round(float(v), 2), float(np.interp(v, lx, ly))) for v in xs]


def site_id(no: str) -> str:
    return f"MTP-{no}"


def datasets(curves: dict | None = None) -> list[dict]:
    today = date.today().isoformat()
    out = []
    for page, no, _x, _y, _z, rho, depths, bottom, note in SHEETS:
        tops = [0.0] + [float(d) for d in depths]
        layers = []
        for i, r in enumerate(rho):
            lay = {"top_m": tops[i], "bottom_m": tops[i + 1] if i + 1 < len(tops) else None}
            if r is None:
                prev = rho[i - 1] / 100
                lay.update(rho_min=prev, note="printed as 'very high'")
            else:
                lay["rho_ohmm"] = r / 100
            layers.append(lay)
        unsure = "?" in note or no == "26"
        out.append({
            "id": f"klang1970-timna-{no}-layered", "survey": SURVEY, "site": site_id(no), "method": "MT",
            "level": "L2", "representation": "model_1d", "measured_on": "1969-08", "model_type": "layered",
            "depth_max_m": float(depths[-1]), "confidence": "C" if unsure else "B", "status": "draft",
            "layers": layers,
            "provenance": {"document": "main", "pages": [page], "figure": f"M.T.P. No. {no} field sheet",
                           "table": "CALC. RES. band", "method": "manual", "tool": "geosigma.extract.klang_timna",
                           "extracted_on": today,
                           "notes": "Printed in ohm.cm; divided by 100. Depths below ground."},
            "notes": note,
        })
        if curves and no in curves:
            pts = [{"x": round((10 ** lx) ** 2, 5), "rho_a": float(f"{bottom * 10 ** ly / 100:.3g}")}
                   for lx, ly in curves[no]]
            out.append({
                "id": f"klang1970-timna-{no}-curve", "survey": SURVEY, "site": site_id(no), "method": "MT",
                "level": "L1", "representation": "sounding_curve", "measured_on": "1969-08",
                "x_quantity": "period", "curve": pts, "confidence": "B", "status": "draft",
                "digitisation_error": "+-0.02 log10 rho_a, +-0.02 log10 sqrt(T) (traced line on log paper)",
                "provenance": {"document": "main", "pages": [page], "figure": f"M.T.P. No. {no} field sheet",
                               "method": "digitised_auto", "tool": "geosigma.extract.klang_timna",
                               "extracted_on": today,
                               "notes": "Smoothed field curve as drawn; period T = (sqrt T)^2. "
                                        f"Bottom decade taken as {bottom} ohm.cm."},
            })
    return out


def run():
    import yaml

    curves = {}
    if PDF.exists():
        for page, no, *_ in SHEETS:
            curves[no] = trace_curve(_render(page), GRID[page])
        (SDIR / "extraction").mkdir(exist_ok=True)
        (SDIR / "extraction" / "curve_traces.json").write_text(json.dumps(curves, indent=1))
    elif (SDIR / "extraction" / "curve_traces.json").exists():
        curves = json.loads((SDIR / "extraction" / "curve_traces.json").read_text())
    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    survey["sites"] = [{
        "id": site_id(no), "name": f"MT sounding {no} ({LOCATION.get(no, 'Timna')})",
        "coords": {"x": x, "y": y, "crs": "EPSG:28193", "source": "table", "accuracy_m": 50},
        "elevation_m": float(z)} for _p, no, x, y, z, *_ in SHEETS]
    survey["extraction_status"] = "complete"
    survey["notes"] = ("6 soundings, August 1969. Models typed from the CALC. RES. band of each sheet "
                       "(ohm.cm on the sheet, stored in ohm.m); apparent-resistivity curves traced by script. "
                       "The report says one more sounding could not be interpreted.")
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    ds = datasets(curves)
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "models_and_curves.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    for d in run():
        print(d["id"], d.get("layers") and [(l["top_m"], l.get("rho_ohmm")) for l in d["layers"]]
              or (d["curve"][0], d["curve"][-1]))
