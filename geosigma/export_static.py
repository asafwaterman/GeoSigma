"""Read-only web copy of the viewer: one HTML page plus two JSON files, no server.

Every API answer the viewer asks for is computed here ahead of time: values and
reliability at each depth step of the slider, coverage per depth, every dataset and
every line section. The source pages the datasets point at are rendered from the local
PDFs as greyscale JPEGs, packed a few pages per file (``src/``). The basemap is web/basemap.geojson, country outlines
clipped from Natural Earth 1:10m (public domain), since a hosted page may not load
map tiles.

Run: ``python -m geosigma export-static [out_dir]`` after ``build``.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import api
from .derived import on_ground_depths, reliability_at_depth, value_at_depth
from .schema import Dataset
from .store import DB_PATH, ROOT

DEPTHS = list(range(0, 3001, 25))  # the slider's steps
REL = {"reliable": "r", "unknown_doi": "u", "below_doi": "b", "beyond_model": "x", "no_model": "n"}
RANK = {"reliable": 0, "unknown_doi": 1, "below_doi": 2, "beyond_model": 3}
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"
CDN_SCRIPTS = ('<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>\n'
               '<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"></script>\n')
# With --libs the two libraries are copied next to the page (lib/), so a hosted site
# does not depend on a CDN carrying them.
LIB_FILES = ("maplibre-gl.js", "maplibre-gl.css", "plotly.min.js")
LOCAL_SCRIPTS = '<script src="lib/maplibre-gl.js"></script>\n<script src="lib/plotly.min.js"></script>\n'


def _sig(v):
    return None if v is None else float(f"{v:.3g}")


def core_data() -> tuple[dict, dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, survey, line, representation FROM dataset").fetchall()
    models = {r["id"]: Dataset.model_validate_json(con.execute("SELECT json FROM dataset WHERE id=?", (r["id"],)).fetchone()[0])
              for r in rows if r["representation"] == "model_1d"}
    lines = sorted({(r["survey"], r["line"]) for r in rows if r["representation"] == "model_1d" and r["line"]})
    con.close()

    sites = api.sites(depth=None)
    depth = []  # per feature: null, or [values per depth, reliability codes]
    for f in sites["features"]:
        ms = [models[i] for i in f["properties"]["datasets"] if i in models and on_ground_depths(models[i])]
        if not ms:
            depth.append(None)
            continue
        vals, codes = [], ""
        for z in DEPTHS:
            best = min(((RANK[reliability_at_depth(m, z)], k, m) for k, m in enumerate(ms)), key=lambda t: t[:2])
            vals.append(_sig(value_at_depth(best[2], z)))
            codes += REL[reliability_at_depth(best[2], z)]
        depth.append([vals, codes])
    coverage = {z: {} for z in DEPTHS}
    for m in models.values():
        for z in DEPTHS:
            c = coverage[z].setdefault(m.survey, {})
            rel = reliability_at_depth(m, z)
            c[rel] = c.get(rel, 0) + 1
    sections = {}
    for survey, line in lines:
        try:
            s = api.section(survey, line)
        except Exception:  # a line whose stations have no positions
            continue
        for st in s["stations"]:
            st["rho"] = [_sig(v) for v in st["rho"]]
            st.pop("reliability")
        sections[f"{survey}|{line}"] = s
    core = {"depths": DEPTHS, "surveys": api.surveys(), "sites": sites, "depth": depth,
            "coverage": coverage, "sections": sections}
    datasets = {r["id"]: api.dataset(r["id"]) for r in rows}
    return core, datasets


SHIM = """
<script>
(() => {
  const load = (f) => fetch(f).then((r) => { if (!r.ok) throw new Error(f + ": " + r.status); return r.json(); });
  const core = load("geosigma-core.json");
  let pages = {};
  core.then((c) => (pages = c.pages || {}));
  let datasets = null;
  const REL = { r: "reliable", u: "unknown_doi", b: "below_doi", x: "beyond_model", n: "no_model" };
  async function apiCall(path) {
    const c = await core;
    const [route, query] = path.split("?");
    const depth = query ? +new URLSearchParams(query).get("depth") : null;
    const k = depth == null ? -1 : c.depths.indexOf(Math.round(depth / 25) * 25);
    if (route === "/api/surveys") return c.surveys;
    if (route === "/api/coverage") return c.coverage[c.depths[k]];
    if (route === "/api/sites") {
      const features = c.sites.features.map((f, i) => {
        const d = c.depth[i];
        const props = { ...f.properties, rho_at_depth: d ? d[0][k] : null, reliability: d ? REL[d[1][k]] : "no_model" };
        return { ...f, properties: props };
      });
      return { type: "FeatureCollection", features };
    }
    let m = route.match(/^\\/api\\/datasets\\/(.+)$/);
    if (m) {
      datasets = datasets || load("geosigma-datasets.json");
      return (await datasets)[decodeURIComponent(m[1])];
    }
    m = route.match(/^\\/api\\/sections\\/([^/]+)\\/(.+)$/);
    if (m) return c.sections[m[1] + "|" + decodeURIComponent(m[2])];
    throw new Error("not in this copy: " + path);
  }
  const style = __STYLE__;
  const cs = getComputedStyle(document.documentElement), tok = (n) => cs.getPropertyValue(n).trim();
  style.layers[0].paint["background-color"] = tok("--sea") || "#dfe8f1";
  style.layers[1].paint["fill-color"] = tok("--land") || "#eceee9";
  style.layers[2].paint["line-color"] = tok("--borderline") || "#9aa196";
  const sourceImage = (survey, doc, page) => {
    const e = pages[survey + "|" + doc + "|" + page];
    return e && { src: e[0], x: e[1], y: e[2], w: e[3], h: e[4] };
  };
  // The PDFs are too large for this copy; downloads come from the GitHub repository.
  const pdfUrl = (survey, doc, filename) =>
    "https://github.com/asafwaterman/GeoSigma/raw/main/data/sources/pdf/" + encodeURIComponent(filename);
  window.GEOSIGMA_STATIC = { api: apiCall, style, sourceImage, pdfUrl };
})();
</script>
"""

THEME = """
:root { --border: var(--line); }
:root[data-theme="light"] { --bg: #f7f8fa; --panel: #ffffff; --text: #1d2430; --muted: #687385; --line: #dde2ea;
  --accent: #1f5fa8; --warn: #a86a00; --land: #eceee9; --sea: #dfe8f1; --borderline: #b9bfb3; }
:root { --land: #eceee9; --sea: #dfe8f1; --borderline: #b9bfb3; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --land: #262b31; --sea: #171b21;
  --borderline: #4a525d; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #14171c; --panel: #1c2027; --text: #e4e8ee; --muted: #9aa4b2; --line: #2e343e;
  --accent: #6aa8f0; --warn: #e0a640; --land: #262b31; --sea: #171b21; --borderline: #4a525d; color-scheme: dark; }
html, body { height: 100%; }
body { height: 100%; }
header, aside { padding-left: max(12px, env(safe-area-inset-left, 0px)); }
.copynote { font-size: 12px; color: var(--muted); }
"""


def page(core_style: dict, maplibre_css: str, local_libs: bool = False) -> str:
    web = ROOT / "web"
    idx = (web / "index.html").read_text()
    body = idx[idx.index("<body>") + 6:idx.index("</body>")]
    body = re.sub(r'<script src="/static/app.js"></script>', "", body)
    body = body.replace('<span class="sub">Resistivity of Israel, from GSI survey reports</span>',
                        '<span class="sub">Resistivity of Israel, from GSI survey reports</span>'
                        '<span class="copynote">Read-only copy.</span>')
    mlcss = maplibre_css
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>GeoSigma Viewer</title>\n'
            '<meta name="claude:viewport-fit-sides" content="cover">\n'
            f"<style>{mlcss}</style>\n<style>{(web / 'style.css').read_text()}{THEME}</style>\n</head>\n<body>\n"
            f"{body}\n"
            + (LOCAL_SCRIPTS if local_libs else CDN_SCRIPTS)
            + SHIM.replace("__STYLE__", json.dumps(core_style))
            + f"<script>{(web / 'app.js').read_text()}</script>\n</body>\n</html>\n")


def basemap_style() -> dict:
    gj = json.loads((ROOT / "web" / "basemap.geojson").read_text())
    return {"version": 8, "sources": {"land": {"type": "geojson", "data": gj,
                                                "attribution": "Natural Earth"}},
            "layers": [{"id": "sea", "type": "background", "paint": {"background-color": "#dfe8f1"}},
                       {"id": "land", "type": "fill", "source": "land", "paint": {"fill-color": "#eceee9"}},
                       {"id": "borders", "type": "line", "source": "land",
                        "paint": {"line-color": "#9aa196", "line-width": 0.8}}]}


PER_FILE = 4  # source pages per image file (a hosted copy may hold a few hundred files)


def source_pages(datasets: dict, out: Path) -> dict:
    """Render every page a dataset points at; return {"survey|doc|page": [file, x, y, w, h]}."""
    import io

    import pymupdf
    from PIL import Image

    from .sources import SOURCES_DIR

    con = sqlite3.connect(DB_PATH)
    files = {(r[0], r[1]): r[2] for r in con.execute("SELECT survey, id, filename FROM document")}
    con.close()
    want: dict[tuple, bool] = {}
    for d in datasets.values():
        for v in d.get("source_views") or []:
            k = (d["survey"], v["document"], v["page"])
            want[k] = want.get(k, False) or bool(v["zoom"])
    groups: dict[tuple, list] = {}
    for (survey, doc, page), zoom in sorted(want.items()):
        path = SOURCES_DIR / files.get((survey, doc), "-")
        if path.exists():
            groups.setdefault((survey, doc), []).append((page, zoom))
    (out / "src").mkdir(exist_ok=True)
    index, n = {}, 0
    for (survey, doc), pages in groups.items():
        with pymupdf.open(SOURCES_DIR / files[(survey, doc)]) as pdf:
            for i in range(0, len(pages), PER_FILE):
                ims = []
                for page, zoom in pages[i:i + PER_FILE]:
                    if not 1 <= page <= len(pdf):
                        continue
                    pix = pdf[page - 1].get_pixmap(dpi=130 if zoom else 100, colorspace=pymupdf.csGRAY)
                    ims.append((page, Image.frombytes("L", (pix.w, pix.h), pix.samples)))
                if not ims:
                    continue
                W, H = max(im.width for _, im in ims), sum(im.height for _, im in ims)
                sheet, y = Image.new("L", (W, H), 255), 0
                name = f"src/{n:03d}.jpg"
                for page, im in ims:
                    sheet.paste(im, (0, y))
                    index[f"{survey}|{doc}|{page}"] = [name, 0, round(y / H, 6), round(im.width / W, 6), round(im.height / H, 6)]
                    y += im.height
                buf = io.BytesIO()
                sheet.save(buf, "JPEG", quality=45, optimize=True)
                (out / name).write_bytes(buf.getvalue())
                n += 1
    return index


def export(out: Path, maplibre_css: Path | None = None, pages: bool = True, libs: Path | None = None) -> Path:
    """``maplibre_css``: a local copy of maplibre-gl.css, else it is downloaded (a hosted
    page may only load scripts from a CDN, so the stylesheet is inlined). ``libs``: a
    folder holding LIB_FILES, copied to ``out/lib/`` and loaded from there."""
    if libs:
        import shutil

        (out / "lib").mkdir(parents=True, exist_ok=True)
        for f in LIB_FILES:
            shutil.copyfile(libs / f, out / "lib" / f)
        maplibre_css = libs / "maplibre-gl.css"
    if maplibre_css:
        css = maplibre_css.read_text()
    else:
        import urllib.request

        css = urllib.request.urlopen(MAPLIBRE_CSS, timeout=30).read().decode()
    out.mkdir(parents=True, exist_ok=True)
    core, datasets = core_data()
    core["pages"] = source_pages(datasets, out) if pages else {}
    (out / "geosigma-core.json").write_text(json.dumps(core, separators=(",", ":")))
    (out / "geosigma-datasets.json").write_text(json.dumps(datasets, separators=(",", ":")))
    (out / "index.html").write_text(page(basemap_style(), css, local_libs=bool(libs)))
    return out
