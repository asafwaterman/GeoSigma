"""L3 products derived from L2 models: values at a chosen depth and coverage."""
from __future__ import annotations

import math
from typing import Optional

from .schema import Dataset, Representation


def value_at_depth(ds: Dataset, depth_m: float) -> Optional[float]:
    """Resistivity of a 1D model at ``depth_m`` (below ground), or None if outside it."""
    if ds.representation != Representation.model_1d:
        return None
    if ds.layers:
        for layer in ds.layers:
            bottom = layer.bottom_m if layer.bottom_m is not None else math.inf
            if layer.top_m <= depth_m < bottom:
                return layer.rho_ohmm
        return None
    s = ds.samples
    if not s or depth_m < s[0].depth_m or depth_m > s[-1].depth_m:
        return None
    for a, b in zip(s, s[1:]):
        if a.depth_m <= depth_m <= b.depth_m:
            if b.depth_m == a.depth_m:
                return a.rho_ohmm
            t = (depth_m - a.depth_m) / (b.depth_m - a.depth_m)
            return 10 ** (math.log10(a.rho_ohmm) * (1 - t) + math.log10(b.rho_ohmm) * t)
    return s[-1].rho_ohmm


def reliability_at_depth(ds: Dataset, depth_m: float) -> str:
    """'reliable', 'below_doi', 'beyond_model' or 'unknown_doi'."""
    deepest = ds.depth_max_m
    if deepest is None:
        if ds.samples:
            deepest = ds.samples[-1].depth_m
        elif ds.layers:
            last = ds.layers[-1]
            deepest = last.bottom_m if last.bottom_m is not None else math.inf
    if deepest is not None and depth_m > deepest:
        return "beyond_model"
    if ds.doi_m is None:
        return "unknown_doi"
    return "reliable" if depth_m <= ds.doi_m else "below_doi"
