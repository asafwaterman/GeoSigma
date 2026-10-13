"""Read IPRG Schlumberger (VES) field sheets.

The IPRG sheets of the 1960s-80s share one layout: log-log paper (AB/2 1-1000 m,
apparent resistivity over two decades), the field points and the fitted curve, then
a row of boxes under the x axis holding the interpreted layer resistivities. Each
box spans the AB/2 range of one layer, so the box edges, read on the AB/2 axis, are
the interface depths. The footer gives the sounding number, coordinates and elevation.

``read_sheet`` returns the pieces with pixel evidence so a person can check them;
survey-specific scripts decide how to turn coordinates and labels into records.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

DPI = 200


@dataclass
class Sheet:
    page: int
    x_one: float  # pixel x of AB/2 = 1 m
    y_one: float  # pixel y of rho_a = 10**y_exp0
    dec_x: float
    dec_y: float
    y_exp0: int = 0
    band: tuple[int, int] | None = None
    edges_px: list[float] = field(default_factory=list)
    box_text: list[str] = field(default_factory=list)
    footer: str = ""

    def ab2(self, x: float) -> float:
        return 10 ** ((x - self.x_one) / self.dec_x)

    @property
    def interfaces_m(self) -> list[float]:
        return [round(float(self.ab2(x)), 1) for x in self.edges_px]


def render(page, dpi: int = DPI) -> np.ndarray:
    import pymupdf

    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).copy()


def _fit_log_axis(prof: np.ndarray, ndec: int, starts, dlo: float, dhi: float, sign: int):
    strong = prof / (prof.max() or 1)
    best = None
    for D in np.arange(dlo, dhi, 0.5):
        for s0 in starts:
            pos = [s0 + sign * D * (k + np.log10(m)) for k in range(ndec) for m in range(1, 10)]
            pos.append(s0 + sign * D * ndec)
            if min(pos) < 2 or max(pos) > len(prof) - 3:
                continue
            sc = sum(strong[int(round(p)) - 1 : int(round(p)) + 2].max() for p in pos)
            if best is None or sc > best[0]:
                best = (sc, D, s0)
    return best


def _ocr(img: np.ndarray, psm: int = 7, extra: str = "") -> str:
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.fromarray(img), config=f"--psm {psm} {extra}").strip()


def read_sheet(page, pno: int) -> Sheet:
    g = render(page)
    d = g < 128
    H, W = d.shape
    s = DPI / 150  # search ranges were tuned at 150 dpi
    fx = _fit_log_axis(d.sum(0).astype(float), 3, np.arange(20 * s, 120 * s, 0.5), 470 * s, 520 * s, +1)
    fy = _fit_log_axis(d[:, int(100 * s) : int(1500 * s)].sum(1).astype(float), 2,
                       np.arange(H * 0.75, H * 0.95, 0.5), 470 * s, 520 * s, -1)
    sh = Sheet(page=pno, x_one=fx[2], dec_x=fx[1], y_one=fy[2], dec_y=fy[1])
    # model band: first pair of long horizontal lines below the x-axis labels
    rows = d[:, int(sh.x_one) : int(sh.x_one + 3 * sh.dec_x)].mean(1)
    long_rows = [y for y in range(int(sh.y_one + 20 * s), H) if rows[y] > 0.3]
    groups = []
    for y in long_rows:
        if groups and y - groups[-1][-1] <= 3:
            groups[-1].append(y)
        else:
            groups.append([y])
    if len(groups) >= 2:
        top, bot = groups[0][-1] + 1, groups[1][0] - 1
        sh.band = (top, bot)
        band = d[top + 3 : bot - 2, :]
        cols = band.mean(0)
        xs = [x for x in range(int(sh.x_one + 15 * s), int(sh.x_one + 3 * sh.dec_x - 10 * s)) if cols[x] > 0.85]
        edges = []
        for x in xs:
            if edges and x - edges[-1][-1] <= 3:
                edges[-1].append(x)
            else:
                edges.append([x])
        sh.edges_px = [float(np.mean(e)) for e in edges]
        bounds = [int(sh.x_one)] + [int(x) for x in sh.edges_px] + [int(sh.x_one + 3 * sh.dec_x)]
        for a, b in zip(bounds, bounds[1:]):
            crop = g[top + 4 : bot - 3, a + 6 : b - 6]
            if crop.size == 0:
                sh.box_text.append("")
                continue
            big = np.kron(crop, np.ones((2, 2), np.uint8))
            sh.box_text.append(_ocr(np.pad(big, 20, constant_values=255), 7))
        foot = g[bot + 2 : min(H, bot + int(110 * s)), :]
        sh.footer = _ocr(foot, 6)
    return sh


NUM = re.compile(r"\d+(?:[.,]\d+)?")


def parse_rho(text: str) -> float | None:
    """Box text -> resistivity; '∞'-like marks (oo, 00, co) -> None."""
    t = text.replace(",", ".").replace(" ", "")
    if re.fullmatch(r"[oO0cC∞]{2,3}", t) or "∞" in t:
        return None
    m = NUM.search(t)
    return float(m.group()) if m else None


def strip_image(page, sh: Sheet) -> np.ndarray:
    """Band and footer of one sheet, with box edges marked, for reading by eye."""
    g = render(page)
    top, bot = sh.band
    s = g[top - 4 : min(g.shape[0], bot + 150)].copy()
    for x in sh.edges_px:
        s[:8, int(x) - 1 : int(x) + 2] = 0
    return s
