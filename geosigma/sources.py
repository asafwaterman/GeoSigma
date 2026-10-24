"""Where on the source page each dataset was read: page, region and marks.

``views(ds)`` returns one entry per page the viewer should show for a dataset:
``{document, page, aspect, region, marks, zoom, caption}``. ``region`` is the part of the
page the values come from, as page fractions [x0, y0, x1, y1] (None for the whole page);
``marks`` are points on the page, as fractions, each tied to a site, so the viewer can
ring the selected station; ``zoom`` asks the viewer to frame the selected site's mark.
Regions and marks come from the extraction files (sheet quadrants, embedded plot
rectangles, pixel positions at 200 dpi), so they point at what was actually read.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .store import ROOT, SURVEYS_DIR

SOURCES_DIR = ROOT / "data" / "sources" / "pdf"  # the original reports

QUAD = {"TL": ([0, 0, 0.5, 0.5], "upper-left"), "TR": ([0.5, 0, 1, 0.5], "upper-right"),
        "BL": ([0, 0.5, 0.5, 1], "lower-left"), "BR": ([0.5, 0.5, 1, 1], "lower-right")}
# Figure 9 of Klang (1970), page 33: x of each sounding's column, as a page fraction
FIG9_X = {k: round(v / 1986, 4) for k, v in {
    "9": 135, "6": 232, "5": 262, "4": 287, "2": 352, "1": 406, "7": 437, "8": 443, "21": 514, "10": 594,
    "22": 697, "11": 765, "12": 931, "13": 1032, "14": 1166, "15": 1277, "16": 1421, "19": 1537, "17": 1745,
    "20": 1862}.items()}
# The author's interpreted model on field sheets of one layout: the CALC. RES. row, as
# page (or sheet) fractions [x0, y0, x1, y1]. Checked against every sheet of the survey.
SHEET_BAND = {
    "paparo-1969-southern-arava": [0.02, 0.845, 0.98, 0.93],
    "paparo-1970-shekhem": [0.0, 0.85, 0.98, 0.95],
    "paparo-1977-revadim": [0.0, 0.855, 0.98, 0.925],
    "klang-1970-mt-timna-ramon": [0.025, 0.835, 0.96, 0.92],
    "rotstein-1977-yizreel-harod": [0.02, 0.845, 0.98, 0.895],
    "klang-1974-mt-south-netanya": [0.02, 0.8, 0.98, 0.885],
}
SHEET_MODEL = (" The author's interpreted model is the boxed CALC. RES. row: one resistivity per layer inside the "
               "boxes; the box edges, read on the AB/2 axis, are the layer boundaries. The curve above it is the "
               "measured apparent resistivity, not the model.")
MT_MODEL = (" The author's interpreted model is the boxed CALC. RES. row: one resistivity per layer inside the boxes, "
            "the boundary depths written under the lines between them. The curve above it is the measured apparent "
            "resistivity, not the model.")
# Rotstein (1979) Figures 2 and 3: the inverted model is the small hatched inset of each panel.
ROT_INSET = {"KFM": [0.19, 0.055, 0.245, 0.135], "BTN": [0.57, 0.135, 0.62, 0.235], "BCH": [0.13, 0.6, 0.19, 0.7],
             "RAL": [0.585, 0.515, 0.62, 0.6], "MRG": [0.11, 0.065, 0.17, 0.16], "DAZ": [0.59, 0.155, 0.635, 0.235],
             "KAR": [0.115, 0.6, 0.17, 0.69], "JOU": [0.62, 0.6, 0.66, 0.69]}
L1 = {"sounding_curve", "profile", "map_grid"}  # measured data: the report gives no model for these
PX_DPI = 200  # pixel positions in the extraction files are at 200 dpi


@lru_cache(maxsize=None)
def _extraction(survey: str, name: str):
    p = SURVEYS_DIR / survey / "extraction" / name
    return json.loads(p.read_text()) if p.exists() else None


@lru_cache(maxsize=4096)
def page_size(filename: str, page: int) -> tuple[float, float] | None:
    """Page width and height in points, or None without the PDF."""
    path = SOURCES_DIR / filename
    if not path.exists():
        return None
    import pymupdf

    with pymupdf.open(path) as doc:
        if not 1 <= page <= len(doc):
            return None
        r = doc[page - 1].rect
        return r.width, r.height


def _band(survey: str, page: int, quad: str | None = None):
    """Per-sheet CALC. RES. row read from the scans (extraction/model_boxes.json), else the survey's layout."""
    per = (_extraction(survey, "model_boxes.json") or {}).get("boxes", {})
    key = f"{page}:{quad}" if quad else str(page)
    return per[key] if key in per else SHEET_BAND.get(survey)


