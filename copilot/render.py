"""Overlay renderer for PDF extraction provenance.

Produces three outputs per document:
  1. raw_pages       — list of PIL Images (300-dpi rasterizations, one per page)
  2. annotated_pages — same images with bbox overlays, labels, and confidence scores
  3. overlay_metadata — OverlayMetadata (machine-readable JSON, serializable)

Entry point:
    result = render_document_overlay(pdf_path, file_bytes, citations)
    persist_overlay(result)   # writes PNGs + metadata JSON to OVERLAY_DIR

Coordinate invariant: every BBox on a Citation is expected to be in
image_px_300dpi space (top-left origin) because ingest.py rasterizes before
sending to Claude. Boxes in other spaces are silently skipped.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

from coords import RENDER_DPI, PageGeometry
from schemas import Citation

OVERLAY_DIR: str = os.environ.get("OVERLAY_DIR", "/var/log/copilot/overlays")

# Per-source_type annotation colors (R, G, B)
_PALETTE: dict[str, tuple[int, int, int]] = {
    "pdf":          (220,  53,  69),   # red
    "ocr":          (255, 133,  27),   # orange
    "intake_form":  ( 13, 110, 253),   # blue
    "lab_pdf":      (220,  53,  69),   # red (alias)
    "guideline":    ( 25, 135,  84),   # green
    "fhir":         ( 32, 201, 151),   # teal
    "hl7":          ( 32, 201, 151),
    "default":      (102,  16, 242),   # purple
}

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_LABEL_FONT_SIZE = 26
_BORDER_PX = 3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PageOverlayAnnotation:
    page_index: int
    field_id: str
    label: str
    x0: int
    y0: int
    x1: int
    y1: int
    confidence: Optional[float]
    quote: str
    color_rgb: tuple[int, int, int]

    def to_dict(self) -> dict:
        return {
            "page_index": self.page_index,
            "field_id": self.field_id,
            "label": self.label,
            "bbox_image_px": [self.x0, self.y0, self.x1, self.y1],
            "confidence": self.confidence,
            "quote": self.quote,
            "color_rgb": list(self.color_rgb),
        }


@dataclass
class OverlayMetadata:
    doc_id: str
    source_path: str
    page_count: int
    render_dpi: int
    coordinate_space: str
    annotations: list[PageOverlayAnnotation]
    geometries: list[dict]

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "page_count": self.page_count,
            "render_dpi": self.render_dpi,
            "coordinate_space": self.coordinate_space,
            "annotations": [a.to_dict() for a in self.annotations],
            "geometries": self.geometries,
        }


@dataclass
class OverlayResult:
    doc_id: str
    raw_pages: list[Image.Image]
    annotated_pages: list[Image.Image]
    overlay_metadata: OverlayMetadata


# ---------------------------------------------------------------------------
# Rasterization — PDF
# ---------------------------------------------------------------------------

def rasterize_pdf(
    pdf_path: Path,
    dpi: int = RENDER_DPI,
) -> tuple[list[Image.Image], list[PageGeometry]]:
    """Open a PDF with PyMuPDF and rasterize every page at `dpi`.

    Returns (images, geometries) in page order. Both lists are the same length.
    """
    doc = fitz.open(str(pdf_path))
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    images: list[Image.Image] = []
    geometries: list[PageGeometry] = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        geom = PageGeometry(
            page_index=page.number,
            pdf_width_pts=page.rect.width,
            pdf_height_pts=page.rect.height,
            image_width_px=pix.width,
            image_height_px=pix.height,
            render_dpi=dpi,
            rotation=page.rotation,
        )
        images.append(img)
        geometries.append(geom)
    doc.close()
    return images, geometries


# ---------------------------------------------------------------------------
# Rasterization — TIFF
# ---------------------------------------------------------------------------

# Standard fax resolutions → DPI lookup by pixel dimensions (US Letter)
_KNOWN_FAX_DIMS: dict[tuple[int, int], int] = {
    (1700, 2200): 200,   # G3 standard, US Letter @ 200 DPI
    (1728, 2200): 204,   # G3 standard, slight variant
    (1728, 2376): 196,   # G4 standard
    (2550, 3300): 300,   # High-res Letter @ 300 DPI
    (1275, 1650): 150,   # Letter @ 150 DPI
    (850,  1100): 100,   # Letter @ 100 DPI
}


def _infer_tiff_dpi(pil_image: Image.Image, width: int, height: int) -> int:
    """Return the native DPI of a TIFF page.

    PIL reads DPI from the TIFF XResolution/YResolution tags. These tags are
    unreliable for fax output — many fax machines write (1, 1) or (0, 0).
    We fall back to matching known standard fax pixel dimensions.
    """
    dpi_info = pil_image.info.get("dpi", (1, 1))
    reported = int(dpi_info[0]) if isinstance(dpi_info, (tuple, list)) else int(dpi_info)
    if reported >= 72:
        return reported

    # Known standard size match
    if (width, height) in _KNOWN_FAX_DIMS:
        return _KNOWN_FAX_DIMS[(width, height)]

    # Infer from aspect ratio: if close to US Letter (8.5 / 11), compute from width
    if abs((width / height) - (8.5 / 11.0)) < 0.02:
        candidate = round(width / 8.5)
        for standard in (600, 400, 300, 204, 200, 150, 100):
            if abs(candidate - standard) <= standard * 0.08:
                return standard

    return 200  # Conservative default: standard G3 fax


def rasterize_tiff(
    tiff_path: Path,
    target_dpi: int = RENDER_DPI,
) -> tuple[list[Image.Image], list[PageGeometry], int]:
    """Open a multi-page TIFF and return (images, geometries, native_dpi).

    Each frame is converted to RGB and resampled to target_dpi if the native
    DPI is lower. 1-bit bilevel fax images (mode='1') are converted to 'L'
    first to avoid PIL LANCZOS artefacts, then to RGB.

    Returns native_dpi (shared across frames, inferred from first frame).
    PageGeometry.pdf_width_pts is the physical page width in 72-dpi PDF points
    so coordinate transforms to/from pdf_pts remain meaningful.
    """
    src = Image.open(str(tiff_path))
    native_w, native_h = src.size
    native_dpi = _infer_tiff_dpi(src, native_w, native_h)

    # Physical dimensions in PDF points (72 dpi)
    phys_w_pts = native_w * 72.0 / native_dpi
    phys_h_pts = native_h * 72.0 / native_dpi

    scale = target_dpi / native_dpi
    send_w = round(native_w * scale)
    send_h = round(native_h * scale)

    images: list[Image.Image] = []
    geometries: list[PageGeometry] = []

    page_idx = 0
    while True:
        try:
            src.seek(page_idx)
        except EOFError:
            break

        frame = src.copy()
        # Bilevel (mode='1') → greyscale → RGB to avoid resampling artefacts
        if frame.mode == "1":
            frame = frame.convert("L")
        frame = frame.convert("RGB")

        if scale != 1.0:
            frame = frame.resize((send_w, send_h), Image.LANCZOS)

        geom = PageGeometry(
            page_index=page_idx,
            pdf_width_pts=phys_w_pts,
            pdf_height_pts=phys_h_pts,
            image_width_px=send_w,
            image_height_px=send_h,
            render_dpi=target_dpi,
        )
        images.append(frame)
        geometries.append(geom)
        page_idx += 1

    return images, geometries, native_dpi


# ---------------------------------------------------------------------------
# Annotation drawing
# ---------------------------------------------------------------------------

def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _color(source_type: str) -> tuple[int, int, int]:
    return _PALETTE.get(source_type, _PALETTE["default"])


def _draw_box(
    draw: ImageDraw.ImageDraw,
    ann: PageOverlayAnnotation,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    r, g, b = ann.color_rgb
    b3 = _BORDER_PX

    # Outer border rectangle
    draw.rectangle(
        [ann.x0 - b3, ann.y0 - b3, ann.x1 + b3, ann.y1 + b3],
        outline=(r, g, b),
        width=b3,
    )

    # Label text
    conf_str = f" {ann.confidence:.0%}" if ann.confidence is not None else ""
    text = f"{ann.label}{conf_str}"
    tb = draw.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    lx = ann.x0 - b3
    ly = max(0, ann.y0 - b3 - th - 8)
    draw.rectangle([lx, ly, lx + tw + 8, ly + th + 6], fill=(r, g, b))
    draw.text((lx + 4, ly + 3), text, fill=(255, 255, 255), font=font)


def annotate_page(
    raw_image: Image.Image,
    annotations: list[PageOverlayAnnotation],
) -> Image.Image:
    """Return a copy of raw_image with all annotation boxes drawn."""
    img = raw_image.copy()
    if not annotations:
        return img
    draw = ImageDraw.Draw(img)
    font = _load_font(_LABEL_FONT_SIZE)
    for ann in annotations:
        _draw_box(draw, ann, font)
    return img


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_document_overlay(
    pdf_path: Path,
    file_bytes: bytes,
    citations: list[Citation],
) -> OverlayResult:
    """Rasterize the PDF and produce raw + annotated pages with overlay metadata.

    Only Citations with a bbox in image_px_300dpi space are rendered. Citations
    without bboxes are silently skipped (they still appear in the response JSON).
    """
    doc_id = hashlib.sha256(file_bytes).hexdigest()[:16]
    raw_pages, geometries = rasterize_pdf(pdf_path)
    n = len(raw_pages)

    ann_by_page: dict[int, list[PageOverlayAnnotation]] = {i: [] for i in range(n)}
    all_annotations: list[PageOverlayAnnotation] = []

    for cit in citations:
        b = cit.bbox
        if b is None or b.coordinate_space != "image_px_300dpi":
            continue
        page_idx = b.page
        if page_idx < 0 or page_idx >= n:
            continue
        ann = PageOverlayAnnotation(
            page_index=page_idx,
            field_id=cit.field_or_chunk_id,
            label=cit.field_or_chunk_id,
            x0=int(b.x0),
            y0=int(b.y0),
            x1=int(b.x1),
            y1=int(b.y1),
            confidence=cit.ocr_confidence,
            quote=(cit.quote_or_value or "")[:80],
            color_rgb=_color(cit.source_type),
        )
        ann_by_page[page_idx].append(ann)
        all_annotations.append(ann)

    annotated_pages = [
        annotate_page(raw_pages[i], ann_by_page[i]) for i in range(n)
    ]

    metadata = OverlayMetadata(
        doc_id=doc_id,
        source_path=str(pdf_path),
        page_count=n,
        render_dpi=RENDER_DPI,
        coordinate_space="image_px_300dpi",
        annotations=all_annotations,
        geometries=[g.to_dict() for g in geometries],
    )

    return OverlayResult(
        doc_id=doc_id,
        raw_pages=raw_pages,
        annotated_pages=annotated_pages,
        overlay_metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_overlay(result: OverlayResult) -> Path:
    """Save annotated PNGs and overlay_metadata.json under OVERLAY_DIR/{doc_id}/."""
    out_dir = Path(OVERLAY_DIR) / result.doc_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, img in enumerate(result.annotated_pages):
        img.save(out_dir / f"page_{i:03d}.png", format="PNG", optimize=True)

    (out_dir / "overlay_metadata.json").write_text(
        json.dumps(result.overlay_metadata.to_dict(), indent=2),
        encoding="utf-8",
    )
    return out_dir


def page_to_b64(image: Image.Image) -> str:
    """Return a base64-encoded PNG of a PIL Image (for inline API responses)."""
    import base64
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()
