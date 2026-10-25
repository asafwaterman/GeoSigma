import math

import pytest

from geosigma.crs import ITM, OLD_GRID, inside_israel, normalise_old_grid, to_wgs84
from geosigma.derived import reliability_at_depth, value_at_depth
from geosigma.schema import Dataset
from geosigma.store import load_catalogue


def _ds(**kw):
    base = dict(id="t", survey="s", method="CSAMT", level="L2", representation="model_1d",
                provenance={"document": "d", "method": "manual"})
    base.update(kw)
    return Dataset.model_validate(base)


def test_old_grid_false_northing_and_km():
    # northern Israel: printed without the 1,000,000 m; Negev: printed as about 880-1000 km
    assert normalise_old_grid(180.5, 165.2) == pytest.approx((180500, 1165200))
    assert normalise_old_grid(180500, 165200) == (180500, 1165200)
    assert normalise_old_grid(145000, 885000) == (145000, 885000)


def test_itm_point_in_golan():
    lon, lat = to_wgs84(265256, 740112, ITM)
    assert inside_israel(lon, lat) and 35.6 < lon < 35.8 and 32.7 < lat < 32.8


def test_old_and_new_grid_agree():
    # ITM is about the old grid (printed) + (50 km, 500 km) in central Israel
    a = to_wgs84(170000, 150000, OLD_GRID)
    b = to_wgs84(220000, 650000, ITM)
    assert math.dist(a, b) < 0.003


def test_smooth_model_log_interpolation():
    ds = _ds(model_type="smooth", samples=[{"depth_m": 0, "rho_ohmm": 10}, {"depth_m": 100, "rho_ohmm": 1000}])
    assert value_at_depth(ds, 50) == pytest.approx(100)
    assert value_at_depth(ds, 150) is None
    assert reliability_at_depth(ds, 150) == "beyond_model"
    assert reliability_at_depth(ds, 50) == "unknown_doi"


def test_layered_model_and_doi():
    ds = _ds(model_type="layered", doi_m=300,
             layers=[{"top_m": 0, "bottom_m": 200, "rho_ohmm": 5}, {"top_m": 200, "rho_ohmm": 50}])
    assert value_at_depth(ds, 199) == 5 and value_at_depth(ds, 1000) == 50
    assert reliability_at_depth(ds, 250) == "reliable"
    assert reliability_at_depth(ds, 400) == "below_doi"


def test_validation_rules():
    with pytest.raises(ValueError):
        _ds()  # model without layers or samples
    with pytest.raises(ValueError):
        _ds(level="L1", samples=[{"depth_m": 0, "rho_ohmm": 1}])
    with pytest.raises(ValueError):
        _ds(samples=[{"depth_m": 10, "rho_ohmm": 1}, {"depth_m": 5, "rho_ohmm": 1}])


def test_catalogue_is_clean():
    cat = load_catalogue()
    assert cat.problems == []
    assert len(cat.surveys) >= 1


def test_profile_dataset_rules():
    import pytest
    from geosigma.schema import Dataset

    base = dict(id="p", survey="s", line="L1", method="PROFILING", representation="profile",
                provenance={"document": "main", "method": "digitised_auto"})
    ds = Dataset.model_validate({**base, "level": "L1", "array": "Wenner", "spacing_m": 50,
                                 "profile": [{"station": 1.5, "rho_a": 34.0}]})
    assert ds.profile[0].rho_a == 34.0
    with pytest.raises(ValueError):
        Dataset.model_validate({**base, "level": "L1", "profile": []})
    with pytest.raises(ValueError):
        Dataset.model_validate({**base, "level": "L2", "profile": [{"station": 1, "rho_a": 5}]})



# --- Guards from the 2026-10-15 data verification (docs/verification-2026-10.md) ---

# Unit printed in each source, with where it is stated. Surveys printed in ohm.cm must
# say on every dataset that the values were divided by 100.
OHM_CM_SURVEYS = {
    "klang-1970-mt-general": "sheet axis 'APPARENT RESISTIVITY ohm.cm' and Fig. 9 legend",
    "klang-1970-mt-timna-ramon": "CALC. RES. band labelled ohm.cm",
    "paparo-1969-southern-arava": "map legend: contour interval 1000 ohm.cm",
    "paparo-1970-shekhem": "report section 2.0 gives formation values in ohm.cm",
    "gvirtzman-1972-mt-heletz-ashqelon": "Table 1 header 'Resistivity, ohm-cm'; Table 2 ranges in ohm-cm",
}