def _rotate(survey: str, page: int) -> int:
    return int(((_extraction(survey, "model_boxes.json") or {}).get("rotate") or {}).get(str(page), 0))


def _sub(rect, box):
    """``box`` given as fractions of ``rect`` (both page fractions), as page fractions."""
    x0, y0, x1, y1 = rect
    return [round(x0 + box[0] * (x1 - x0), 4), round(y0 + box[1] * (y1 - y0), 4),
            round(x0 + box[2] * (x1 - x0), 4), round(y0 + box[3] * (y1 - y0), 4)]


@lru_cache(maxsize=4096)
def _image_rects(filename: str, page: int) -> list:
    import pymupdf

    with pymupdf.open(SOURCES_DIR / filename) as doc:
        pg = doc[page - 1]
        out = []
        for img in pg.get_images(full=True):
            rs = pg.get_image_rects(img[0])
            r = rs[0] if rs else None
            out.append(None if r is None else [r.x0 / pg.rect.width, r.y0 / pg.rect.height,
                                               r.x1 / pg.rect.width, r.y1 / pg.rect.height])
        return out


def _frac(size, x, y):
    w, h = size
    s = PX_DPI / 72
    return round(x / (w * s), 4), round(y / (h * s), 4)


def _what(prov: dict) -> str:
    parts = [(prov.get("figure") or "").split(";")[0].strip() or None, ("values from the " + prov["table"]) if prov.get("table") else None]
    return "; ".join(p for p in parts if p)


