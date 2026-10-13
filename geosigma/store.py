"""Load survey records from disk and build the SQLite database."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .crs import inside_israel, to_itm, to_wgs84
from .schema import Dataset, Status, Survey

ROOT = Path(__file__).resolve().parent.parent
SURVEYS_DIR = ROOT / "data" / "surveys"
DB_PATH = ROOT / "build" / "geosigma.sqlite"


@dataclass
class Catalogue:
    surveys: list[Survey] = field(default_factory=list)
    datasets: list[Dataset] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _load_yaml_or_json(path: Path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)


def load_catalogue(surveys_dir: Path = SURVEYS_DIR) -> Catalogue:
    """Read and validate every survey and dataset file.

    Validation errors are collected rather than raised so one bad file does not
    hide the rest; ``geosigma check`` prints them.
    """
    cat = Catalogue()
    for sdir in sorted(p for p in surveys_dir.iterdir() if p.is_dir()):
        sfile = sdir / "survey.yaml"
        if not sfile.exists():
            cat.problems.append(f"{sdir.name}: missing survey.yaml")
            continue
        try:
            survey = Survey.model_validate(_load_yaml_or_json(sfile))
        except Exception as e:  # noqa: BLE001 - report and continue
            cat.problems.append(f"{sfile}: {e}")
            continue
        cat.surveys.append(survey)
        site_ids = {s.id for s in survey.sites}
        doc_ids = {d.id for d in survey.documents}
        for site in survey.sites:
            lon, lat = to_wgs84(site.coords.x, site.coords.y, site.coords.crs)
            if not inside_israel(lon, lat):
                cat.problems.append(f"{survey.id}/{site.id}: outside Israel ({lon:.3f}, {lat:.3f})")
        for dfile in sorted((sdir / "datasets").glob("*.*")) if (sdir / "datasets").exists() else []:
            if dfile.suffix not in (".yaml", ".yml", ".json"):
                continue
            raw = _load_yaml_or_json(dfile)
            for item in raw if isinstance(raw, list) else [raw]:
                try:
                    ds = Dataset.model_validate(item)
                except Exception as e:  # noqa: BLE001
                    cat.problems.append(f"{dfile}: {e}")
                    continue
                if ds.survey != survey.id:
                    cat.problems.append(f"{ds.id}: survey field {ds.survey!r} != {survey.id!r}")
                if ds.site and ds.site not in site_ids:
                    cat.problems.append(f"{ds.id}: unknown site {ds.site!r}")
                if ds.provenance.document not in doc_ids:
                    cat.problems.append(f"{ds.id}: unknown document {ds.provenance.document!r}")
                cat.datasets.append(ds)
    ids = [d.id for d in cat.datasets]
    for dup in {i for i in ids if ids.count(i) > 1}:
        cat.problems.append(f"duplicate dataset id {dup}")
    return cat


SCHEMA_SQL = """
CREATE TABLE survey (
  id TEXT PRIMARY KEY, name TEXT, organisation TEXT, client TEXT, year INTEGER,
  methods TEXT, region TEXT, purpose TEXT, geometry TEXT, depth_reach TEXT,
  extraction_status TEXT, json TEXT
);
CREATE TABLE document (
  id TEXT, survey TEXT, title TEXT, filename TEXT, drive_id TEXT, pages INTEGER,
  language TEXT, scanned INTEGER, role TEXT, PRIMARY KEY (survey, id)
);
CREATE TABLE site (
  survey TEXT, id TEXT, name TEXT, line TEXT, lon REAL, lat REAL, itm_x REAL, itm_y REAL,
  orig_x REAL, orig_y REAL, orig_crs TEXT, coord_source TEXT, elevation_m REAL,
  PRIMARY KEY (survey, id)
);
CREATE TABLE dataset (
  id TEXT PRIMARY KEY, survey TEXT, site TEXT, line TEXT, method TEXT, level TEXT,
  representation TEXT, measured_on TEXT, depth_max_m REAL, doi_m REAL, doi_estimated INTEGER,
  confidence TEXT, status TEXT, model_type TEXT, interface_depth_m REAL, summary TEXT,
  document TEXT, pages TEXT, extraction_method TEXT, json TEXT
);
CREATE INDEX dataset_site ON dataset (survey, site);
"""


def build_database(cat: Catalogue, db_path: Path = DB_PATH, include_drafts: bool = True) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_SQL)
    for s in cat.surveys:
        con.execute(
            "INSERT INTO survey VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.id, s.name, s.organisation, s.client, s.year, ",".join(m.value for m in s.methods),
             s.region, s.purpose, s.geometry, s.depth_reach, s.extraction_status,
             s.model_dump_json(exclude={"sites"})),
        )
        for d in s.documents:
            con.execute(
                "INSERT INTO document VALUES (?,?,?,?,?,?,?,?,?)",
                (d.id, s.id, d.title, d.filename, d.drive_id, d.pages, ",".join(d.language), int(d.scanned), d.role),
            )
        for site in s.sites:
            c = site.coords
            lon, lat = to_wgs84(c.x, c.y, c.crs)
            ix, iy = to_itm(c.x, c.y, c.crs)
            con.execute(
                "INSERT INTO site VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s.id, site.id, site.name, site.line, lon, lat, ix, iy, c.x, c.y, c.crs, c.source, site.elevation_m),
            )
    allowed = {Status.approved, Status.checked} | ({Status.draft} if include_drafts else set())
    for ds in cat.datasets:
        if ds.status not in allowed:
            continue
        p = ds.provenance
        con.execute(
            "INSERT INTO dataset VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ds.id, ds.survey, ds.site, ds.line, ds.method.value, ds.level.value, ds.representation.value,
             ds.measured_on, ds.depth_max_m, ds.doi_m, int(ds.doi_estimated), ds.confidence.value,
             ds.status.value, ds.model_type, ds.interface_depth_m, ds.summary, p.document,
             ",".join(map(str, p.pages)), p.method.value, ds.model_dump_json()),
        )
    con.commit()
    con.close()
    return db_path
