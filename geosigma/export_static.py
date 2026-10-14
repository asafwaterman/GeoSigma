"""Read-only web copy of the viewer: one HTML page plus two JSON files, no server.

Every API answer the viewer asks for is computed here ahead of time: values and
reliability at each depth step of the slider, coverage per depth, every dataset and
every line section. Source-page images and review are left out (they need the local
PDFs and the dataset files). The basemap is web/basemap.geojson, country outlines
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
from .derived import reliability_at_depth, value_at_depth
from .schema import Dataset
from .store import DB_PATH, ROOT

DEPTHS = list(range(0, 3001, 25))  # the slider's steps
REL = {"reliable": "r", "unknown_doi": "u", "below_doi": "b", "beyond_model": "x", "no_model": "n"}
RANK = {"reliable": 0, "unknown_doi": 1, "below_doi": 2, "beyond_model": 3}
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"


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
        ms = [models[i] for i in f["properties"]["datasets"] if i in models]
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
  window.GEOSIGMA_STATIC = { api: apiCall, style };
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


def page(core_style: dict, maplibre_css: str) -> str:
    web = ROOT / "web"
    idx = (web / "index.html").read_text()
    body = idx[idx.index("<body>") + 6:idx.index("</body>")]
    body = re.sub(r'<script src="/static/app.js"></script>', "", body)
    body = body.replace('<span class="sub">Resistivity of Israel, from GSI survey reports</span>',
                        '<span class="sub">Resistivity of Israel, from GSI survey reports</span>'
                        '<span class="copynote">Read-only copy. Drafts, not yet reviewed.</span>')
    mlcss = maplibre_css
    return ("<title>GeoSigma Viewer</title>\n"
            '<meta name="claude:viewport-fit-sides" content="cover">\n'
            f"<style>{mlcss}</style>\n<style>{(web / 'style.css').read_text()}{THEME}</style>\n"
            f"{body}\n"
            '<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>\n'
            '<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"></script>\n'
            + SHIM.replace("__STYLE__", json.dumps(core_style))
            + f"<script>{(web / 'app.js').read_text()}</script>\n")


def basemap_style() -> dict:
    gj = json.loads((ROOT / "web" / "basemap.geojson").read_text())
    return {"version": 8, "sources": {"land": {"type": "geojson", "data": gj,
                                                "attribution": "Natural Earth"}},
            "layers": [{"id": "sea", "type": "background", "paint": {"background-color": "#dfe8f1"}},
                       {"id": "land", "type": "fill", "source": "land", "paint": {"fill-color": "#eceee9"}},
                       {"id": "borders", "type": "line", "source": "land",
                        "paint": {"line-color": "#9aa196", "line-width": 0.8}}]}


def export(out: Path, maplibre_css: Path | None = None) -> Path:
    """``maplibre_css``: a local copy of maplibre-gl.css, else it is downloaded (a hosted
    page may only load scripts from a CDN, so the stylesheet is inlined)."""
    if maplibre_css:
        css = maplibre_css.read_text()
    else:
        import urllib.request

        css = urllib.request.urlopen(MAPLIBRE_CSS, timeout=30).read().decode()
    out.mkdir(parents=True, exist_ok=True)
    core, datasets = core_data()
    (out / "geosigma-core.json").write_text(json.dumps(core, separators=(",", ":")))
    (out / "geosigma-datasets.json").write_text(json.dumps(datasets, separators=(",", ":")))
    (out / "index.html").write_text(page(basemap_style(), css))
    return out
