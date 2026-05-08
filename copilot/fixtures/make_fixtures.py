"""Generate synthetic clinical test fixtures (PDFs + PNG).

Produces realistic lab reports and intake forms with known content so the
bbox overlay can be visually verified against ground truth.

Run from the copilot/ directory:
    python fixtures/make_fixtures.py

Output: fixtures/
    p01-chen-lipid-panel.pdf     — 1-page lipid panel (lab_pdf)
    p02-patel-cbc.pdf            — 1-page CBC with differential (lab_pdf)
    p03-garcia-hba1c.pdf         — 1-page HbA1c + metabolic (lab_pdf)
    p01-chen-intake.pdf          — 1-page typed intake form (intake_form)
    p02-patel-intake.pdf         — 1-page typed intake form (intake_form)
    p01-chen-lipid-panel.png     — rasterized version of the lipid panel
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

OUT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

W, H = 612, 792   # US Letter in PDF points (72 dpi)
MARGIN = 54        # 0.75in
COL_RIGHT = W - MARGIN

BLACK  = (0, 0, 0)
GRAY   = (0.4, 0.4, 0.4)
RED    = (0.8, 0.1, 0.1)
BLUE   = (0.1, 0.1, 0.7)
LINE_C = (0.7, 0.7, 0.7)


def _page(doc: fitz.Document) -> fitz.Page:
    return doc.new_page(width=W, height=H)


def _text(page: fitz.Page, x: float, y: float, text: str,
          size: float = 10, color=BLACK, bold: bool = False) -> None:
    font = "hebo" if bold else "helv"
    page.insert_text((x, y), text, fontsize=size, color=color, fontname=font)


def _hline(page: fitz.Page, y: float, x0: float = MARGIN, x1: float = COL_RIGHT,
           width: float = 0.5, color=LINE_C) -> None:
    page.draw_line((x0, y), (x1, y), color=color, width=width)


def _header(page: fitz.Page, title: str, patient: dict, collection: str) -> float:
    """Draw lab report header. Returns y position after header."""
    y = 48
    _text(page, MARGIN, y, "REGIONAL MEDICAL LABORATORY SERVICES", size=9, color=GRAY)
    _text(page, MARGIN, y + 14, "123 Health Way, Suite 400 | Boston, MA 02115 | (617) 555-0100", size=8, color=GRAY)
    _text(page, MARGIN, y + 32, title, size=14, bold=True)
    _hline(page, y + 40, width=1.0, color=BLUE)

    y = 108
    _text(page, MARGIN,       y,      "PATIENT",         size=8, color=GRAY, bold=True)
    _text(page, MARGIN,       y + 12, patient["name"],   size=10, bold=True)
    _text(page, MARGIN,       y + 24, f"DOB: {patient['dob']}  |  MRN: {patient['mrn']}", size=9)

    _text(page, 260,          y,      "PROVIDER",        size=8, color=GRAY, bold=True)
    _text(page, 260,          y + 12, patient["provider"], size=9)
    _text(page, 260,          y + 24, patient["npi"],    size=9)

    _text(page, 420,          y,      "COLLECTION",      size=8, color=GRAY, bold=True)
    _text(page, 420,          y + 12, collection,        size=9)
    _text(page, 420,          y + 24, "Fasting: Yes",    size=9)

    _hline(page, y + 38)
    return y + 54


def _table_header(page: fitz.Page, y: float) -> float:
    cols = [MARGIN, 220, 305, 390, 480]
    labels = ["TEST NAME", "RESULT", "UNITS", "REFERENCE RANGE", "FLAG"]
    for x, label in zip(cols, labels):
        _text(page, x, y, label, size=8, color=GRAY, bold=True)
    _hline(page, y + 6, width=0.75, color=(0.5, 0.5, 0.5))
    return y + 18


def _table_row(page: fitz.Page, y: float, name: str, value: str, unit: str,
               ref: str, flag: str = "", bold_name: bool = False) -> float:
    cols = [MARGIN, 220, 305, 390, 480]
    color_flag = RED if flag == "H" or flag == "L" else BLACK
    _text(page, cols[0], y, name,  size=9, bold=bold_name)
    _text(page, cols[1], y, value, size=9, bold=bool(flag), color=color_flag)
    _text(page, cols[2], y, unit,  size=9)
    _text(page, cols[3], y, ref,   size=9)
    if flag:
        _text(page, cols[4], y, flag, size=9, bold=True, color=color_flag)
    _hline(page, y + 8)
    return y + 20


def _section_label(page: fitz.Page, y: float, label: str) -> float:
    _text(page, MARGIN, y, label, size=9, color=BLUE, bold=True)
    return y + 14


# ---------------------------------------------------------------------------
# Fixture 1: Lipid Panel — p01-chen
# ---------------------------------------------------------------------------

def make_lipid_panel() -> None:
    doc = fitz.open()
    page = _page(doc)
    patient = {
        "name": "Wei Chen",
        "dob": "1968-03-14",
        "mrn": "MRN-001234",
        "provider": "Dr. Sarah Hoffman, MD",
        "npi": "NPI 1234567890",
    }
    y = _header(page, "LIPID PANEL", patient, "2025-11-03")

    y = _section_label(page, y, "LIPID PANEL")
    y = _table_header(page, y)
    y = _table_row(page, y, "Total Cholesterol",     "241",  "mg/dL",  "100–199",   "H")
    y = _table_row(page, y, "LDL Cholesterol",       "162",  "mg/dL",  "0–99",      "H")
    y = _table_row(page, y, "HDL Cholesterol",       "38",   "mg/dL",  "≥40",       "L")
    y = _table_row(page, y, "Triglycerides",         "205",  "mg/dL",  "0–149",     "H")
    y = _table_row(page, y, "Non-HDL Cholesterol",   "203",  "mg/dL",  "0–129",     "H")
    y = _table_row(page, y, "VLDL Cholesterol",      "41",   "mg/dL",  "5–40",      "H")
    y = _table_row(page, y, "LDL/HDL Ratio",         "4.3",  "",       "<3.5",      "H")

    y += 10
    y = _section_label(page, y, "GLUCOSE")
    y = _table_header(page, y)
    y = _table_row(page, y, "Glucose, Fasting",      "118",  "mg/dL",  "70–99",     "H")

    y += 10
    _hline(page, y, width=1.0, color=BLUE)
    y += 12
    _text(page, MARGIN, y,
          "* Results flagged H (High) or L (Low) are outside reference range. "
          "Confirm fasting status before interpretation.",
          size=8, color=GRAY)
    y += 12
    _text(page, MARGIN, y,
          "This report is for authorized clinical use only. "
          "Reviewed and released: 2025-11-03  |  Lab Director: James Okonkwo, MD, FCAP",
          size=8, color=GRAY)

    path = OUT / "p01-chen-lipid-panel.pdf"
    doc.save(str(path))
    doc.close()
    print(f"  created {path}")


# ---------------------------------------------------------------------------
# Fixture 2: CBC with Differential — p02-patel
# ---------------------------------------------------------------------------

def make_cbc() -> None:
    doc = fitz.open()
    page = _page(doc)
    patient = {
        "name": "Priya Patel",
        "dob": "1985-07-22",
        "mrn": "MRN-002891",
        "provider": "Dr. Marcus Webb, MD",
        "npi": "NPI 9876543210",
    }
    y = _header(page, "COMPLETE BLOOD COUNT WITH DIFFERENTIAL", patient, "2025-11-10")

    y = _section_label(page, y, "CBC")
    y = _table_header(page, y)
    y = _table_row(page, y, "WBC",                   "4.2",   "10³/µL", "4.5–11.0",  "L")
    y = _table_row(page, y, "RBC",                   "4.10",  "10⁶/µL", "3.80–5.10", "")
    y = _table_row(page, y, "Hemoglobin",             "11.2",  "g/dL",   "11.5–15.5", "L")
    y = _table_row(page, y, "Hematocrit",             "33.8",  "%",      "34.0–45.0", "L")
    y = _table_row(page, y, "MCV",                    "72.4",  "fL",     "80.0–100.0","L")
    y = _table_row(page, y, "MCH",                    "23.1",  "pg",     "27.0–33.0", "L")
    y = _table_row(page, y, "MCHC",                   "31.9",  "g/dL",   "32.0–36.0", "L")
    y = _table_row(page, y, "RDW",                    "15.8",  "%",      "11.0–14.5", "H")
    y = _table_row(page, y, "Platelets",              "312",   "10³/µL", "150–400",   "")

    y += 4
    y = _section_label(page, y, "DIFFERENTIAL")
    y = _table_header(page, y)
    y = _table_row(page, y, "Neutrophils",            "58",    "%",      "50–70",     "")
    y = _table_row(page, y, "Lymphocytes",            "31",    "%",      "20–40",     "")
    y = _table_row(page, y, "Monocytes",              "8",     "%",      "2–10",      "")
    y = _table_row(page, y, "Eosinophils",            "2",     "%",      "1–4",       "")
    y = _table_row(page, y, "Basophils",              "1",     "%",      "0–1",       "")

    y += 10
    _text(page, MARGIN, y,
          "Interpretation: Microcytic hypochromic anemia pattern. "
          "Clinical correlation recommended. Iron studies suggested.",
          size=8, color=GRAY)

    path = OUT / "p02-patel-cbc.pdf"
    doc.save(str(path))
    doc.close()
    print(f"  created {path}")


# ---------------------------------------------------------------------------
# Fixture 3: HbA1c + Metabolic Panel — p03-garcia
# ---------------------------------------------------------------------------

def make_hba1c() -> None:
    doc = fitz.open()
    page = _page(doc)
    patient = {
        "name": "Eduardo Garcia",
        "dob": "1959-12-01",
        "mrn": "MRN-003445",
        "provider": "Dr. Sarah Hoffman, MD",
        "npi": "NPI 1234567890",
    }
    y = _header(page, "HEMOGLOBIN A1c + BASIC METABOLIC PANEL", patient, "2025-11-15")

    y = _section_label(page, y, "GLYCEMIC")
    y = _table_header(page, y)
    y = _table_row(page, y, "Hemoglobin A1c",        "8.4",   "%",      "<5.7",      "H")
    y = _table_row(page, y, "eAG (est. avg glucose)", "193",  "mg/dL",  "—",         "")
    y = _table_row(page, y, "Glucose, Random",        "214",  "mg/dL",  "70–140",    "H")

    y += 4
    y = _section_label(page, y, "BASIC METABOLIC PANEL")
    y = _table_header(page, y)
    y = _table_row(page, y, "Sodium",                 "138",  "mEq/L",  "136–145",   "")
    y = _table_row(page, y, "Potassium",              "4.1",  "mEq/L",  "3.5–5.1",   "")
    y = _table_row(page, y, "Chloride",               "102",  "mEq/L",  "98–107",    "")
    y = _table_row(page, y, "CO2",                    "24",   "mEq/L",  "22–29",     "")
    y = _table_row(page, y, "BUN",                    "19",   "mg/dL",  "7–20",      "")
    y = _table_row(page, y, "Creatinine",             "1.1",  "mg/dL",  "0.6–1.2",   "")
    y = _table_row(page, y, "eGFR",                   "68",   "mL/min/1.73m²", ">60","")
    y = _table_row(page, y, "Calcium",                "9.3",  "mg/dL",  "8.5–10.2",  "")

    y += 8
    _text(page, MARGIN, y,
          "HbA1c of 8.4% indicates suboptimal glycemic control. "
          "ADA 2024 target: <7.0% for most adults with T2DM.",
          size=8, color=GRAY)

    path = OUT / "p03-garcia-hba1c.pdf"
    doc.save(str(path))
    doc.close()
    print(f"  created {path}")


# ---------------------------------------------------------------------------
# Fixture 4: Intake Form — p01-chen
# ---------------------------------------------------------------------------

def make_intake_chen() -> None:
    doc = fitz.open()
    page = _page(doc)

    y = 48
    _text(page, MARGIN, y,      "RIVERDALE PRIMARY CARE", size=12, bold=True, color=BLUE)
    _text(page, MARGIN, y + 16, "PATIENT INTAKE FORM", size=10, bold=True)
    _hline(page, y + 28, width=1.0, color=BLUE)
    y += 44

    def section(label: str) -> None:
        nonlocal y
        y += 6
        _text(page, MARGIN, y, label, size=9, bold=True, color=BLUE)
        _hline(page, y + 10, width=0.5)
        y += 20

    def field(label: str, value: str, x_label: float = MARGIN, x_value: float = 180) -> None:
        nonlocal y
        _text(page, x_label, y, label, size=8, color=GRAY)
        _text(page, x_value, y, value, size=9, bold=True)
        y += 16

    def bullet(text: str) -> None:
        nonlocal y
        _text(page, MARGIN + 8, y, f"• {text}", size=9)
        y += 14

    section("PATIENT DEMOGRAPHICS")
    field("Full Name:",           "Wei Chen")
    field("Date of Birth:",       "March 14, 1968")
    field("Sex:",                 "Male")
    field("Phone:",               "(617) 555-0191")
    field("Address:",             "44 Elm Street, Cambridge, MA 02138")

    section("CHIEF CONCERN")
    _text(page, MARGIN, y,
          "I've been having chest tightness and shortness of breath when I walk up stairs.",
          size=9, bold=True)
    y += 14
    _text(page, MARGIN, y,
          "Started about 3 weeks ago. Also noticed ankle swelling in the evenings.",
          size=9)
    y += 20

    section("CURRENT MEDICATIONS")
    bullet("Atorvastatin 40 mg — once daily at bedtime")
    bullet("Lisinopril 10 mg — once daily in the morning")
    bullet("Metformin 500 mg — twice daily with meals")

    section("ALLERGIES")
    bullet("Penicillin — hives and throat swelling (anaphylaxis)")
    bullet("Sulfa drugs — rash")
    bullet("Shellfish — GI upset")

    section("FAMILY HISTORY")
    bullet("Father: MI at age 58, hypertension, T2DM")
    bullet("Mother: Hypertension, hyperlipidemia")
    bullet("Brother: T2DM diagnosed age 45")

    y += 4
    _hline(page, y, width=0.5)
    y += 10
    _text(page, MARGIN, y,
          "Signature: Wei Chen                                    Date: November 3, 2025",
          size=8, color=GRAY)

    path = OUT / "p01-chen-intake.pdf"
    doc.save(str(path))
    doc.close()
    print(f"  created {path}")


# ---------------------------------------------------------------------------
# Fixture 5: Intake Form — p02-patel
# ---------------------------------------------------------------------------

def make_intake_patel() -> None:
    doc = fitz.open()
    page = _page(doc)

    y = 48
    _text(page, MARGIN, y,      "RIVERDALE PRIMARY CARE", size=12, bold=True, color=BLUE)
    _text(page, MARGIN, y + 16, "PATIENT INTAKE FORM", size=10, bold=True)
    _hline(page, y + 28, width=1.0, color=BLUE)
    y += 44

    def section(label: str) -> None:
        nonlocal y
        y += 6
        _text(page, MARGIN, y, label, size=9, bold=True, color=BLUE)
        _hline(page, y + 10, width=0.5)
        y += 20

    def field(label: str, value: str) -> None:
        nonlocal y
        _text(page, MARGIN, y, label, size=8, color=GRAY)
        _text(page, 180, y, value, size=9, bold=True)
        y += 16

    def bullet(text: str) -> None:
        nonlocal y
        _text(page, MARGIN + 8, y, f"• {text}", size=9)
        y += 14

    section("PATIENT DEMOGRAPHICS")
    field("Full Name:",    "Priya Patel")
    field("Date of Birth:","July 22, 1985")
    field("Sex:",          "Female")
    field("Phone:",        "(857) 555-0347")
    field("Address:",      "19 Beacon Hill Ave, Boston, MA 02108")

    section("CHIEF CONCERN")
    _text(page, MARGIN, y,
          "Extreme fatigue for the past two months, worse in the afternoon.",
          size=9, bold=True)
    y += 14
    _text(page, MARGIN, y,
          "Also feeling cold all the time and noticed hair thinning. No chest pain.",
          size=9)
    y += 20

    section("CURRENT MEDICATIONS")
    bullet("Ferrous sulfate 325 mg — once daily (prescribed 6 months ago, ran out)")
    bullet("Ibuprofen 400 mg — as needed for menstrual cramps")

    section("ALLERGIES")
    bullet("No known drug allergies (NKDA)")
    bullet("Latex — contact dermatitis")

    section("FAMILY HISTORY")
    bullet("Mother: Hypothyroidism, iron-deficiency anemia")
    bullet("Father: Hypertension")
    bullet("Maternal aunt: Celiac disease")

    y += 4
    _hline(page, y, width=0.5)
    y += 10
    _text(page, MARGIN, y,
          "Signature: Priya Patel                                 Date: November 10, 2025",
          size=8, color=GRAY)

    path = OUT / "p02-patel-intake.pdf"
    doc.save(str(path))
    doc.close()
    print(f"  created {path}")


# ---------------------------------------------------------------------------
# Fixture 6: PNG rasterization of the lipid panel
# ---------------------------------------------------------------------------

def make_png() -> None:
    import fitz
    src = OUT / "p01-chen-lipid-panel.pdf"
    if not src.exists():
        print(f"  skipped PNG — {src} not found (run make_lipid_panel first)")
        return
    doc = fitz.open(str(src))
    page = doc[0]
    mat = fitz.Matrix(300 / 72, 300 / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    path = OUT / "p01-chen-lipid-panel.png"
    pix.save(str(path))
    doc.close()
    print(f"  created {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating clinical test fixtures...")
    make_lipid_panel()
    make_cbc()
    make_hba1c()
    make_intake_chen()
    make_intake_patel()
    make_png()
    print(f"\nDone. Files written to {OUT}/")
    print("\nTest with:")
    print("  Lab PDF:")
    print("  curl -X POST https://clinicalcopilot.org/copilot/v2/ingest \\")
    print("    -H 'X-Copilot-Secret: copilot-prod-559a98e9a9a7d479dfb99e16' \\")
    print("    -F 'file=@fixtures/p01-chen-lipid-panel.pdf' \\")
    print("    -F 'doc_type=lab_pdf' -F 'pid=1' | python3 -m json.tool")
    print()
    print("  Intake form:")
    print("  curl -X POST https://clinicalcopilot.org/copilot/v2/ingest \\")
    print("    -H 'X-Copilot-Secret: copilot-prod-559a98e9a9a7d479dfb99e16' \\")
    print("    -F 'file=@fixtures/p01-chen-intake.pdf' \\")
    print("    -F 'doc_type=intake_form' -F 'pid=1' | python3 -m json.tool")
    print()
    print("  Then fetch the overlay:")
    print("  curl 'https://clinicalcopilot.org/copilot/v2/overlay/<doc_id>/0' \\")
    print("    -H 'X-Copilot-Secret: copilot-prod-559a98e9a9a7d479dfb99e16' \\")
    print("    -o annotated_page_0.png && open annotated_page_0.png")
