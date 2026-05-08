"""Unit tests for the coordinate transform module.

All transforms must be:
  - Invertible (round-trip within floating-point tolerance)
  - Consistent with the declared scale factor
  - Correct at page edges (0,0) and (w,h)

Run with: python -m pytest evals/test_coords.py -v
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from coords import (
    BBoxCoords,
    PageGeometry,
    RENDER_DPI,
    PDF_DPI,
    DEFAULT_SCALE,
    clamp_to_page,
    image_px_to_normalized,
    image_px_to_pdf_pts,
    normalized_to_image_px,
    normalized_to_pdf_pts,
    pdf_pts_to_image_px,
    pdf_pts_to_normalized,
)

TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def letter_page() -> PageGeometry:
    """US Letter at 300 DPI: 8.5in × 11in."""
    return PageGeometry(
        page_index=0,
        pdf_width_pts=612.0,   # 8.5in × 72
        pdf_height_pts=792.0,  # 11in  × 72
        image_width_px=2550,   # 8.5in × 300
        image_height_px=3300,  # 11in  × 300
    )


@pytest.fixture
def a4_page() -> PageGeometry:
    """A4 at 300 DPI: 595pt × 842pt."""
    scale = RENDER_DPI / PDF_DPI
    return PageGeometry(
        page_index=1,
        pdf_width_pts=595.0,
        pdf_height_pts=842.0,
        image_width_px=round(595.0 * scale),
        image_height_px=round(842.0 * scale),
    )


def _px_bbox(x0, y0, x1, y1) -> BBoxCoords:
    return BBoxCoords(x0=x0, y0=y0, x1=x1, y1=y1, coordinate_space="image_px_300dpi")


def _norm_bbox(x0, y0, x1, y1) -> BBoxCoords:
    return BBoxCoords(x0=x0, y0=y0, x1=x1, y1=y1, coordinate_space="normalized")


def _pdf_bbox(x0, y0, x1, y1) -> BBoxCoords:
    return BBoxCoords(x0=x0, y0=y0, x1=x1, y1=y1, coordinate_space="pdf_pts")


# ---------------------------------------------------------------------------
# Scale consistency
# ---------------------------------------------------------------------------

def test_default_scale():
    assert math.isclose(DEFAULT_SCALE, 300 / 72, rel_tol=1e-9)


def test_page_geometry_scale(letter_page):
    assert math.isclose(letter_page.scale, DEFAULT_SCALE, rel_tol=1e-9)


def test_letter_page_dimensions(letter_page):
    assert letter_page.image_width_px == 2550
    assert letter_page.image_height_px == 3300


# ---------------------------------------------------------------------------
# image_px ↔ normalized (round-trip)
# ---------------------------------------------------------------------------

def test_px_to_normalized_center(letter_page):
    px = _px_bbox(1275.0, 1650.0, 1275.0, 1650.0)
    norm = image_px_to_normalized(px, letter_page)
    assert norm.coordinate_space == "normalized"
    assert math.isclose(norm.x0, 0.5, abs_tol=TOLERANCE)
    assert math.isclose(norm.y0, 0.5, abs_tol=TOLERANCE)


def test_px_to_normalized_top_left(letter_page):
    px = _px_bbox(0, 0, 0, 0)
    norm = image_px_to_normalized(px, letter_page)
    assert math.isclose(norm.x0, 0.0, abs_tol=TOLERANCE)
    assert math.isclose(norm.y0, 0.0, abs_tol=TOLERANCE)


def test_px_to_normalized_bottom_right(letter_page):
    px = _px_bbox(2550, 3300, 2550, 3300)
    norm = image_px_to_normalized(px, letter_page)
    assert math.isclose(norm.x1, 1.0, abs_tol=TOLERANCE)
    assert math.isclose(norm.y1, 1.0, abs_tol=TOLERANCE)


def test_normalized_to_px_round_trip(letter_page):
    original = _px_bbox(300.0, 400.0, 800.0, 900.0)
    norm = image_px_to_normalized(original, letter_page)
    recovered = normalized_to_image_px(norm, letter_page)
    assert recovered.coordinate_space == "image_px_300dpi"
    assert math.isclose(recovered.x0, original.x0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y0, original.y0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.x1, original.x1, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y1, original.y1, abs_tol=TOLERANCE)


def test_normalized_to_px_round_trip_a4(a4_page):
    original = _px_bbox(100.0, 200.0, 500.0, 700.0)
    recovered = normalized_to_image_px(image_px_to_normalized(original, a4_page), a4_page)
    assert math.isclose(recovered.x0, original.x0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y0, original.y0, abs_tol=TOLERANCE)


# ---------------------------------------------------------------------------
# image_px ↔ pdf_pts (round-trip)
# ---------------------------------------------------------------------------

def test_px_to_pdf_pts_scale(letter_page):
    px = _px_bbox(300.0, 300.0, 600.0, 600.0)
    pts = image_px_to_pdf_pts(px, letter_page)
    assert pts.coordinate_space == "pdf_pts"
    expected_x0 = 300.0 / DEFAULT_SCALE
    assert math.isclose(pts.x0, expected_x0, rel_tol=1e-6)


def test_pdf_pts_to_px_round_trip(letter_page):
    original = _px_bbox(127.5, 165.0, 1275.0, 1650.0)
    pts = image_px_to_pdf_pts(original, letter_page)
    recovered = pdf_pts_to_image_px(pts, letter_page)
    assert recovered.coordinate_space == "image_px_300dpi"
    assert math.isclose(recovered.x0, original.x0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y0, original.y0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.x1, original.x1, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y1, original.y1, abs_tol=TOLERANCE)


def test_full_page_pdf_pts(letter_page):
    px = _px_bbox(0, 0, 2550, 3300)
    pts = image_px_to_pdf_pts(px, letter_page)
    assert math.isclose(pts.x1, 612.0, rel_tol=1e-4)
    assert math.isclose(pts.y1, 792.0, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# normalized ↔ pdf_pts (round-trip, two-step chain)
# ---------------------------------------------------------------------------

def test_normalized_to_pdf_pts_round_trip(letter_page):
    original = _norm_bbox(0.1, 0.2, 0.8, 0.9)
    pts = normalized_to_pdf_pts(original, letter_page)
    assert pts.coordinate_space == "pdf_pts"
    recovered = pdf_pts_to_normalized(pts, letter_page)
    assert math.isclose(recovered.x0, original.x0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y0, original.y0, abs_tol=TOLERANCE)
    assert math.isclose(recovered.x1, original.x1, abs_tol=TOLERANCE)
    assert math.isclose(recovered.y1, original.y1, abs_tol=TOLERANCE)


# ---------------------------------------------------------------------------
# clamp_to_page
# ---------------------------------------------------------------------------

def test_clamp_keeps_valid_bbox(letter_page):
    px = _px_bbox(100.0, 200.0, 500.0, 600.0)
    clamped = clamp_to_page(px, letter_page)
    assert clamped.x0 == 100.0
    assert clamped.y1 == 600.0


def test_clamp_negative_coords(letter_page):
    px = _px_bbox(-50.0, -100.0, 300.0, 400.0)
    clamped = clamp_to_page(px, letter_page)
    assert clamped.x0 == 0.0
    assert clamped.y0 == 0.0


def test_clamp_overflow_coords(letter_page):
    px = _px_bbox(0, 0, 9999.0, 9999.0)
    clamped = clamp_to_page(px, letter_page)
    assert clamped.x1 == float(letter_page.image_width_px)
    assert clamped.y1 == float(letter_page.image_height_px)


# ---------------------------------------------------------------------------
# BBoxCoords helpers
# ---------------------------------------------------------------------------

def test_bbox_width_height():
    b = _px_bbox(100, 200, 400, 500)
    assert b.width() == 300.0
    assert b.height() == 300.0


def test_bbox_area():
    b = _px_bbox(0, 0, 10, 20)
    assert b.area() == 200.0


# ---------------------------------------------------------------------------
# Coordinate space assertion guards
# ---------------------------------------------------------------------------

def test_wrong_space_raises_for_px_to_norm():
    wrong = _norm_bbox(0.1, 0.1, 0.5, 0.5)
    geom = PageGeometry(0, 612, 792, 2550, 3300)
    with pytest.raises(AssertionError):
        image_px_to_normalized(wrong, geom)


def test_wrong_space_raises_for_norm_to_px():
    wrong = _px_bbox(100, 100, 200, 200)
    geom = PageGeometry(0, 612, 792, 2550, 3300)
    with pytest.raises(AssertionError):
        normalized_to_image_px(wrong, geom)
