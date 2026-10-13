"""Digitise the Afek 2013 CSAMT smooth-model plots (Appendix C) into 1D models.

Each Appendix C page holds two raster plots. The right panel of each plot is the
SCS2D smooth-model resistivity against depth. Inputs, kept in the survey folder:

* ``extraction/plot_map.json``: plot image -> App B line, station, receiver
  coordinates (matched by page order; see ``scripts/afek/``).
* ``extraction/axis_calibration.json``: per plot, the log10 resistivity at the
  left and right frame edges (read from the axis labels) and the depth tick rows.

Run: ``python -m geosigma.extract.afek`` (needs the App C PDF in data/sources/pdf).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

from ..store import ROOT, SURVEYS_DIR

SURVEY = "afek-2013-csamt"
SDIR = SURVEYS_DIR / SURVEY
PDF = ROOT / "data" / "sources" / "pdf" / "Afek-Project-Geophysical-Report-Appendix-C.pdf"

# Model panel frame in plot pixels (all 240 plots share one layout).
X0, X1 = 454, 665  # frame edges = left and right axis exponents
Y0, Y1 = 14, 466  # frame top = 0 m
DEPTH_TICK_M = 200


def plot_images(pdf: Path = PDF) -> dict[str, np.ndarray]:
    """Return {"pNNN_i.png": grey image} for every embedded plot."""
    import pymupdf

    out = {}
    with pymupdf.open(pdf) as doc:
        for pno in range(2, len(doc)):
            page = doc[pno]
            for i, img in enumerate(page.get_images(full=True)):
                pix = pymupdf.Pixmap(doc, img[0])
                if pix.n - pix.alpha > 1:
                    pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
                a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, 0]
                out[f"p{pno + 1:03d}_{i}.png"] = a
    return out


def depth_scale(ticks: list[float]) -> float:
    """Pixels per 200 m, from the median spacing of the regular depth ticks."""
    t = np.array(sorted(ticks))
    sp = np.diff(t)
    med = np.median(sp)
    good = sp[np.abs(sp - med) < 3]
    return float(np.mean(good))


def _rdp(pts: np.ndarray, tol: float) -> np.ndarray:
    """Ramer-Douglas-Peucker simplification of a polyline."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.hypot(*ab) or 1.0
    d = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n
    i = int(np.argmax(d))
    if d[i] > tol:
        return np.vstack([_rdp(pts[: i + 1], tol)[:-1], _rdp(pts[i:], tol)])
    return np.vstack([a, b])


def trace(img: np.ndarray, el: int, er: int, px_per_tick: float) -> list[tuple[float, float]]:
    """Return [(depth_m, rho_ohmm), ...] traced from the model panel."""
    dark = img < 128
    n_dec = er - el
    # major and minor (2..9) log ticks along the top and bottom frame edges
    xlat = [X0 + (k + np.log10(m)) * (X1 - X0) / n_dec for k in range(n_dec + 1) for m in range(1, 10)]
    ytick = [Y0 + k * px_per_tick for k in range(1, 20) if Y0 + k * px_per_tick < Y1]
    # frame lines are not always on exactly the same row; skip any row that is mostly dark
    frame_rows = set(np.nonzero(dark[:, X0 + 5 : X1 - 5].mean(axis=1) > 0.6)[0].tolist())
    frame_rows |= {r + 1 for r in frame_rows} | {r - 1 for r in frame_rows}
    pts: list[tuple[float, float]] = []  # (y, x) pixel path
    prev = None
    for y in range(Y0 + 2, Y1 - 1):
        if y in frame_rows:
            continue
        xs = np.nonzero(dark[y, X0 + 1 : X1])[0] + X0 + 1
        # drop axis tick marks on the frame edges
        keep = []
        for x in xs:
            near_ytick = any(abs(y - t) <= 1.5 for t in ytick)
            if near_ytick and (x <= X0 + 7 or x >= X1 - 7):
                continue
            if (y <= Y0 + 7 or y >= Y1 - 7) and any(abs(x - c) <= 2.2 for c in xlat):
                continue
            keep.append(x)
        if not keep:
            continue
        runs, start = [], keep[0]
        for a, b in zip(keep, keep[1:] + [None]):
            if b is None or b - a > 2:
                runs.append((start, a))
                start = b
        if prev is None:
            r = runs[0]
        else:
            r = min(runs, key=lambda r: min(abs(r[0] - prev), abs(r[1] - prev)))
        lo, hi = r
        if hi - lo > 3:  # horizontal step: enter at the end nearest the previous point
            first, last = (lo, hi) if prev is None or abs(lo - prev) <= abs(hi - prev) else (hi, lo)
            pts += [(y, first), (y, last)]
            prev = last
        else:
            prev = (lo + hi) / 2
            pts.append((y, prev))
    p = _rdp(np.array(pts, float), 0.75)
    out = []
    for y, x in p:
        depth = (y - Y0) * DEPTH_TICK_M / px_per_tick
        log_rho = el + (x - X0) / (X1 - X0) * n_dec
        out.append((round(depth, 1), float(f"{10 ** log_rho:.4g}")))
    # the curve starts on the frame's top edge (0 m), which the trace has to skip
    if out and out[0][0] < 15:
        out[0] = (0.0, out[0][1])
    return out


