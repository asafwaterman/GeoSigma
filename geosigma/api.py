"""FastAPI backend: the only read path for the web interface."""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .derived import reliability_at_depth, value_at_depth
from .schema import Dataset
from .store import DB_PATH, ROOT

WEB_DIR = ROOT / "web"
SOURCES_DIR = ROOT / "data" / "sources" / "pdf"  # local PDFs, not committed

app = FastAPI(title="GeoSigma")


def _db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, "Database not built; run `python -m geosigma build`")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@app.get("/api/surveys")
def surveys():
    with _db() as con:
        rows = con.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM site WHERE survey=s.id) AS n_sites,"
            " (SELECT COUNT(*) FROM dataset WHERE survey=s.id) AS n_datasets FROM survey s ORDER BY year"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = json.loads(d.pop("json"))
        out.append(d)
    return out


@app.get("/api/sites")
def sites(
    method: Optional[str] = None,
    depth: Optional[float] = Query(None, description="Depth below ground (m) to evaluate models at"),
):
    """GeoJSON of all sites with their datasets summarised; with ``depth``, each site
    also carries the value and reliability of its best model at that depth."""
    with _db() as con:
        site_rows = con.execute("SELECT * FROM site").fetchall()
        ds_rows = con.execute("SELECT id, survey, site, method, level, representation, json FROM dataset").fetchall()
        survey_years = {r["id"]: r["year"] for r in con.execute("SELECT id, year FROM survey")}
    by_site: dict[tuple, list] = {}
    for r in ds_rows:
        by_site.setdefault((r["survey"], r["site"]), []).append(r)
    feats = []
    for s in site_rows:
        dss = by_site.get((s["survey"], s["id"]), [])
        methods = sorted({r["method"] for r in dss}) or []
        if method and method not in methods:
            continue
        props = {
            "survey": s["survey"], "site": s["id"], "name": s["name"], "line": s["line"],
            "year": survey_years.get(s["survey"]), "methods": methods,
            "datasets": [r["id"] for r in dss],
            "levels": sorted({r["level"] for r in dss}),
            "has_model": any(r["representation"] == "model_1d" for r in dss),
            "orig": f'{s["orig_x"]:.0f}, {s["orig_y"]:.0f} ({s["orig_crs"]})',
        }
        if depth is not None:
            best = None
            for r in dss:
                if r["representation"] != "model_1d":
                    continue
                ds = Dataset.model_validate_json(r["json"])
                v = value_at_depth(ds, depth)
                rel = reliability_at_depth(ds, depth)
                rank = {"reliable": 0, "unknown_doi": 1, "below_doi": 2, "beyond_model": 3}[rel]
                if best is None or rank < best[0]:
                    best = (rank, v, rel, ds.id)
            if best:
                props.update(rho_at_depth=best[1], reliability=best[2], depth_dataset=best[3])
            else:
                props.update(rho_at_depth=None, reliability="no_model")
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": feats}


@app.get("/api/datasets/{dataset_id}")
def dataset(dataset_id: str):
    with _db() as con:
        r = con.execute("SELECT json FROM dataset WHERE id=?", (dataset_id,)).fetchone()
        if not r:
            raise HTTPException(404, "unknown dataset")
        ds = json.loads(r["json"])
        doc = con.execute(
            "SELECT * FROM document WHERE survey=? AND id=?", (ds["survey"], ds["provenance"]["document"])
        ).fetchone()
    ds["document_info"] = dict(doc) if doc else None
    return ds


@app.get("/api/coverage")
def coverage(depth: float):
    """Count of 1D models per reliability class at a depth, per survey."""
    with _db() as con:
        rows = con.execute("SELECT survey, json FROM dataset WHERE representation='model_1d'").fetchall()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        ds = Dataset.model_validate_json(r["json"])
        rel = reliability_at_depth(ds, depth)
        out.setdefault(r["survey"], {}).setdefault(rel, 0)
        out[r["survey"]][rel] += 1
    return out


@app.get("/api/sections/{survey}/{line}")
def section(survey: str, line: str, dz: float = 25, zmax: Optional[float] = None):
    """Stations of one line, in order along it, with their 1D models sampled on a
    common depth grid; for a quick (distance, depth) section."""
    import math

    with _db() as con:
        sites = con.execute(
            "SELECT id, itm_x, itm_y FROM site WHERE survey=? AND line=?", (survey, line)
        ).fetchall()
        rows = con.execute(
            "SELECT site, json FROM dataset WHERE survey=? AND line=? AND representation='model_1d'",
            (survey, line),
        ).fetchall()
    if not sites:
        raise HTTPException(404, "unknown line")
    models = {r["site"]: Dataset.model_validate_json(r["json"]) for r in rows}
    pos = {s["id"]: (s["itm_x"], s["itm_y"]) for s in sites}
    # order stations along the line's longest axis
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    axis = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
    order = sorted((sid for sid in models if sid in pos), key=lambda sid: pos[sid][axis])
    if not order:
        raise HTTPException(404, "no models on this line")
    x0, y0 = pos[order[0]]
    deepest = max((m.depth_max_m or 0) for m in models.values()) or 1000
    zmax = zmax or deepest
    depths = [i * dz for i in range(int(zmax / dz) + 1)]
    out = []
    for sid in order:
        m = models[sid]
        vals = [value_at_depth(m, z) for z in depths]
        out.append({
            "site": sid, "dataset": m.id,
            "distance_m": round(math.hypot(pos[sid][0] - x0, pos[sid][1] - y0)),
            "rho": vals, "reliability": [reliability_at_depth(m, z) for z in depths],
        })
    return {"survey": survey, "line": line, "depths": depths, "stations": out}


@lru_cache(maxsize=256)
def _render_page(path: str, page: int, dpi: int) -> bytes:
    import pymupdf

    with pymupdf.open(path) as doc:
        if not 1 <= page <= len(doc):
            raise HTTPException(404, "page out of range")
        return doc[page - 1].get_pixmap(dpi=dpi).tobytes("png")


@app.get("/api/source/{survey}/{document}/page/{page}.png")
def source_page(survey: str, document: str, page: int, dpi: int = 100):
    """Render a page of the original report, for provenance checks."""
    with _db() as con:
        doc = con.execute("SELECT filename FROM document WHERE survey=? AND id=?", (survey, document)).fetchone()
    if not doc:
        raise HTTPException(404, "unknown document")
    path = SOURCES_DIR / doc["filename"]
    if not path.exists():
        raise HTTPException(404, f"source PDF not available locally: {doc['filename']}")
    return Response(_render_page(str(path), page, min(dpi, 200)), media_type="image/png")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
