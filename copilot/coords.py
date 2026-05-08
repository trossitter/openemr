"""Coordinate transform module for PDF extraction provenance.

All bounding boxes extracted by Claude Vision are in image_px_300dpi space
(top-left origin, integer pixels) because we send rasterized page images at a
declared DPI — not the raw PDF document block. That makes the coordinate space
explicit and deterministic.

Coordinate spaces modelled:
  pdf_pts         — PDF point space, 72 dpi, top-left origin (PyMuPDF convention)
  image_px_300dpi — pixel space of the 300-dpi rasterized image (top-left origin)
  normalized      — [0.0, 1.0] fractions of image dimensions (viewport-independent)

All transforms are invertible. Every transform records itself in a TransformChain
so the full lineage of a BBox can be reconstructed deterministically.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Optional

RENDER_DPI: int = 300
PDF_DPI: int = 72
DEFAULT_SCALE: float = RENDER_DPI / PDF_DPI  # 4.1̄6̄


# ---------------------------------------------------------------------------
# Page geometry — captured once at rasterization time
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class PageGeometry:
    """Immutable record of a single page's rasterization parameters."""
    page_index: int           # 0-based page number
    pdf_width_pts: float      # PyMuPDF page.rect.width  (PDF points)
    pdf_height_pts: float     # PyMuPDF page.rect.height (PDF points)
    image_width_px: int       # pixmap.width  after rasterizing at render_dpi
    image_height_px: int      # pixmap.height after rasterizing at render_dpi
    render_dpi: int = RENDER_DPI
    rotation: int = 0         # page rotation in degrees (0 | 90 | 180 | 270)

    @property
    def scale(self) -> float:
        """Pixel-per-point scale factor used during rasterization."""
        return self.render_dpi / PDF_DPI

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @property
    def transform_chain_label(self) -> str:
        return f"fitz_rasterize_{self.render_dpi}dpi_page{self.page_index}"


# ---------------------------------------------------------------------------
# Bounding box with declared coordinate space
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class BBoxCoords:
    """Axis-aligned bounding box plus the coordinate space it lives in."""
    x0: float
    y0: float
    x1: float
    y1: float
    coordinate_space: str  # "image_px_300dpi" | "normalized" | "pdf_pts"

    def width(self) -> float:
        return abs(self.x1 - self.x0)

    def height(self) -> float:
        return abs(self.y1 - self.y0)

    def area(self) -> float:
        return self.width() * self.height()

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Transform chain — audit log of all coordinate operations
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class TransformChain:
    """Ordered log of coordinate transform steps applied to a BBox."""
    steps: list[str] = dataclasses.field(default_factory=list)
    created_at: str = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add(self, step: str) -> "TransformChain":
        self.steps.append(step)
        return self

    def to_list(self) -> list[str]:
        return list(self.steps)

    @classmethod
    def for_extraction(cls, geom: PageGeometry, parser: str = "claude_vision") -> "TransformChain":
        """Standard chain for PDF → Claude Vision extractions."""
        tc = cls()
        tc.add("pdf_source")
        tc.add(geom.transform_chain_label)
        tc.add(f"{parser}_extraction")
        tc.add(f"image_px_{geom.render_dpi}dpi_output")
        return tc

    @classmethod
    def for_tiff_extraction(
        cls,
        geom: PageGeometry,
        native_dpi: int,
        parser: str = "claude_vision",
    ) -> "TransformChain":
        """Chain for TIFF → (optional resample) → Claude Vision extractions.

        native_dpi is the DPI of the source TIFF (inferred from metadata or
        page dimensions). If geom.render_dpi differs, a resample step is logged.
        """
        tc = cls()
        tc.add("tiff_source")
        tc.add(f"read_native_{native_dpi}dpi_page{geom.page_index}")
        if geom.render_dpi != native_dpi:
            tc.add(f"resample_{geom.render_dpi}dpi")
        tc.add(f"{parser}_extraction")
        tc.add(f"image_px_{geom.render_dpi}dpi_output")
        return tc

    @classmethod
    def for_hl7_field(cls, segment_name: str, field_idx: int) -> "TransformChain":
        """Chain for HL7v2 deterministic field extraction (no visual position).

        HL7v2 fields have no bounding-box concept — the transform chain records
        the segment and field index as the provenance anchor instead.
        """
        tc = cls()
        tc.add("hl7v2_source")
        tc.add(f"segment_{segment_name}")
        tc.add(f"field_{field_idx}")
        tc.add("deterministic_parse")
        return tc