def site_id(line: str, station: int, comp: str) -> str:
    return f"{line}-{station}" + ("-Ey" if comp == "Ey" else "")


def run() -> list[dict]:
    pmap = json.loads((SDIR / "extraction" / "plot_map.json").read_text())
    cal = json.loads((SDIR / "extraction" / "axis_calibration.json").read_text())
    imgs = plot_images()
    datasets = []
    for m in pmap:
        name = Path(m["file"]).name
        c = cal[name]
        el, er = c["log10_rho_left"], c["log10_rho_right"]
        sp = depth_scale(c["depth_ticks_px"])
        samples = trace(imgs[name], el, er, sp)
        sid = site_id(m["line"], m["station"], m["comp"])
        dz = DEPTH_TICK_M / sp
        dlog = (er - el) / (X1 - X0)
        datasets.append({
            "id": f"afek-csamt-{sid}-scs2d",
            "survey": SURVEY,
            "site": sid,
            "line": m["line"],
            "method": "CSAMT",
            "level": "L2",
            "representation": "model_1d",
            "measured_on": "2013",
            "depth_max_m": round((Y1 - Y0) * dz, 0),
            "confidence": "B",
            "status": "draft",
            "model_type": "smooth",
            "samples": [{"depth_m": d, "rho_ohmm": r} for d, r in samples],
            "digitisation_error": f"+-{2 * dlog:.3f} log10 rho, +-{2 * dz:.0f} m (2 px)",
            "provenance": {
                "document": "appC",
                "pages": [m["page"]],
                "figure": f'Plot "{m["title_ocr"].strip(chr(34) + chr(39) + " “")}"',
                "method": "digitised_auto",
                "tool": "geosigma.extract.afek (curve trace, RDP 0.75 px)",
                "extracted_on": date.today().isoformat(),
                "notes": "Zonge SCS2D smooth-model 1D inversion, TM mode (report p. 25).",
            },
            "notes": "DOI not given in the report; plot depth is the model extent, not a DOI.",
        })
    # Six broadside lines show the same plot for the Ey station and the next Ex station.
    seen: dict[str, list[dict]] = {}
    for d in datasets:
        seen.setdefault(json.dumps(d["samples"]), []).append(d)
    for group in seen.values():
        for d in group if len(group) > 1 else []:
            other = ", ".join(o["site"] for o in group if o is not d)
            d["confidence"] = "C"
            d["notes"] += f" Plot is identical to the one for {other} in App. C; the report may repeat a plot."
    out = SDIR / "datasets" / "appC_smooth_models.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(datasets, indent=1))
    return datasets


if __name__ == "__main__":
    ds = run()
    print(len(ds), "models written")
