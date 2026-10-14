"""Digitise the apparent-resistivity profile plots of the 1982 Geoelectric Atlas.

Each plot page holds two or three panels: apparent resistivity (log axis) against
the reading number along the line, one panel per Wenner spacing. Readings are
drawn as filled dots joined by lines; pages with repeat surveys overlay one line
style per date (dashed, thin, thick).

``read_panels(page)`` finds each panel's axes, calibrates them from the tick marks
(the resistivity labels are OCR'd and fitted on a log scale) and returns the dot
centres in data units. Assigning dots to dates is left to ``link_series``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

DPI = 200


def render(page) -> np.ndarray:
    import pymupdf

    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).copy()


def _runs(mask1d: np.ndarray, gap: int = 2) -> list[tuple[int, int]]:
    idx = np.flatnonzero(mask1d)
    if not len(idx):
        return []
    out, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            out.append((s, p))
            s = i
        p = i
    out.append((s, p))
    return out


@dataclass
class Panel:
    axis_y: int
    axis_x: int
    x_right: int
    top: int
    px_per_station: float = 0.0
    y_fit: tuple[float, float] = (0.0, 0.0)  # log10(rho) = a + b*y
    y_ticks: list[tuple[float, float]] = field(default_factory=list)  # (y_px, label)
    dots: list[tuple[float, float]] = field(default_factory=list)  # (x_px, y_px)
    snap: dict = field(default_factory=dict)  # dot x_px -> station on the reading grid

    def station(self, x: float) -> float:
        return (x - self.axis_x) / self.px_per_station

    def rho(self, y: float) -> float:
        a, b = self.y_fit
        return float(10 ** (a + b * y))

    def grid_station(self, x: float) -> float:
        return self.snap.get(x, round(self.station(x) * 2) / 2)

    def points(self) -> list[tuple[float, float]]:
        return [(self.grid_station(x), float(f"{self.rho(y):.3g}")) for x, y in self.dots]


def find_panels(dk: np.ndarray) -> list[tuple[int, int, int, int]]:
    """(y_axis_x, top_y, x_axis_y, x_axis_right) of each panel.

    X axes are rows holding one long run of ink, shorter than the page frame. The
    y axis starts at the run's left end; the panel top is where that axis begins
    below the previous panel (a window of +-8 px follows the skew of the scans).
    """
    H, W = dk.shape
    rows = []
    for y in range(150, H - 40):
        for s0, e0 in _runs(dk[y - 1 : y + 2].any(0), gap=12):
            if 0.36 * W <= e0 - s0 <= 0.8 * W and s0 > 0.08 * W:
                rows.append((y, int(s0), int(e0)))
    groups = []
    for r in rows:
        if groups and r[0] - groups[-1][-1][0] <= 6:
            groups[-1].append(r)
        else:
            groups.append([r])
    out, prev = [], 40
    for gr in groups:
        y, s0, e0 = max(gr, key=lambda t: t[2] - t[1])
        ax = s0
        # refine: the y axis is the darkest column near the run start, just above the axis
        # (the run can start at a tick label left of the axis, so look right of it too)
        x0 = max(0, ax - 10)
        win = dk[y - 300 : y - 5, x0 : ax + 60].sum(0)
        ax = x0 + int(np.argmax(win))
        col = dk[:, ax - 8 : ax + 9].any(1)
        seg = [r for r in _runs(col[prev + 60 : y + 3], gap=120) if r[1] - r[0] >= 30]
        if not seg:
            continue
        top = prev + 60 + int(seg[-1][0])  # the stretch that reaches the x axis
        if y - top < 200:
            continue
        out.append((ax, top, y, e0))
        prev = y
    return out


def _ocr_labels(g: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> list[tuple[float, float]]:
    """Numbers printed in a column strip, with their vertical centres (page px)."""
    import pytesseract
    from PIL import Image

    crop = g[y0:y1, x0:x1]
    big = np.kron(crop, np.ones((2, 2), np.uint8))
    data = pytesseract.image_to_data(Image.fromarray(np.pad(big, 20, constant_values=255)),
                                     config="--psm 6 -c tessedit_char_whitelist=0123456789.",
                                     output_type=pytesseract.Output.DICT)
    out = []
    for t, top, h in zip(data["text"], data["top"], data["height"]):
        t = t.strip().strip(".")
        if not t:
            continue
        try:
            v = float(t)
        except ValueError:
            continue
        out.append((y0 + (top - 20 + h / 2) / 2, v))
    return out


def _fit_log(labels: list[tuple[float, float]]) -> tuple[tuple[float, float], list]:
    """Fit log10(value) = a + b*y, dropping labels that do not fit (OCR misreads)."""
    labels = [(y, v) for y, v in labels if v > 0]
    best = None
    for i in range(len(labels)):  # RANSAC over label pairs
        for j in range(i + 1, len(labels)):
            (y1, v1), (y2, v2) = labels[i], labels[j]
            if abs(y2 - y1) < 30 or v1 == v2:
                continue
            b = (np.log10(v2) - np.log10(v1)) / (y2 - y1)
            if b >= 0:
                continue
            a = np.log10(v1) - b * y1
            inl = [(y, v) for y, v in labels if abs(np.log10(v) - (a + b * y)) < 0.02]
            if best is None or len(inl) > len(best):
                best = inl
    if not best or len(best) < 3:
        return (0.0, 0.0), []
    ys = np.array([y for y, _ in best])
    b, a = np.polyfit(ys, np.log10([v for _, v in best]), 1)
    return (float(a), float(b)), best


def find_dots(dk: np.ndarray, x0: int, x1: int, y0: int, y1: int, rmin: float = 3.6):
    """Centres of filled dots: local maxima of the distance transform above the line half-width."""
    area = dk[y0:y1, x0:x1]
    dt = ndi.distance_transform_edt(area)
    mx = ndi.maximum_filter(dt, size=9)
    cand = np.argwhere((dt >= rmin) & (dt == mx))
    dots = []
    for y, x in sorted(cand.tolist(), key=lambda p: -dt[p[0], p[1]]):
        if all((x - a) ** 2 + (y - b) ** 2 > 64 for a, b, _ in dots):
            dots.append((x, y, dt[y, x]))
    return [(x0 + x, y0 + y) for x, y, _ in sorted(dots)]


def _snap_stations(p: Panel, dots):
    """Readings sit on a regular grid (whole or half stations), but hand-plotted dots
    drift slowly against the tick marks. Fit that drift, drop dots off the grid (line
    crossings) and snap the rest."""
    st = np.array([p.station(x) for x, _ in dots])
    fr = st % 1
    ph = np.angle(np.exp(2j * np.pi * fr).mean()) / (2 * np.pi) % 1
    keep = np.ones(len(st), bool)
    c1, c0 = 0.0, 0.0
    for _ in range(3):
        r = (st - ph - (c0 + c1 * st) + 0.5) % 1 - 0.5
        keep = np.abs(r) < 0.15
        if keep.sum() >= 4:
            c1, c0 = np.polyfit(st[keep], ((st - ph + 0.5) % 1 - 0.5)[keep], 1)
    base = 0.5 if 0.25 <= ph < 0.75 else 0.0
    out, snap = [], {}
    for d, s_, k in zip(dots, st, keep):
        if not k:
            continue
        corr = s_ - (c0 + c1 * s_)
        snap[d[0]] = float(np.round(corr - base) + base)
        out.append(d)
    return out, snap


def read_panels(page) -> list[Panel]:
    g = render(page)
    dk = g < 140
    panels = []
    for ax, top, ay, right in find_panels(dk):
        p = Panel(axis_y=ay, axis_x=ax, x_right=right, top=top)
        band = dk[ay + 6 : ay + 16, ax - 3 : right + 3].any(0)
        ticks = [ax - 3 + (a + b) / 2 for a, b in _runs(band, gap=1)]
        gaps = np.diff(ticks)
        gaps = gaps[(gaps > 15) & (gaps < 80)]
        p.px_per_station = float(np.median(gaps)) if len(gaps) else 0.0
        labels = _ocr_labels(g, max(0, ax - 130), ax - 4, max(0, top - 25), ay + 25)
        p.y_fit, p.y_ticks = _fit_log(labels)
        if p.y_ticks:  # the highest label marks the top of the plotting area
            p.top = max(top, int(min(y for y, _ in p.y_ticks)) - 15)
        dots = find_dots(dk, ax + 8, right, p.top + 2, ay - 3)
        if p.px_per_station and dots:
            dots, p.snap = _snap_stations(p, dots)
        p.dots = dots
        panels.append(p)
    return panels


def segment_features(dk: np.ndarray, dt: np.ndarray, a, b, skip: float = 8.0):
    """Ink coverage and mean half-width along the straight segment a-b (dot radii skipped)."""
    (x1, y1), (x2, y2) = a, b
    L = float(np.hypot(x2 - x1, y2 - y1))
    if L <= 2 * skip + 4:
        return 1.0, 0.0, L
    ts = np.linspace(skip / L, 1 - skip / L, max(8, int(L - 2 * skip)))
    xs, ys = x1 + ts * (x2 - x1), y1 + ts * (y2 - y1)
    cov, wid = [], []
    for x, y in zip(xs, ys):
        xi, yi = int(round(x)), int(round(y))
        win = dt[yi - 1 : yi + 2, xi - 1 : xi + 2]
        hit = win.max() if win.size else 0
        cov.append(hit > 0)
        if hit > 0:
            wid.append(hit)
    return float(np.mean(cov)), float(np.median(wid)) if wid else 0.0, L


STYLES = ("dashed", "thin", "thick")


def style_masks(dk: np.ndarray, dots: list[tuple[float, float]]) -> dict[str, np.ndarray]:
    """Split the ink into thick strokes, thin solid strokes and dashes, with the dots removed."""
    H, W = dk.shape
    yy, xx = np.ogrid[:H, :W]
    dotm = np.zeros_like(dk)
    for x, y in dots:
        y0, y1, x0, x1 = int(y) - 10, int(y) + 11, int(x) - 10, int(x) + 11
        dotm[y0:y1, x0:x1] |= (yy[y0:y1] - y) ** 2 + (xx[:, x0:x1] - x) ** 2 <= 81
    thick = ndi.binary_opening(dk, structure=np.ones((3, 3))) & ~dotm
    thick = ndi.binary_opening(thick, structure=np.ones((2, 2)))
    lab, n = ndi.label(thick)
    sizes = ndi.sum(thick, lab, range(1, n + 1))
    thick = np.isin(lab, 1 + np.flatnonzero(sizes >= 40))  # drop the specks thin lines leave
    rest = dk & ~ndi.binary_dilation(thick, iterations=3) & ~dotm
    lab, n = ndi.label(rest, structure=np.ones((3, 3)))
    thin = np.zeros_like(dk)
    dashed = np.zeros_like(dk)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        target = dashed if np.hypot(h, w) < 34 else thin
        target[sl] |= lab[sl] == i
    return {"thick": thick, "thin": thin, "dashed": dashed, "ink": dk,
            "dt": ndi.distance_transform_edt(dk)}


def _coverage(mask: np.ndarray, a, b, skip: float = 9.0, tol: int = 2) -> float:
    (x1, y1), (x2, y2) = a, b
    L = float(np.hypot(x2 - x1, y2 - y1))
    if L <= 2 * skip + 4:
        return 0.5  # dots nearly touch: no evidence either way
    n = max(8, int(L - 2 * skip))
    ts = np.linspace(skip / L, 1 - skip / L, n)
    hits = 0
    for t in ts:
        xi, yi = int(round(x1 + t * (x2 - x1))), int(round(y1 + t * (y2 - y1)))
        hits += bool(mask[yi - tol : yi + tol + 1, xi - tol : xi + tol + 1].any())
    return hits / n


def link_series(panel: Panel, masks: dict[str, np.ndarray], styles=STYLES, min_cov=None):
    """For each line style, the best chain of dots (one per station) joined by that style."""
    min_cov = min_cov or {"thick": 0.6, "thin": 0.6, "dashed": 0.35}
    by_st: dict[float, list] = {}
    for x, y in panel.dots:
        by_st.setdefault(panel.grid_station(x), []).append((x, y))
    keys = sorted(by_st)
    out = {}
    for style in styles:
        m = masks[style]
        # DP over stations: best[k][i] = (score, back) of a chain ending at dot i of station k
        best = [[(0.0, None) for _ in by_st[k]] for k in keys]
        top = (0.0, None)
        for k in range(1, len(keys)):
            if keys[k] - keys[k - 1] > 1.01:
                continue
            for j, b in enumerate(by_st[keys[k]]):
                for i, a in enumerate(by_st[keys[k - 1]]):
                    c = _coverage(m, a, b)
                    if c < min_cov[style]:
                        continue
                    sc = best[k - 1][i][0] + c
                    if sc > best[k][j][0]:
                        best[k][j] = (sc, i)
                if best[k][j][0] > top[0]:
                    top = (best[k][j][0], (k, j))
        chain = []
        node = top[1]
        while node is not None:
            k, j = node
            x, y = by_st[keys[k]][j]
            chain.append((keys[k], x, y))
            back = best[k][j][1]
            node = (k - 1, back) if back is not None else None
        out[style] = chain[::-1]
    return out


def _edge_profile(dk, dt, a, b, skip: float = 9.0):
    (x1, y1), (x2, y2) = a, b
    L = float(np.hypot(x2 - x1, y2 - y1))
    if L <= 2 * skip + 4:
        return 0.75, 0.0, 0, L
    ts = np.linspace(skip / L, 1 - skip / L, max(8, int(L - 2 * skip)))
    on, w = [], []
    for t in ts:
        xi, yi = int(round(x1 + t * (x2 - x1))), int(round(y1 + t * (y2 - y1)))
        m = dt[yi - 1 : yi + 2, xi - 1 : xi + 2].max()
        on.append(m > 0)
        if m > 0:
            w.append(m)
    on = np.array(on, int)
    gaps = int(np.sum(np.diff(on) == -1))
    return float(on.mean()), float(np.mean(w)) if w else 0.0, gaps, L


def link_joint(panel: Panel, masks: dict[str, np.ndarray], styles=STYLES):
    """Assign every dot to the dated series at once (Viterbi over stations).

    State at a station: for each style, the index of its dot there, or -1 when that
    survey has no reading there. Edges score the ink of the style's mask between the
    two dots; leaving a dot unassigned, sharing a dot and starting or stopping a series
    are penalised.
    """
    import itertools

    by_st: dict[float, list] = {}
    for x, y in panel.dots:
        by_st.setdefault(panel.grid_station(x), []).append((x, y))
    keys = sorted(by_st)
    S = len(styles)

    def states(k):
        n = len(by_st[keys[k]])
        for st in itertools.product(range(-1, n), repeat=S):
            used = {i for i in st if i >= 0}
            pen = 1.5 * (n - len(used)) + 0.25 * (sum(i >= 0 for i in st) - len(used))
            yield st, pen

    cache = {}

    dk = masks["ink"]
    dt = masks["dt"]

    def cov(style, k, i, j):
        """Edge evidence for this style: ink right on the segment, plus a style term
        (thick strokes survive an opening; dashes leave gaps; thin lines are narrow
        and unbroken). Short segments carry little style information."""
        key = (style, k, i, j)
        if key not in cache:
            a, b = by_st[keys[k - 1]][i], by_st[keys[k]][j]
            on, width, gaps, L = _edge_profile(dk, dt, a, b)
            weight = min(1.0, L / 120)
            if style == "thick":
                term = 1.0 if _coverage(masks["thick"], a, b) > 0.8 else -1.0
            elif style == "dashed":
                term = 1.0 if gaps >= 3 else -1.0
            else:
                term = 1.0 if gaps <= 1 and width < 1.8 else -1.0
            cache[key] = on + 0.35 * weight * term
        return cache[key]

    layer = {st: (-pen, None) for st, pen in states(0)}
    hist = [layer]
    for k in range(1, len(keys)):
        new = {}
        adjacent = keys[k] - keys[k - 1] <= 1.01
        for st, pen in states(k):
            best = None
            for prev, (sc, _) in hist[-1].items():
                t = sc - pen
                for s in range(S):
                    a, b = prev[s], st[s]
                    if a >= 0 and b >= 0:
                        t += max(2.0 * cov(styles[s], k, a, b) - 1.0, -0.6) if adjacent else -1.0
                    elif (a >= 0) != (b >= 0):
                        t -= 0.8
                pairs = [(prev[s], st[s]) for s in range(S) if prev[s] >= 0 and st[s] >= 0]
                t -= 1.6 * (len(pairs) - len(set(pairs)))  # two dates on the same ink
                if best is None or t > best[0]:
                    best = (t, prev)
            new[st] = best
        hist.append(new)
    st = max(hist[-1], key=lambda s: hist[-1][s][0])
    path = []
    for k in range(len(keys) - 1, -1, -1):
        path.append(st)
        st = hist[k][st][1]
    path = path[::-1]
    out = {s: [] for s in styles}
    for k, st in enumerate(path):
        for s, i in zip(styles, st):
            if i >= 0:
                x, y = by_st[keys[k]][i]
                out[s].append((keys[k], x, y))
    return out
