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