def test_ohm_cm_sources_are_converted():
    for ds in load_catalogue().datasets:
        if ds.survey in OHM_CM_SURVEYS and ds.representation.value not in ("qualitative",):
            assert "divided by 100" in (ds.provenance.notes or ""), ds.id


def test_resistivities_physically_plausible_or_flagged():
    # below 0.1 ohm.m is lower than brine-saturated rock; above 1e5 is beyond dry rock
    for ds in load_catalogue().datasets:
        vals = [l.rho_ohmm for l in ds.layers if l.rho_ohmm is not None] + [s.rho_ohmm for s in ds.samples]
        vals += [c.rho_a for c in ds.curve] + [p.rho_a for p in ds.profile]
        if vals and (min(vals) < 0.1 or max(vals) > 1e5):
            assert ds.confidence.value == "C" and "artefact" in (ds.notes or ""), ds.id


def test_sea_level_models_stay_off_the_depth_axis():
    ds = _ds(depth_ref="below_sea_level", samples=[{"depth_m": 25, "rho_ohmm": 10}])
    assert value_at_depth(ds, 25) is None


def test_southern_arava_map_values_are_measured_data():
    # the iso-resistivity maps follow the apparent-resistivity curve, not the layered models
    for ds in load_catalogue().datasets:
        if ds.id.startswith("paparo-1969-southern-arava-maps-"):
            assert ds.level.value == "L1" and ds.representation.value != "model_1d", ds.id


def test_layers_are_contiguous_from_the_surface():
    for ds in load_catalogue().datasets:
        if ds.layers:
            assert ds.layers[0].top_m == 0, ds.id
            for a, b in zip(ds.layers, ds.layers[1:]):
                assert a.bottom_m == b.top_m and a.bottom_m > a.top_m, ds.id


# --- Guards from the 2026-10 Drive additions (TDEM reports and source-only entries) ---

NEW_TDEM_COUNTS = {
    ("goldman-1987-tdem-feasibility", "model_1d"): 28,
    ("goldman-1990-tdem-feasibility-stage-b", "model_1d"): 59,
    ("goldman-1999-tdem-arava-reservoirs", "model_1d"): 24,
    ("bartov-1998-tdem-northern-arava", "interface_depth"): 137,
    ("goldman-1998-tdem-coastal-monitoring", "model_1d"): 54,
    ("goldman-1998-tdem-coastal-monitoring", "interface_depth"): 81,
    ("rabinovich-1993-tdem-coastal-interface", "model_1d"): 64,
    ("rabinovich-1993-tdem-coastal-interface", "interface_depth"): 86,
    ("goldman-1995-tdem-coastal-interface", "model_1d"): 58,
    ("goldman-1995-tdem-coastal-interface", "interface_depth"): 68,
    ("goldman-1996-tdem-ashqelon", "model_1d"): 2,
    ("goldman-2001-tdem-nahal-hever-south", "model_1d"): 5,
}

# half-space of each model as printed in the source (checked twice by eye)
NEW_TDEM_HALF_SPACES = {
    "rabinovich1993-HS239-layered": (93.21, 0.894),
    "goldman1995-HS317-layered": (164.07, 39.4),
    "goldman1996-TH1-layered": (200.36, 0.879),
    "goldman2001s-NH5_E-layered": (88.53, 0.292),
}


def test_new_tdem_reports_counts_and_spot_values():
    from collections import Counter

    cat = load_catalogue()
    counts = Counter((d.survey, d.representation.value) for d in cat.datasets)
    for key, n in NEW_TDEM_COUNTS.items():
        assert counts[key] == n, key
    by_id = {d.id: d for d in cat.datasets}
    for ds_id, (top, rho) in NEW_TDEM_HALF_SPACES.items():
        last = by_id[ds_id].layers[-1]
        assert last.bottom_m is None and last.top_m == pytest.approx(top) and last.rho_ohmm == pytest.approx(rho)


def test_source_only_reports_carry_no_values():
    cat = load_catalogue()
    source_only = {"ezersky-2011-tem-nahal-hever", "goldman-2001-tdem-nahal-hever-north", "goldman-kafri-2021-review",
                   "meidav-1963-qiryat-hayyim", "meidav-1965-tellurics", "meqbel-2013-mt-dead-sea",
                   "zafrir-1991-ramon-drillholes"}
    status = {s.id: s.extraction_status for s in cat.surveys}
    assert all(status[s] == "registered" for s in source_only)
    assert not [d.id for d in cat.datasets if d.survey in source_only]
