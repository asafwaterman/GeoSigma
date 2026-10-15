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