def views(ds: dict, filename: str | None) -> list[dict]:
    prov = ds.get("provenance") or {}
    pages = prov.get("pages") or []
    if not pages:
        return []
    survey, doc = ds["survey"], prov.get("document")
    sizes = {p: page_size(filename, p) if filename else None for p in pages}

    def view(page, caption, region=None, marks=None, zoom=False, boxes=None):
        s = sizes.get(page) or (page_size(filename, page) if filename else None)
        return {"document": doc, "page": page, "aspect": round(s[1] / s[0], 4) if s else None,
                "region": region, "marks": marks or [], "zoom": zoom, "caption": caption, "boxes": boxes or [],
                "rotate": _rotate(survey, page)}

    what = _what(prov)
    first = pages[0]

    # Northern Arava Vol. 2: four sheets per page; the quadrant is in the notes.
    m = re.search(r"Sheet at page (\d+) (TL|TR|BL|BR)", ds.get("notes") or "")
    if m:
        region, word = QUAD[m.group(2)]
        band = _band(survey, first, m.group(2))
        return [view(first, f"Page {first}, {word} sheet: {what}." + SHEET_MODEL, region,
                     boxes=[_sub(region, band)] if band else None)]

    # Afek Appendix C: two embedded plots per page.
    if survey == "afek-2013-csamt" and filename and sizes.get(first):
        sm = re.match(r"^(.+)-(\d+)(?:-(E[xy]))?$", ds["site"])
        line, st, comp = sm.groups() if sm else (ds["site"], "", None)
        for e in _extraction(survey, "plot_map.json") or []:
            if e["page"] == first and e["line"] == line and str(e["station"]) == st and (comp is None or e.get("comp") == comp):
                i = int(e["file"].rsplit("_", 1)[1].split(".")[0])
                rects = _image_rects(filename, first)
                if i < len(rects) and rects[i]:
                    return [view(first, f"Page {first}, plot for line {line}, station {st}. The author's "
                                        "interpreted model is the boxed right-hand panel (smooth 1D inversion, "
                                        "resistivity against depth). The left panel is the measured sounding "
                                        "curve with the model's fit", rects[i], boxes=[_sub(rects[i], [0.64, 0.0, 0.99, 0.97])])]

    # Rotstein (1979) MT: the model is the hatched inset of the station's panel.
    if survey == "rotstein-1979-mt-northern-israel":
        name = next((k for k in ROT_INSET if k in (prov.get("figure") or "")), None)
        if name:
            b = ROT_INSET[name]
            region = [max(0, b[0] - 0.1), max(0, b[1] - 0.06), min(1, b[2] + 0.3), min(1, b[3] + 0.12)]
            return [view(first, f"Page {first}, {prov['figure']}. The author's inverted model is the boxed hatched "
                                "inset (resistivity against depth in km); the points and curves around it are the "
                                "measured apparent resistivity and phase with the model's fit", region, boxes=[b])]

    # Southern Arava iso-resistivity maps: ring the sounding on each map it appears on.
    if survey == "paparo-1969-southern-arava" and ds["site"].startswith("map-") and filename:
        from .extract.arava_maps import SLICES, norm_label

        mp = _extraction(survey, "map_points.json") or {"pages": {}}
        out = []
        for p in sorted(mp["pages"], key=int):
            s = page_size(filename, int(p))
            pts = [q for q in mp["pages"][p]["points"]
                   if q.get("label") is not None and f"map-{norm_label(q['label'])}" == ds["site"]]
            if not pts or not s:
                continue
            ref, depth = SLICES[int(p)]
            where = f"{depth} m below sea level" if ref == "below_sea_level" else f"{depth} m depth"
            marks = [{"site": ds["site"], "x": fx, "y": fy} for fx, fy in (_frac(s, q["x"], q["y"]) for q in pts)]
            vals = ", ".join(f"{q['value']:g} ohm.cm" for q in pts if q.get("value") is not None) or "no value printed"
            out.append(view(int(p), f"Page {p}, the author's iso-resistivity map titled {where}: the value printed "
                                    f"at the ringed sounding ({vals}). These map values follow the measured "
                                    "apparent-resistivity curve, not the layered model, so they are shown as "
                                    "measured data", marks=marks, zoom=True))
        if out:
            return out

    # Yizreel-Harod roving-dipole maps: one map per source, ring the selected station.
    if ds.get("representation") == "map_grid" and filename and sizes.get(first):
        rd = _extraction(survey, "roving_dipole.json") or {"pages": {}}
        page = rd["pages"].get(str(first))
        if page:
            marks = [{"site": f"RD-{q['station']}", "x": fx, "y": fy}
                     for q in page["points"] for fx, fy in [_frac(sizes[first], q["x"], q["y"])]]
            return [view(first, f"Page {first}: {what}. The value printed beside the ringed station is "
                                "the one shown here", marks=marks, zoom=True)]

    # Geoelectric Atlas: several plot panels per page; frame the panel, mark each reading.
    if ds.get("representation") == "profile" and survey == "paparo-1982-geoelectric-atlas" and sizes.get(first):
        pr = (_extraction(survey, "plot_readings.json") or {}).get(str(first)) or []
        from .extract.atlas_build import STYLE_WORD

        fig = prov.get("figure") or ""
        style = next((k for k, w in STYLE_WORD.items() if fig.endswith(f", {w} curve")), None)
        for sr in pr:
            if sr["spacing"] == ds.get("spacing_m") and (style is None or sr["style"] == style):
                px = sr["pixels"]
                xs, ys = [p[0] for p in px], [p[1] for p in px] + [sr["panel_axis_y"]]
                x0, y0 = _frac(sizes[first], min(xs) - 230, min(ys) - 80)
                x1, y1 = _frac(sizes[first], max(xs) + 60, max(ys) + 40)
                marks = [{"site": q["site"], "x": fx, "y": fy}
                         for q, (x, y) in zip(ds["profile"], px) for fx, fy in [_frac(sizes[first], x, y)]]
                out = [view(first, f"Page {first}, plot panel for a = {sr['spacing']} m"
                                   + (f" ({STYLE_WORD[style]} curve)" if style else "") + f": {what}",
                            [max(0, x0), max(0, y0), min(1, x1), min(1, y1)], marks)]
                out += [view(p, f"Page {p}: location map of the line") for p in pages[1:]]
                return out

    # Klang 1970 Afiq-Lot: the author's model is the CALC. RES. band of the sheet and the
    # sounding's column on Figure 9 (page 33).
    if survey == "klang-1970-mt-general":
        no = ds["site"].split("-", 1)[1]
        out = [view(first, f"Page {first}, M.T.P. No. {no} field sheet. The author's interpreted model is the boxed "
                           "CALC. RES. row: resistivity of each layer in ohm.cm inside the boxes, the depth of each "
                           "boundary (m below ground) under the lines between them. The curve above is the measured "
                           "apparent resistivity", boxes=[[0.025, 0.83, 0.96, 0.91]])]
        if no in FIG9_X:
            x = FIG9_X[no]
            out.append(view(33, f"Page 33, Figure 9 (interpreted resistivity, traverse A-A'): the column under "
                                f"sounding {no}, the same model drawn against sea level, in ohm.cm",
                            [max(0, x - 0.07), 0.08, min(1, x + 0.07), 0.75],
                            marks=[{"site": ds["site"], "x": x, "y": 0.123}]))
        return out

    # Models typed from printed tables and printouts (extract.printed_tables): box the site's rows.
    tb = (_extraction(survey, "table_boxes.json") or {}).get(ds["id"])
    if tb:
        b = tb["box"]
        region = [max(0, b[0] - 0.05), max(0, b[1] - 0.12), min(1, b[2] + 0.05), min(1, b[3] + 0.06)]
        src = prov.get("table") or prov.get("figure") or "the printed table"
        cap = (f"Page {tb['page']}, {src}. The author's interpreted model is the boxed rows: the depth interval "
               "(or thickness) and resistivity of each layer, as printed")
        if tb.get("caption"):
            cap = f"Page {tb['page']}, {src}. {tb['caption']}"
        elif ds.get("representation") == "interface_depth":
            cap += "; the interface depth is derived from it"
        out = [view(tb["page"], cap, region, boxes=[b])]
        figs = [f.strip() for f in (prov.get("figure") or "").split(";")]
        for i, p in enumerate(pages[1:], 1):
            out.append(view(p, f"Page {p}: {figs[i] if i < len(figs) and figs[i] else 'also cited for these values'}"))
        return out

    # Default: a whole field sheet or table page, then any figure it was checked against.
    figs = [f.strip() for f in (prov.get("figure") or "").split(";")]
    boxes, rep = None, ds.get("representation")
    if rep in L1:
        what += (". This is measured data (apparent resistivity), read from the plot; the report gives no "
                 "interpreted model for it")
    elif (prov.get("figure") or "").startswith("VES sheet") or "RES. band" in (prov.get("table") or ""):
        band = _band(survey, first)
        boxes = [band] if band else None
        what += "." + (MT_MODEL if ds.get("method") == "MT" else SHEET_MODEL) if band else "."
    elif survey == "goldman-2000-tdem-coastal":
        boxes = [[0.04, 0.33, 0.98, 0.52]]
        what += (". The author's inverted model is the boxed table: resistivity and thickness of each layer "
                 "(PROTEM 1D inversion)" + ("; the interface depth is derived from it" if rep == "interface_depth" else ""))
    elif survey == "rotstein-1979-carmel" and rep == "model_1d":
        boxes = [[0.62, 0.3, 0.78, 0.86]]
        what += ". The author's interpreted models A and B are the boxed table drawn on the sheet"
    out = [view(first, f"Page {first}: {what}" if what else f"Page {first}", boxes=boxes)]
    for i, p in enumerate(pages[1:], 1):
        label = figs[i] if i < len(figs) and figs[i] else "also cited for these values"
        out.append(view(p, f"Page {p}: {label} (used to check the reading)" if i < len(figs) else f"Page {p}: {label}"))
    return out
