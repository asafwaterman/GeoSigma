"""Box edges on the Southern Arava VES sheets (Paparo 1969, GK/625/68).

These sheets are faint grey scans on a wider log paper than the later Paparo sheets, so
``ves_sheet.read_sheet`` does not find their axis or model band. Here the AB/2 axis is
found by fitting a log-paper comb to the thin grid lines (1 m at the left frame, about
324 px per decade at 100 dpi). The band under the plot is searched for vertical lines
that span most of its height: those are the box edges.

When a sheet's first box is too narrow for its value (written sideways at the left
edge), its right edge sits within about 0.1 m of the frame and is often too faint to
find. Then a weaker line just right of the frame is used, or 1.1 m if there is none,
and the layer is noted as such.

Writes ``extraction/ves_edges_auto.json`` ({page: [AB/2 m, ...]}), which
``build_ves`` uses for readings without ``edges_m`` or ``edges_px``.

Run: ``python -m geosigma.extract.arava_sheets``.
"""
from __future__ import annotations

import json

import numpy as np
import pymupdf
import yaml

from ..store import ROOT, SURVEYS_DIR

SURVEY = "paparo-1969-southern-arava"
SDIR = SURVEYS_DIR / SURVEY
PDF = ROOT / "data" / "sources" / "pdf" / "Paparo-H-Reinterpretation-Electrical-Resistivity-Measurements-Southern-Arava-IPRG-Rep-GK-625-68-1969.pdf"
DPI = 100
NARROW_FIRST = 1.1  # m, default edge of a sideways-labelled first box


def _mask(page) -> np.ndarray:
    from scipy import ndimage as ndi

    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    g = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).astype(float)
    return g < ndi.median_filter(g, size=25) - 25  # dark relative to the local paper tone


def fit_axis(a: np.ndarray) -> tuple[float, float]:
    """(px per decade, x of AB/2 = 1 m) from the thin vertical grid lines."""
    from scipy import ndimage as ndi

    H = a.shape[0]
    thin = a & ~ndi.binary_dilation(ndi.binary_opening(a, np.ones((4, 4))), iterations=2)
    prof = ndi.uniform_filter1d(thin[int(H * .1):int(H * .8)].sum(0).astype(float), 3)
    prof /= prof.max()
    marks = np.log10([m * 10 ** k for k in range(2) for m in range(1, 10)] + [100])
    w = np.where(np.isclose(marks % 1, 0), 3.0, 1.0)
    best = (-1.0, 0.0, 0.0)
    for s in np.arange(300, 345, 0.5):
        for o in np.arange(5, 60, 0.5):
            idx = np.round(o + marks * s).astype(int)
            sc = float((w * prof[idx]).sum())
            if sc > best[0]:
                best = (sc, s, o)
    return best[1], best[2]


def edge_candidates(a: np.ndarray, dec: float, one: float) -> list[tuple[float, int]]:
    """(AB/2 m, longest vertical run in px) for each line crossing the model band."""
    from scipy import ndimage as ndi

    H, W = a.shape
    rows = a[:, int(one):int(one + 2.5 * dec)].mean(1)
    lo, hi = int(H * .8), int(H * .9)
    ya = lo + int(np.argmax(ndi.uniform_filter1d(rows[lo:hi], 3)))  # bottom frame of the plot
    run = np.zeros(W, int)
    cur = np.zeros(W, int)
    for row in a[ya + 14:ya + 58]:
        cur = np.where(row, cur + 1, 0)
        run = np.maximum(run, cur)
    groups: list[list[int]] = []
    for x in range(int(one) + 2, W - 15):
        if run[x] >= 10:
            if groups and x - groups[-1][-1] <= 3:
                groups[-1].append(x)
            else:
                groups.append([x])
    return [(round(10 ** ((float(np.mean(g)) - one) / dec), 2), int(run[g].max())) for g in groups]


def edges_for(cands: list[tuple[float, int]], n_boxes: int, narrow_first: bool) -> tuple[list[float] | None, str | None]:
    strong = [v for v, r in cands if r >= 22]
    if strong and strong[0] < 1.12:  # the left frame of the plot (AB/2 = 1 m, give or take the fit)
        strong = strong[1:]
    if len(strong) == n_boxes - 1:
        return strong, None
    if narrow_first and len(strong) == n_boxes - 2:  # narrow first box whose edge was not found
        weak = [v for v, r in cands if r < 22 and 1.06 < v < 1.3 and v not in strong]
        return [weak[0] if weak else NARROW_FIRST] + strong, "first box edge near the frame, approximate"
    return None, None


def run() -> dict:
    readings = yaml.safe_load((SDIR / "extraction" / "ves_readings.yaml").read_text())
    doc = pymupdf.open(PDF)
    out, report = {}, {}
    for r in readings:
        a = _mask(doc[r["page"] - 1])
        dec, one = fit_axis(a)
        cands = edge_candidates(a, dec, one)
        edges, note = edges_for(cands, len(r["rho"]), bool(r.get("narrow_first")))
        report[r["page"]] = {"dec_px": dec, "one_px": one, "candidates": cands, "edges": edges, "note": note}
        if edges:
            out[r["page"]] = edges
    (SDIR / "extraction" / "ves_edges_auto.json").write_text(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    rep = run()
    bad = [p for p, v in rep.items() if not v["edges"]]
    print(f"{len(rep) - len(bad)} of {len(rep)} sheets matched; unmatched pages: {bad}")
    for p in bad:
        print(p, rep[p]["candidates"])
