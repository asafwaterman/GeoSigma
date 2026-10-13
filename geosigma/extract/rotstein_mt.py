"""Layered MT models of Rotstein and Goldberg (1979), northern Israel.

The report has no tables. Each sounding in Figures 2 and 3 carries a small inset
with the inverted layered model (TE data): log resistivity across, log depth (km)
down. Readings below are pixel positions in 500 dpi crops of those insets: the
labelled ticks of both axes and the step edges of the hatched model (found by a
row-by-row trace and checked by eye). Site positions were read from Figure 1, whose
frame is labelled in Old Israel Grid km (150/200 E, 250/300 N).

Run: ``python -m geosigma.extract.rotstein_mt``.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np

from ..store import SURVEYS_DIR

SURVEY = "rotstein-1979-mt-northern-israel"
SDIR = SURVEYS_DIR / SURVEY

# Figure 1 at 110 dpi: grid label positions -> Old Israel Grid km.
FIG1 = {"x150": 178.0, "px_per_km_x": 10.64, "y300": 103.0, "px_per_km_y": 10.54}
SITES_PX = {  # dot centres on Figure 1 (110 dpi render of PDF page 6)
    "KFM": (444.2, 695.3), "BTN": (554.1, 656.8), "BCH": (562.1, 538.8), "RAL": (790.0, 369.9),
    "MRG": (948.0, 276.8), "KAR": (885.8, 314.9), "JOU": (999.5, 539.6), "DAZ": (883.4, 609.3),
}
NOISY_PX = [(644.1, 426.2), (659.0, 584.0), (808.7, 576.4)]
REGION = {"KFM": "Upper Galil", "BTN": "Upper Galil", "BCH": "Upper Galil", "RAL": "Hula Valley",
          "MRG": "Golan Heights", "KAR": "Golan Heights", "JOU": "Golan Heights", "DAZ": "Golan Heights"}

# Per inset: rho ticks {x_px: ohm.m}, depth ticks {y_px: km}, layers as
# (top_y or None for the surface, bottom_y or None for open, edge_x).
INSETS = {
    "KFM": {"page": 10, "fig": 2, "rho": {246.5: 1, 310: 10, 370.5: 100}, "z": {135: .1, 278: 1, 418: 10, 555: 100},
            "layers": [(None, 230.0, 329), (230.0, 300.5, 272), (300.5, 443.5, 341), (443.5, None, 281)], "end": 520},
    "BTN": {"page": 10, "fig": 2, "rho": {203: 10, 267.5: 100}, "z": {33: .1, 176: 1, 318.5: 10, 457: 100},
            "layers": [(None, 124.5, 169), (124.5, 201.0, 203), (201.0, 251.0, 141), (251.0, None, 190)], "end": 296},
    "BCH": {"page": 10, "fig": 2, "rho": {137: 10, 197: 100}, "z": {57: .1, 194.5: 1, 333: 10, 447.5: 100},
            "layers": [(None, 178.0, 189), (178.0, 275.5, 139), (275.5, 382.0, 189), (382.0, None, 134)], "end": 427},
    "RAL": {"page": 10, "fig": 2, "rho": {134: 1, 197: 10, 259.5: 100}, "z": {77: .1, 217: 1, 356: 10, 496.5: 100},
            "layers": [(None, 111.5, 165), (111.5, 148.5, 236), (148.5, 177.0, 171), (177.0, 244.5, 228),
                       (244.5, 323.5, 177), (323.5, 370.5, 242), (370.5, None, 143)], "end": 467},
    "MRG": {"page": 11, "fig": 3, "rho": {91.5: 100, 153.5: 1000}, "z": {38.5: .1, 178.5: 1, 317.5: 10, 457: 100},
            "layers": [(None, 175.5, 85), (175.5, 223.5, 117), (223.5, 252.5, 75), (252.5, 339.0, 138),
                       (339.0, None, 73)], "end": 447.5},
    "DAZ": {"page": 11, "fig": 3, "rho": {153: 10, 216: 100}, "z": {80.5: .1, 218: 1, 359.5: 10},
            "layers": [(None, 149.5, 183), (149.5, 233.5, 200), (233.5, 245.5, 140), (245.5, 362.0, 201),
                       (362.0, None, 172)], "end": 449},
    "KAR": {"page": 11, "fig": 3, "rho": {150: 10, 213.5: 100, 271.5: 1000}, "z": {108: .1, 248: 1, 389.5: 10, 525.5: 100},
            "layers": [(None, 225.5, 203), (225.5, 263.0, 272), (263.0, 341.5, 198), (341.5, 441.5, 210),
                       (441.5, None, 173)], "end": 502},
    "JOU": {"page": 11, "fig": 3, "rho": {139.5: 10, 202: 100, 263: 1000}, "z": {86.5: .1, 228: 1, 366.5: 10, 505.5: 100},
            "layers": [(None, 172.5, 175), (172.5, 257.0, 199), (257.0, 312.5, 163), (312.5, 386.5, 208),
                       (386.5, None, 142)], "end": 466},
}
# Table 2 of the report: depth to the top of the crustal conductor (km).
TABLE2_KM = {"RAL": 13, "KAR": 23, "BCH": 22, "MRG": 14, "JOU": 13, "DAZ": 12, "KFM": 16}


def _interp_log(p: float, ticks: dict) -> float:
    """Pixel -> value on a log axis, piecewise linear between labelled ticks."""
    px = np.array(sorted(ticks))
    lv = np.log10([ticks[k] for k in px])
    if p <= px[0]:
        i = 0
    elif p >= px[-1]:
        i = len(px) - 2
    else:
        i = int(np.searchsorted(px, p)) - 1
    t = (p - px[i]) / (px[i + 1] - px[i])
    return float(10 ** (lv[i] + t * (lv[i + 1] - lv[i])))


def site_coords(px: tuple[float, float]) -> tuple[float, float]:
    x, y = px
    e = 150 + (x - FIG1["x150"]) / FIG1["px_per_km_x"]
    n = 300 - (y - FIG1["y300"]) / FIG1["px_per_km_y"]
    return round(e * 1000), round(n * 1000)


def models() -> list[dict]:
    out = []
    for name, c in INSETS.items():
        layers = []
        for top_y, bot_y, x in c["layers"]:
            top = 0.0 if top_y is None else _interp_log(top_y, c["z"]) * 1000
            bot = None if bot_y is None else _interp_log(bot_y, c["z"]) * 1000
            layers.append({"top_m": round(top, -1), "bottom_m": None if bot is None else round(bot, -1),
                           "rho_ohmm": float(f"{_interp_log(x, c['rho']):.2g}")})
        deepest = _interp_log(c["end"], c["z"]) * 1000
        noisy = name in ("BCH", "DAZ", "MRG", "KFM", "BTN")
        out.append({
            "id": f"rotstein1979-mt-{name}-te-layered",
            "survey": SURVEY, "site": name, "method": "MT", "level": "L2", "representation": "model_1d",
            "measured_on": "1977", "depth_max_m": round(deepest, -2),
            "confidence": "C" if noisy else "B", "status": "draft", "model_type": "layered",
            "layers": layers,
            "digitisation_error": "+-0.05 log10 rho, +-0.03 log10 depth (inset drawing and scan)",
            "provenance": {
                "document": "main", "pages": [c["page"]], "figure": f"Figure {c['fig']}, {name} inset",
                "method": "digitised_manual", "tool": "geosigma.extract.rotstein_mt (pixel readings)",
                "extracted_on": date.today().isoformat(),
                "notes": "1D inversion of TE data. Top of plot is 0.1 km; the first layer is extended to the surface.",
            },
            "notes": (f"Report Table 2: crustal low-resistivity layer from {TABLE2_KM[name]} km. "
                      if name in TABLE2_KM else "")
                     + ("Report warns of strong 2D/3D effects; layer depths may be off by tens of percent."
                        if noisy else "Report rates this sounding among the most reliable."),
        })
    return out


def run():
    import yaml

    sfile = SDIR / "survey.yaml"
    survey = yaml.safe_load(sfile.read_text())
    sites = []
    for name, px in SITES_PX.items():
        x, y = site_coords(px)
        sites.append({"id": name, "name": f"MT sounding {name} ({REGION[name]})",
                      "coords": {"x": x, "y": y, "crs": "EPSG:28193", "source": "map", "accuracy_m": 300}})
    for i, px in enumerate(NOISY_PX, 1):
        x, y = site_coords(px)
        sites.append({"id": f"noisy-{i}", "name": f"Unnamed MT sounding {i} (noisy, no data reported)",
                      "coords": {"x": x, "y": y, "crs": "EPSG:28193", "source": "map", "accuracy_m": 300}})
    survey["sites"] = sites
    survey["extraction_status"] = "complete"
    sfile.write_text(yaml.safe_dump(survey, sort_keys=False, allow_unicode=True, width=110))
    ds = models()
    (SDIR / "datasets").mkdir(exist_ok=True)
    (SDIR / "datasets" / "layered_models.json").write_text(json.dumps(ds, indent=1))
    return ds


if __name__ == "__main__":
    for d in run():
        print(d["site"], [(l["top_m"], l["bottom_m"], l["rho_ohmm"]) for l in d["layers"]])