# ---------------------------------------------------------------------------
# Explicit transform functions — all invertible
# ---------------------------------------------------------------------------

def image_px_to_normalized(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """image_px_300dpi → normalized [0,1]. Invertible via normalized_to_image_px."""
    assert bbox.coordinate_space == "image_px_300dpi", bbox.coordinate_space
    w, h = geom.image_width_px, geom.image_height_px
    return BBoxCoords(
        x0=bbox.x0 / w,
        y0=bbox.y0 / h,
        x1=bbox.x1 / w,
        y1=bbox.y1 / h,
        coordinate_space="normalized",
    )


def normalized_to_image_px(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """normalized → image_px_300dpi. Inverse of image_px_to_normalized."""
    assert bbox.coordinate_space == "normalized", bbox.coordinate_space
    w, h = geom.image_width_px, geom.image_height_px
    return BBoxCoords(
        x0=bbox.x0 * w,
        y0=bbox.y0 * h,
        x1=bbox.x1 * w,
        y1=bbox.y1 * h,
        coordinate_space="image_px_300dpi",
    )


def image_px_to_pdf_pts(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """image_px_300dpi → pdf_pts. Invertible via pdf_pts_to_image_px.

    Both PyMuPDF and the rasterized image use top-left origin, so this is a
    pure scale — no y-axis flip needed.
    """
    assert bbox.coordinate_space == "image_px_300dpi", bbox.coordinate_space
    s = geom.scale
    return BBoxCoords(
        x0=bbox.x0 / s,
        y0=bbox.y0 / s,
        x1=bbox.x1 / s,
        y1=bbox.y1 / s,
        coordinate_space="pdf_pts",
    )


def pdf_pts_to_image_px(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """pdf_pts → image_px_300dpi. Inverse of image_px_to_pdf_pts."""
    assert bbox.coordinate_space == "pdf_pts", bbox.coordinate_space
    s = geom.scale
    return BBoxCoords(
        x0=bbox.x0 * s,
        y0=bbox.y0 * s,
        x1=bbox.x1 * s,
        y1=bbox.y1 * s,
        coordinate_space="image_px_300dpi",
    )


def normalized_to_pdf_pts(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """normalized → pdf_pts via image_px intermediate."""
    px = normalized_to_image_px(bbox, geom)
    return image_px_to_pdf_pts(px, geom)


def pdf_pts_to_normalized(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """pdf_pts → normalized via image_px intermediate."""
    px = pdf_pts_to_image_px(bbox, geom)
    return image_px_to_normalized(px, geom)


# ---------------------------------------------------------------------------
# Convenience: clamp a bbox to valid page bounds
# ---------------------------------------------------------------------------

def clamp_to_page(bbox: BBoxCoords, geom: PageGeometry) -> BBoxCoords:
    """Clamp image_px_300dpi bbox to [0, page_dim]. Silently fixes off-edge coords."""
    assert bbox.coordinate_space == "image_px_300dpi", bbox.coordinate_space
    w, h = float(geom.image_width_px), float(geom.image_height_px)
    return BBoxCoords(
        x0=max(0.0, min(bbox.x0, w)),
        y0=max(0.0, min(bbox.y0, h)),
        x1=max(0.0, min(bbox.x1, w)),
        y1=max(0.0, min(bbox.y1, h)),
        coordinate_space="image_px_300dpi",
    )
