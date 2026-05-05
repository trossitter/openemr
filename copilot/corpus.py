"""Static guideline corpus for hybrid RAG (MVP: 3 docs, section-level chunks)."""
from __future__ import annotations

# Each chunk is a plain dict matching the GuidelineChunk shape in retriever.py.
# Text is sourced from publicly available clinical guidelines.
CORPUS_CHUNKS: list[dict] = [
    # ── ADA Standards of Care 2024 ─────────────────────────────────────────
    {
        "text": (
            "For most nonpregnant adults with type 2 diabetes, an HbA1c goal of less than 7% "
            "(53 mmol/mol) is appropriate. Less stringent goals (e.g., <8%) may be appropriate "
            "for patients with a history of severe hypoglycemia, limited life expectancy, "
            "advanced diabetes complications, or poor glycemic control despite multiple "
            "interventions. More stringent goals (e.g., <6.5%) may be considered in select "
            "patients with short duration of diabetes and long life expectancy if achievable "
            "without significant hypoglycemia or other adverse effects."
        ),
        "source_type": "guideline",
        "source_id": "ADA-2024",
        "page_or_section": "Section 6: Glycemic Targets",
        "field_or_chunk_id": "ada-2024-s6-glycemic-targets",
    },
    {
        "text": (
            "Metformin, if not contraindicated and if tolerated, is the preferred initial "
            "pharmacologic agent for type 2 diabetes. For patients with type 2 diabetes and "
            "established cardiovascular disease, indicators of high cardiovascular risk, "
            "established kidney disease, or heart failure, a GLP-1 receptor agonist or "
            "SGLT-2 inhibitor with proven cardiovascular benefit is recommended as part of "
            "the glucose-lowering regimen independent of HbA1c and in addition to metformin."
        ),
        "source_type": "guideline",
        "source_id": "ADA-2024",
        "page_or_section": "Section 9: Pharmacologic Approaches to Glycemic Treatment",
        "field_or_chunk_id": "ada-2024-s9-pharmacologic-therapy",
    },
    {
        "text": (
            "People with diabetes and hypertension should be treated to a systolic blood "
            "pressure (SBP) goal of less than 130 mmHg and a diastolic blood pressure (DBP) "
            "goal of less than 80 mmHg, if it can be safely achieved. ACE inhibitors or "
            "angiotensin receptor blockers (ARBs) are the recommended first-line agents for "
            "treating hypertension in people with diabetes who have albuminuria, as they slow "
            "the progression of kidney disease."
        ),
        "source_type": "guideline",
        "source_id": "ADA-2024",
        "page_or_section": "Section 10: Cardiovascular Disease and Risk Management — Hypertension",
        "field_or_chunk_id": "ada-2024-s10-bp-treatment",
    },
    {
        "text": (
            "Statin therapy is recommended for patients with diabetes aged 40–75 years. "
            "Moderate-intensity statin therapy is recommended for patients without additional "
            "atherosclerotic cardiovascular disease (ASCVD) risk factors. High-intensity statin "
            "therapy is recommended for patients with diabetes and established ASCVD or multiple "
            "ASCVD risk factors to reduce LDL cholesterol by 50% or more. The primary goal is "
            "an LDL cholesterol less than 70 mg/dL for high-risk patients."
        ),
        "source_type": "guideline",
        "source_id": "ADA-2024",
        "page_or_section": "Section 10: Cardiovascular Disease and Risk Management — Lipids",
        "field_or_chunk_id": "ada-2024-s10-statin-therapy",
    },

    # ── JNC 8 Hypertension Guidelines (JAMA 2014) ──────────────────────────
    {
        "text": (
            "In the general population aged 60 years or older, initiate pharmacologic treatment "
            "at SBP ≥150 mmHg or DBP ≥90 mmHg and treat to a goal of SBP <150 mmHg and DBP "
            "<90 mmHg. In the general population younger than 60 years, initiate treatment at "
            "DBP ≥90 mmHg (goal <90 mmHg) and at SBP ≥140 mmHg (goal <140 mmHg). In patients "
            "aged 18 years or older with diabetes or chronic kidney disease (CKD), initiate "
            "treatment at SBP ≥140 mmHg or DBP ≥90 mmHg and treat to goals of SBP <140 mmHg "
            "and DBP <90 mmHg."
        ),
        "source_type": "guideline",
        "source_id": "JNC-8",
        "page_or_section": "Table 1: Thresholds and Goals for Pharmacologic BP Treatment",
        "field_or_chunk_id": "jnc8-table1-thresholds-goals",
    },
    {
        "text": (
            "In the general nonblack population, including those with diabetes, initial "
            "antihypertensive treatment should include a thiazide-type diuretic, calcium "
            "channel blocker (CCB), ACE inhibitor (ACEI), or angiotensin receptor blocker "
            "(ARB). In the general black population, including those with diabetes, initial "
            "treatment should include a thiazide-type diuretic or CCB. In all patients with "
            "CKD, initial or add-on antihypertensive treatment should include an ACEI or ARB "
            "to improve kidney outcomes, regardless of race or diabetes status."
        ),
        "source_type": "guideline",
        "source_id": "JNC-8",
        "page_or_section": "Table 5: Drug Selection for Hypertension Treatment",
        "field_or_chunk_id": "jnc8-table5-drug-selection",
    },
    {
        "text": (
            "The primary goal of hypertension treatment in adults is to reduce cardiovascular "
            "and cerebrovascular events, heart failure, and kidney disease. If the BP goal is "
            "not reached within one month of treatment, increase the dose of the initial drug "
            "or add a second drug. If the BP goal cannot be reached with two drugs, add and "
            "titrate a third drug. Do not use an ACEI and an ARB together in the same patient."
        ),
        "source_type": "guideline",
        "source_id": "JNC-8",
        "page_or_section": "Recommendations 7–9: Treatment Strategy",
        "field_or_chunk_id": "jnc8-recs7-9-treatment-strategy",
    },

    # ── USPSTF Recommendations Summary ─────────────────────────────────────
    {
        "text": (
            "The USPSTF recommends screening for prediabetes and type 2 diabetes in adults "
            "aged 35 to 70 years who have overweight or obesity (BMI ≥25 kg/m²). Clinicians "
            "should offer or refer patients with prediabetes to effective preventive "
            "interventions. Screening can begin before age 35 for persons at higher risk "
            "(e.g., family history of diabetes, history of gestational diabetes). "
            "Grade B Recommendation (2021)."
        ),
        "source_type": "guideline",
        "source_id": "USPSTF-2024",
        "page_or_section": "Prediabetes and Type 2 Diabetes Screening",
        "field_or_chunk_id": "uspstf-diabetes-screening",
    },
    {
        "text": (
            "The USPSTF recommends screening for hypertension in adults 18 years or older. "
            "Obtain measurements outside of the clinical setting (ambulatory or home BP "
            "monitoring) for diagnostic confirmation before starting treatment. Screening "
            "interval: annually for adults with BP 130–139/85–89 mmHg; every 3–5 years for "
            "adults with normal BP and no risk factors. Grade A Recommendation (2021)."
        ),
        "source_type": "guideline",
        "source_id": "USPSTF-2024",
        "page_or_section": "Hypertension in Adults: Screening",
        "field_or_chunk_id": "uspstf-hypertension-screening",
    },
    {
        "text": (
            "The USPSTF recommends prescribing a statin for the primary prevention of CVD "
            "events and mortality for adults aged 40 to 75 years who have 1 or more CVD risk "
            "factors (dyslipidemia, diabetes, hypertension, or smoking) and an estimated "
            "10-year CVD event risk of 10% or greater. The decision to initiate a statin for "
            "adults with a 10-year CVD risk of 7.5–10% should be individualized. "
            "Grade B Recommendation (2022)."
        ),
        "source_type": "guideline",
        "source_id": "USPSTF-2024",
        "page_or_section": "Statin Use for Primary Prevention of CVD Events",
        "field_or_chunk_id": "uspstf-statin-cvd-prevention",
    },
]
