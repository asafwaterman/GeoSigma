"""Unified GeoSigma data model.

Every survey lives in ``data/surveys/<survey_id>/survey.yaml`` plus one file per
dataset under ``datasets/``. These files are the reviewed source of truth; the
SQLite database is rebuilt from them by ``geosigma build``.

Data levels (never mixed in one product):
  L0  original source file (PDF)
  L1  observed / apparent quantities (sounding curves, pseudosections, maps)
  L2  interpreted models published by the survey authors
  L3  products GeoSigma derives (depth slices, interpolations)
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Method(str, Enum):
    TEM = "TEM"
    MT = "MT"
    AMT = "AMT"
    CSAMT = "CSAMT"
    CSEM = "CSEM"
    VES = "VES"
    DIPOLE = "DIPOLE"  # roving dipole / dipole-dipole DC mapping
    PROFILING = "PROFILING"  # DC resistivity profiling at fixed spacings (e.g. Wenner)
    ERT = "ERT"
    IP = "IP"
    LOG = "LOG"
    OTHER = "OTHER"


class Level(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class Representation(str, Enum):
    sounding_curve = "sounding_curve"  # L1: apparent resistivity vs time/period/spacing
    model_1d = "model_1d"  # L2: layered or smooth resistivity vs depth
    section_2d = "section_2d"  # L2: resistivity on a (distance, depth) grid
    map_grid = "map_grid"  # L1/L3: resistivity on a map
    qualitative = "qualitative"  # text-only result, no usable numbers
    interface_depth = "interface_depth"  # depth to a layer meeting a resistivity criterion
    profile = "profile"  # L1: apparent resistivity along a line at one electrode spacing


class ExtractionMethod(str, Enum):
    parsed_text = "parsed_text"  # copied from a digital text layer or table
    ocr = "ocr"
    digitised_auto = "digitised_auto"  # traced from a raster figure by script
    digitised_manual = "digitised_manual"
    manual = "manual"  # typed by a person or model from the page


class Status(str, Enum):
    draft = "draft"  # extracted, not yet checked
    checked = "checked"  # spot-checked against the source page
    approved = "approved"  # approved by the project owner
    rejected = "rejected"


class Confidence(str, Enum):
    A = "A"  # numeric values from tables or digital data
    B = "B"  # carefully digitised from a clear figure
    C = "C"  # digitised from a poor scan, or model with known issues
    D = "D"  # qualitative only


class SourceDocument(BaseModel):
    id: str
    title: str
    filename: str
    drive_id: Optional[str] = None
    sha256: Optional[str] = None
    pages: Optional[int] = None
    language: list[str] = ["en"]
    scanned: bool = True
    role: str = "main_report"  # main_report, appendix, figures, maps


class Provenance(BaseModel):
    document: str  # SourceDocument.id
    pages: list[int] = []  # 1-based PDF page numbers
    figure: Optional[str] = None
    table: Optional[str] = None
    method: ExtractionMethod
    tool: Optional[str] = None  # script name and version
    extracted_by: str = "claude"
    extracted_on: Optional[date] = None
    checked_by: Optional[str] = None
    notes: Optional[str] = None


class Coordinates(BaseModel):
    """Coordinates as printed in the source, plus their CRS."""

    x: float
    y: float
    crs: str  # e.g. EPSG:2039 (Israeli TM Grid), EPSG:28193 (Old Israel Grid), EPSG:4326
    source: str = "table"  # table, map, text, estimated
    accuracy_m: Optional[float] = None


class Site(BaseModel):
    id: str  # unique within the survey, e.g. "A1-100"
    name: Optional[str] = None
    coords: Coordinates
    elevation_m: Optional[float] = None
    line: Optional[str] = None
    notes: Optional[str] = None


class Layer(BaseModel):
    top_m: float
    bottom_m: Optional[float] = None  # None = half-space
    rho_ohmm: Optional[float] = None
    rho_min: Optional[float] = None
    rho_max: Optional[float] = None
    note: Optional[str] = None


class Sample(BaseModel):
    depth_m: float
    rho_ohmm: float


class CurvePoint(BaseModel):
    x: float  # frequency (Hz), period (s), time (s) or AB/2 (m)
    rho_a: float
    phase_deg: Optional[float] = None


class ProfilePoint(BaseModel):
    station: float  # reading number along the line, as plotted
    rho_a: float
    site: Optional[str] = None  # Site.id of the station, when its position is known


class Dataset(BaseModel):
    id: str
    survey: str
    site: Optional[str] = None
    line: Optional[str] = None
    method: Method
    level: Level
    representation: Representation
    quantity: str = "resistivity"
    unit: str = "ohm.m"
    measured_on: Optional[str] = None  # ISO date or year
    depth_ref: Literal["below_ground", "below_sea_level", "elevation"] = "below_ground"
    depth_max_m: Optional[float] = None  # deepest depth shown in the source
    doi_m: Optional[float] = None  # reliable depth of investigation
    doi_estimated: bool = False
    confidence: Confidence = Confidence.C
    status: Status = Status.draft
    model_type: Optional[Literal["layered", "smooth"]] = None
    x_quantity: Optional[str] = None  # for sounding curves: frequency, period, time, ab2
    layers: list[Layer] = []
    samples: list[Sample] = []
    curve: list[CurvePoint] = []
    profile: list[ProfilePoint] = []
    array: Optional[str] = None  # electrode array, e.g. "Wenner"
    spacing_m: Optional[float] = None  # electrode spacing of a profile
    interface_depth_m: Optional[float] = None
    criterion: Optional[str] = None  # e.g. "rho < 3 ohm.m (seawater)"
    summary: Optional[str] = None  # required for qualitative results
    digitisation_error: Optional[str] = None  # e.g. "+-0.03 log10 rho, +-15 m"
    provenance: Provenance
    reinterprets: Optional[str] = None  # Dataset id this one reinterprets
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_content(self) -> "Dataset":
        r = self.representation
        if r == Representation.model_1d and not (self.layers or self.samples):
            raise ValueError(f"{self.id}: model_1d needs layers or samples")
        if r == Representation.sounding_curve and not self.curve:
            raise ValueError(f"{self.id}: sounding_curve needs curve points")
        if r == Representation.qualitative and not self.summary:
            raise ValueError(f"{self.id}: qualitative dataset needs a summary")
        if r == Representation.profile and not self.profile:
            raise ValueError(f"{self.id}: profile needs points")
        if self.level != Level.L1 and r == Representation.profile:
            raise ValueError(f"{self.id}: a profile of apparent resistivity is L1")
        if r == Representation.interface_depth and self.interface_depth_m is None:
            raise ValueError(f"{self.id}: interface_depth needs interface_depth_m")
        if self.level == Level.L1 and r == Representation.model_1d:
            raise ValueError(f"{self.id}: a depth model cannot be L1")
        for s in self.samples:
            if s.rho_ohmm <= 0:
                raise ValueError(f"{self.id}: non-positive resistivity")
        depths = [s.depth_m for s in self.samples]
        if depths != sorted(depths):
            raise ValueError(f"{self.id}: samples must be ordered by depth")
        tops = [l.top_m for l in self.layers]
        if tops != sorted(tops):
            raise ValueError(f"{self.id}: layers must be ordered by depth")
        return self


class Survey(BaseModel):
    id: str
    name: str
    organisation: str
    client: Optional[str] = None
    authors: list[str] = []
    report_number: Optional[str] = None
    year: int
    acquired: Optional[str] = None  # e.g. "1969-03" or "2013-09/2013-10"
    methods: list[Method]
    region: str
    purpose: Optional[str] = None
    geometry: Optional[str] = None  # "stations", "profile", "area"
    depth_reach: Optional[str] = None
    documents: list[SourceDocument]
    sites: list[Site] = []
    acquisition: dict = Field(default_factory=dict)  # method-specific parameters
    extraction_status: Literal["registered", "partial", "complete", "blocked"] = "registered"
    notes: Optional[str] = None
