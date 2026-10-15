# GeoSigma

One place to bring together Israel's geophysical resistivity data (from GSI survey
reports) so it can be explored and compared. Phase 1 is a single-user local tool with
a web interface.

## Run

```
pip install -e '.[dev]'
python -m geosigma check      # validate all survey and dataset files
python -m geosigma build      # rebuild build/geosigma.sqlite
python -m geosigma serve      # http://127.0.0.1:8000
```

The viewer loads MapLibre, Plotly and OpenStreetMap tiles from the internet. Source
page previews use the report PDFs in `data/sources/pdf/` (committed, about 380 MB; Drive ids
are in `data/sources/manifest.json`).

## Layout

- `data/surveys/<id>/survey.yaml`: one survey: report metadata, documents, sites with
  coordinates as printed and their CRS.
- `data/surveys/<id>/datasets/*.json|yaml`: the extracted values. These files are the
  reviewed source of truth; the database is rebuilt from them.
- `geosigma/schema.py`: the unified schema (levels L1 apparent, L2 model, L3 derived;
  provenance, depth of investigation, confidence A-D, status draft/checked/approved).
- `geosigma/extract/`: extraction scripts, one per survey where automation pays off.
- `web/`: the viewer (plain JavaScript, no build step).

## Data rules

- Every value carries its source document, page, figure and extraction method.
- Values read from graphs are marked `digitised_auto` or `digitised_manual` with a
  reading error.
- Nothing is dropped: shallow data stay in the database even though the main interest
  is 500 m and deeper.
- Different methods are never merged into one value; the map shows the best model at
  each site and the site panel lists all of them.
- New extractions start as `draft` and show an "unreviewed" badge until checked.

## Reviewing

Open a site, compare the plot with the source page thumbnail under it, and press
**Checked**, **Approve** or **Reject** (with an optional note). The decision is saved
in the dataset's file under `data/surveys/`, so commit those files to keep it.
Rejected datasets drop out of the database on the next build. `GET /api/review`
lists the counts per survey, deepest data first. For the Geoelectric Atlas,
`python scripts/atlas_qa.py <dir>` draws the digitised readings over each plot page.

## Coordinates

- EPSG:2039 Israeli TM Grid (Afek App. B "NID TM").
- EPSG:28193 Old Israel Grid. Reports print northings without the 1,000,000 m in the
  north, or in km; `geosigma/crs.py` normalises them.
