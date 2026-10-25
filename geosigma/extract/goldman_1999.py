"""Digitise the Goldman & Ezersky 1999 TDEM model plots (northern Arava water reservoirs).

The report (GII 822/90/98(3)) prints no model tables. Each appendix page (9-32)
holds one station's plot: the measured curve with its fit on the left, and on the
right the author's model, resistivity (log axis) against depth, as a staircase.
Every station has a layered and a smooth inversion page.

Axis values per plot are read from the printed labels and kept in
``extraction/plot_calibration.yaml``. This script, for each plot:

- renders the page at 300 dpi and finds the model panel frame;
- checks the axis values against the tick marks (log ticks 1-9 per decade under
  the bottom frame, 100 m ticks on the right frame) and fits the pixel scales to
  the ticks;
- traces the staircase: horizontal runs are layer boundaries, the vertical line
  between them gives the layer resistivity;
- marks a layer whose line lies on the panel edge as clipped (the value is beyond
  the axis, so only a bound is stored).

Run: ``python -m geosigma.extract.goldman_1999``.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import yaml
from scipy import ndimage

from ..store import ROOT, SURVEYS_DIR

SURVEY = "goldman-1999-tdem-arava-reservoirs"
SDIR = SURVEYS_DIR / SURVEY
PDF = ROOT / "data" / "sources" / "pdf" / "Goldman-M-TDEM-Survey-Water-Reservoirs-Northern-Arava-GII-Rep-822-90-98-3-1999.pdf"
DPI = 300
MARGIN = 7  # px inside the frame ignored when tracing
H_RUN = 12  # px of line in one row that make a horizontal step
EDGE = 3  # px: a line this close to the frame is the frame itself (value off the axis)
MAX_TICK_MISS = 8  # px


def render(page: int, rotate: int = 0) -> np.ndarray:
    import pymupdf

    with pymupdf.open(PDF) as doc:
        pix = doc[page - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    im = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width) < 128
    return np.rot90(im, rotate // 90) if rotate else im


def _longest_run(v: np.ndarray) -> int:
    if not v.any():
        return 0
    d = np.diff(np.concatenate(([0], v.astype(np.int8), [0])))
    return int((np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]).max())


def _lines(mask: np.ndarray, axis: int, minlen: int) -> list[float]:
    """Centres of straight lines at least ``minlen`` long: columns (axis 0) or rows (axis 1)."""
    n = mask.shape[1] if axis == 0 else mask.shape[0]
    hits = [i for i in range(n) if _longest_run(mask[:, i] if axis == 0 else mask[i, :]) >= minlen]
    groups: list[list[int]] = []
    for i in hits:
        if groups and i - groups[-1][-1] <= 3:
            groups[-1].append(i)
        else:
            groups.append([i])
    return [(g[0] + g[-1]) / 2 for g in groups]


def _groups(idx) -> list[float]:
    out: list[list[int]] = []
    for i in idx:
        if out and i - out[-1][-1] <= 2:
            out[-1].append(i)
        else:
            out.append([i])
    return [float(np.mean(g)) for g in out]


def panel(im: np.ndarray) -> tuple[float, float, float, float, float]:
    """Model panel frame (left, right, top, bottom) and the left frame of the curve panel."""
    H, W = im.shape
    V = _lines(im, 0, int(0.2 * H))
    R = V[-1]
    for L in (v for v in V if 0.4 * W < v < R - 200):
        sub = ndimage.binary_dilation(im[:, int(L):int(R) + 1], np.ones((7, 3)))
        Hs = _lines(sub, 1, int(0.9 * (R - L)))
        if len(Hs) >= 2:
            return L, R, Hs[0], Hs[-1], V[0]
    raise ValueError("model panel not found")


def calibrate(im, box, rho, depth_max):
    """Fit log10(rho) = a + b*x and depth = c + d*y to the tick marks; return the fits and the worst misses."""
    L, R, T, B = box
    l0, l1 = np.log10(rho[0]), np.log10(rho[1])
    zone = im[int(B) + 5:int(B) + 20, int(L) + 8:int(R) - 7]
    xt = np.array([int(L) + 8 + t for t in _groups(np.nonzero(zone.sum(0) >= 4)[0])])
    logs = [np.log10(k * 10.0 ** n) for n in range(int(round(l0)), int(round(l1))) for k in range(1, 10)] + [l1]
    px = L + (np.array(logs) - l0) / (l1 - l0) * (R - L)
    inner = [(lg, p) for lg, p in zip(logs, px) if L + 10 < p < R - 10]
    pairs = [(lg, xt[np.abs(xt - p).argmin()]) for lg, p in inner]
    miss_x = max(abs(x - p) for (lg, x), (_, p) in zip(pairs, inner))
    pts = [(L, l0), (R, l1)] + [(x, lg) for lg, x in pairs]
    b, a = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)
    zone = im[int(T) + 8:int(B) - 7, int(R) - 28:int(R) - 6]
    yt = np.array([int(T) + 8 + t for t in _groups(np.nonzero(zone.sum(1) >= 8)[0])])
    nt = int(round(depth_max / 100))
    py = [T + k / nt * (B - T) for k in range(1, nt)]
    ys = [yt[np.abs(yt - p).argmin()] for p in py]
    miss_y = max(abs(y - p) for y, p in zip(ys, py))
    pts = [(T, 0.0), (B, float(depth_max))] + [(y, k * 100.0) for k, y in enumerate(ys, 1)]
    d, c = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)
    return (a, b), (c, d), miss_x, miss_y


def trace(im, box):
    """Staircase as [(y_top, y_bottom, x or None, x spread)] in page pixels."""
    L, R, T, B = box
    y0, x0 = int(T) + MARGIN, int(L) + MARGIN
    sub = im[y0:int(B) - MARGIN + 1, x0:int(R) - MARGIN + 1]
    lab, n = ndimage.label(sub, structure=np.ones((3, 3)))
    sizes = ndimage.sum(sub, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 0.05 * max(sizes)])
    cnt = keep.sum(1)
    bounds = []
    for g in _groups(np.nonzero(cnt > H_RUN)[0]):
        bounds.append(y0 + g)
    edges = [T] + bounds + [B]
    out = []
    for ya, yb in zip(edges[:-1], edges[1:]):
        rows = [r for r in range(int(ya - y0) + 6, int(yb - y0) - 6) if 0 <= r < len(cnt) and 0 < cnt[r] <= H_RUN]
        if not rows:
            rows = [r for r in range(max(int(ya - y0), 0), min(int(yb - y0), len(cnt))) if 0 < cnt[r] <= H_RUN]
        xs = [float(np.median(np.nonzero(keep[r])[0])) for r in rows]
        out.append((ya, yb, x0 + float(np.median(xs)) if xs else None, float(np.percentile(xs, 90) - np.percentile(xs, 10)) if xs else None))
    return out


def build() -> list[dict]:
    cfg = yaml.safe_load((SDIR / "extraction" / "plot_calibration.yaml").read_text())
    sv = yaml.safe_load((SDIR / "survey.yaml").read_text())
    today = date.today().isoformat()
    ds, boxes, report, problems = [], {}, [], []
    for p in cfg["plots"]:
        im = render(p["page"], p.get("rotate", 0))
        L, R, T, B, Lc = panel(im)
        (a, b), (c, d), mx, my = calibrate(im, (L, R, T, B), p["rho"], p["depth_max"])
        tag = f"page {p['page']} {p['station']} {p['model']}"
        if mx > MAX_TICK_MISS or my > MAX_TICK_MISS:
            problems.append(f"{tag}: axis ticks miss the calibration by {mx:.1f}/{my:.1f} px")
        layers = []
        steps = trace(im, (L, R, T, B))
        for i, (ya, yb, x, spread) in enumerate(steps):
            top = 0.0 if i == 0 else round(c + d * ya, 1)
            bottom = None if i == len(steps) - 1 else round(c + d * yb, 1)
            lay = {"top_m": top, "bottom_m": bottom}
            if x is None:
                problems.append(f"{tag}: no line found between {top} and {bottom} m")
                continue
            if spread > 10:
                problems.append(f"{tag}: layer {top}-{bottom} m line wanders by {spread:.0f} px")
            rho = 10 ** (a + b * x)
            if x > R - MARGIN - EDGE:
                lay["rho_min"] = round(10 ** (a + b * R), 3)
                lay["note"] = "The line runs along the right edge of the plot: the value is beyond the axis maximum."
            elif x < L + MARGIN + EDGE:
                lay["rho_max"] = round(10 ** (a + b * L), 3)
                lay["note"] = "The line runs along the left edge of the plot: the value is below the axis minimum."
            else:
                lay["rho_ohmm"] = round(float(rho), 3 if rho < 1 else 2 if rho < 10 else 1 if rho < 100 else 0)
            layers.append(lay)
        report.append(f"{tag}: ticks miss {mx:.1f}/{my:.1f} px; " + "; ".join(
            f"{l['top_m']:g}-{l['bottom_m'] if l['bottom_m'] is not None else '':} m "
            f"{l.get('rho_ohmm', '>' + str(l.get('rho_min')) if 'rho_min' in l else '<' + str(l.get('rho_max')))}" for l in layers))
        st = p["station"]
        did = f"goldman1999-{st}-{p['model']}"
        H, W = im.shape
        # Box the model panel and its axis labels; for the station name, the crop region also
        # reaches the curve panel title on the left.
        bx = [(L - 260) / W, (T - 30) / H, (R + 40) / W, (B + 260) / H]
        if p.get("rotate") == 90:  # back to the unrotated page: x = 1 - y', y = x'
            bx = [1 - bx[3], bx[0], 1 - bx[1], bx[2]]
        bx = [round(min(max(v, 0), 1), 4) for v in bx]
        cap = (f"The boxed panel is the author's {p['model']} inversion model for station {st} (resistivity "
               f"against depth in hundreds of metres); the left panel is the measured curve and its fit. "
               "Values were traced from the plot")
        if p.get("rotate"):
            cap += ". The page is printed sideways"
        boxes[did] = {"page": p["page"], "box": bx, "caption": cap}
        ds.append({
            "id": did, "survey": SURVEY, "site": st, "method": "TEM", "level": "L2", "representation": "model_1d",
            "measured_on": None, "depth_max_m": float(p["depth_max"]), "confidence": p.get("confidence", "B"), "status": "draft",
            "model_type": p["model"], "layers": layers,
            **({"notes": p["notes"]} if p.get("notes") else {}),
            "digitisation_error": "+-0.03 log10 rho, +-3 m (line width and axis fit)",
            "provenance": {
                "document": "main", "pages": [p["page"], cfg["stations"][st]["text_page"]],
                "figure": f"Appendix, {p['model']} inversion plot {st} (right panel); text with the coordinates",
                "method": "digitised_auto", "tool": "geosigma.extract.goldman_1999 (staircase trace, 300 dpi)",
                "extracted_on": today,
                "notes": "Axis values read from the labels and checked against the tick marks; the station's "
                         "coordinates are printed in the text."},
        })
    if problems:
        raise SystemExit(f"{SURVEY}: problems:\n  " + "\n  ".join(problems))
    sv["sites"] = [{"id": st, "name": f"TDEM station {st}",
                    "coords": {"x": s["xy"][0], "y": s["xy"][1], "crs": "EPSG:28193", "source": "text",
                               "accuracy_m": 10}} for st, s in cfg["stations"].items()]
    (SDIR / "survey.yaml").write_text(yaml.safe_dump(sv, sort_keys=False, allow_unicode=True, width=110))
    (SDIR / "datasets" / "models.json").write_text(json.dumps(ds, indent=1, ensure_ascii=False))
    (SDIR / "extraction" / "table_boxes.json").write_text(json.dumps(boxes, indent=1))
    (SDIR / "extraction" / "trace_report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"{SURVEY}: {len(sv['sites'])} sites, {len(ds)} models")
    return ds


if __name__ == "__main__":
    build()
