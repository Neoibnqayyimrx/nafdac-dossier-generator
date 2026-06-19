"""
smpc_pil_generator.py
=====================
Generates the Summary of Product Characteristics (SmPC) and
Patient Information Leaflet (PIL) for NAFDAC CTD Module 1.3.

Both documents follow the WHO/ICH mandated section structure
and are populated from the resolved spec (spec_resolver output).

SmPC structure (WHO/NAFDAC format)
-----------------------------------
  1.  Name of the Medicinal Product
  2.  Qualitative and Quantitative Composition
  3.  Pharmaceutical Form
  4.  Clinical Particulars
      4.1  Therapeutic indications
      4.2  Posology and method of administration
      4.3  Contraindications
      4.4  Special warnings and precautions
      4.5  Interaction with other medicinal products
      4.6  Fertility, pregnancy and lactation
      4.7  Effects on ability to drive
      4.8  Undesirable effects
      4.9  Overdose
  5.  Pharmacological Properties
      5.1  Pharmacodynamic properties
      5.2  Pharmacokinetic properties
      5.3  Preclinical safety data
  6.  Pharmaceutical Particulars
      6.1  List of excipients
      6.2  Incompatibilities
      6.3  Shelf life
      6.4  Special precautions for storage
      6.5  Nature and contents of container
      6.6  Special precautions for disposal
  7.  Marketing Authorisation Holder
  8.  Marketing Authorisation Number
  9.  Date of First Authorisation / Renewal
  10. Date of Revision of the Text

PIL structure (WHO/NAFDAC patient-friendly format)
---------------------------------------------------
  1.  What X is and what it is used for
  2.  What you need to know before you take X
  3.  How to take X
  4.  Possible side effects
  5.  How to store X
  6.  Contents of the pack and other information

Usage
-----
  from smpc_pil_generator import generate_smpc, generate_pil

  generate_smpc("submissions/Amlodipine_Besylate_10mg_Tablets", resolved_spec)
  generate_pil("submissions/Amlodipine_Besylate_10mg_Tablets", resolved_spec)

CLI (via cli.py)
----------------
  python cli.py generate-smpc --submission submissions/Amlodipine_Besylate_10mg_Tablets --drug-spec "amlodipine besilate"
  python cli.py generate-pil  --submission submissions/Amlodipine_Besylate_10mg_Tablets --drug-spec "amlodipine besilate"
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.resolve()

# ── Drug class knowledge base (extend as needed) ───────────────────────────────
# Maps drug name keywords → clinical data template
_DRUG_PROFILES = {
    "amlodipine": {
        "atc_code":       "C08CA01",
        "class":          "Calcium channel blocker (dihydropyridine)",
        "indications":    "Hypertension and stable angina pectoris. Prevention of myocardial infarction in patients with coronary artery disease.",
        "mechanism":      "Amlodipine is a calcium ion influx inhibitor (slow-channel blocker or calcium ion antagonist) that inhibits the transmembrane influx of calcium ions into cardiac and vascular smooth muscle. It acts directly on vascular smooth muscle cells to cause a reduction in peripheral vascular resistance and reduction in blood pressure.",
        "pk_absorption":  "After oral administration, amlodipine is well absorbed with peak plasma concentrations reached 6-12 hours after administration. The absolute bioavailability is between 64% and 80%.",
        "pk_distribution": "The volume of distribution is approximately 21 L/kg. Plasma protein binding is approximately 97.5%.",
        "pk_metabolism":  "Amlodipine is extensively metabolised by the liver to inactive metabolites. Approximately 10% of the parent compound and 60% of the metabolites are excreted in urine.",
        "pk_elimination": "The elimination half-life is 35-50 hours, which is consistent with once-daily dosing.",
        "standard_dose":  "5–10 mg once daily",
        "max_dose":       "10 mg once daily",
        "contraindications": "Hypersensitivity to amlodipine, other dihydropyridines, or any of the excipients. Severe hypotension. Shock (including cardiogenic shock). Left ventricular outflow tract obstruction.",
        "warnings":       "Use with caution in patients with heart failure, hepatic impairment, or elderly patients. May cause ankle oedema.",
        "interactions":   "CYP3A4 inhibitors (e.g., ketoconazole, itraconazole, ritonavir) may increase amlodipine exposure. CYP3A4 inducers (e.g., rifampicin) may decrease amlodipine levels. Concomitant use with other antihypertensives may have additive blood pressure lowering effects.",
        "pregnancy":      "Not recommended during pregnancy. Use contraception during treatment. Animal studies have shown reproductive toxicity.",
        "lactation":      "Amlodipine is excreted in breast milk. A decision must be made whether to discontinue breast-feeding or to discontinue/abstain from amlodipine therapy.",
        "driving":        "Amlodipine may mildly or moderately influence the ability to drive and use machines. Patients should be cautious if they experience dizziness or fatigue.",
        "side_effects":   "Very common (≥1/10): oedema. Common (≥1/100 to <1/10): headache, dizziness, somnolence, palpitations, flushing, abdominal pain, nausea, ankle swelling, fatigue. Uncommon: insomnia, mood changes, tremor, dyspepsia, alopecia, purpura, skin discolouration, hyperhidrosis.",
        "overdose":       "Overdose may result in excessive peripheral vasodilation with marked hypotension and possibly reflex tachycardia. Clinically significant hypotension requires active cardiovascular support including frequent monitoring, elevation of extremities, and attention to circulating fluid volume and urine output.",
        "shelf_life":     "3 years",
        "storage":        "Store below 30°C. Keep in the original container.",
        "container":      "PVC/Aluminium blister packs or HDPE bottles.",
    },
    "metformin": {
        "atc_code":       "A10BA02",
        "class":          "Biguanide antidiabetic",
        "indications":    "Treatment of type 2 diabetes mellitus, particularly in overweight patients, when diet alone and exercise have not been sufficient to control blood glucose.",
        "mechanism":      "Metformin decreases hepatic glucose production, decreases intestinal absorption of glucose, and improves insulin sensitivity by increasing peripheral glucose uptake and utilisation.",
        "standard_dose":  "500–850 mg 2-3 times daily with meals",
        "max_dose":       "3000 mg daily",
        "contraindications": "Hypersensitivity to metformin or any excipient. Renal impairment (eGFR <30 mL/min/1.73m²). Diabetic ketoacidosis. Hepatic impairment. Acute or chronic conditions that may cause tissue hypoxia.",
        "warnings":       "Risk of lactic acidosis. Suspend treatment before iodinated contrast imaging. Monitor renal function regularly.",
        "side_effects":   "Very common: gastrointestinal disorders (nausea, vomiting, diarrhoea, abdominal pain, loss of appetite). Rare: lactic acidosis, vitamin B12 deficiency.",
        "shelf_life":     "3 years",
        "storage":        "Store below 25°C. Keep in the original container.",
        "container":      "PVC/Aluminium blister packs.",
    },
}


def _get_drug_profile(drug_name: str) -> dict:
    """Get the clinical profile for a drug, matching by keyword."""
    dn = drug_name.lower()
    for key, profile in _DRUG_PROFILES.items():
        if key in dn:
            return profile
    # Return a generic template
    return {
        "atc_code":       "[ATC CODE]",
        "class":          "[PHARMACOLOGICAL CLASS]",
        "indications":    "[TO BE COMPLETED — Insert approved therapeutic indications]",
        "mechanism":      "[TO BE COMPLETED — Insert mechanism of action]",
        "pk_absorption":  "[TO BE COMPLETED — Insert absorption data]",
        "pk_distribution": "[TO BE COMPLETED — Insert distribution data]",
        "pk_metabolism":  "[TO BE COMPLETED — Insert metabolism data]",
        "pk_elimination": "[TO BE COMPLETED — Insert elimination data]",
        "standard_dose":  "[TO BE COMPLETED]",
        "max_dose":       "[TO BE COMPLETED]",
        "contraindications": "[TO BE COMPLETED — Insert contraindications]",
        "warnings":       "[TO BE COMPLETED — Insert warnings and precautions]",
        "interactions":   "[TO BE COMPLETED — Insert drug interactions]",
        "pregnancy":      "[TO BE COMPLETED — Insert pregnancy information]",
        "lactation":      "[TO BE COMPLETED — Insert lactation information]",
        "driving":        "[TO BE COMPLETED]",
        "side_effects":   "[TO BE COMPLETED — Insert undesirable effects]",
        "overdose":       "[TO BE COMPLETED — Insert overdose management]",
        "shelf_life":     "3 years",
        "storage":        "[TO BE COMPLETED — Insert storage conditions]",
        "container":      "[TO BE COMPLETED — Insert container description]",
    }


def _v(fields: dict, field: str, default: str = "[NOT AVAILABLE]") -> str:
    """Get field value from resolved spec."""
    entry = fields.get(field, {})
    val   = entry.get("value") if isinstance(entry, dict) else entry
    if val is None:
        return default
    if isinstance(val, dict):
        return json.dumps(val)
    if isinstance(val, list):
        return "; ".join(str(i) for i in val[:3]) if val else default
    return str(val).strip()


def _je(text: str) -> str:
    """Escape string for JS template literal."""
    return (str(text)
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
            .replace("\n", " ")
            .replace("\r", ""))


def _run_node(js_code: str, out_path: Path) -> bool:
    """Run JS code via Node.js to generate DOCX."""
    tmp_js = _PROJECT_ROOT / f"_tmp_docgen_{out_path.stem}.js"
    tmp_js.write_text(js_code, encoding="utf-8")
    try:
        result = subprocess.run(
            ["node", str(tmp_js)],
            capture_output=True, text=True, timeout=60,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            log.error("Node.js error for %s:\n%s", out_path.name, result.stderr[:600])
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.error("Node.js failed for %s: %s", out_path.name, exc)
        return False
    finally:
        tmp_js.unlink(missing_ok=True)


# ── Shared JS style block ──────────────────────────────────────────────────────
_STYLES_JS = """
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: "1F3864" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "2E75B6" },
        paragraph: { spacing: { before: 180, after: 90 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: "404040" },
        paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 2 } },
    ]
  },"""

_A4_JS = """
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1440, right: 1080, bottom: 1440, left: 1800 }
      }
    },"""


def _hf_js(product_name: str, section: str) -> str:
    p = _je(product_name)
    s = _je(section)
    return f"""
    headers: {{ default: new Header({{ children: [new Paragraph({{
      border: {{ bottom: {{ style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 }} }},
      children: [
        new TextRun({{ text: "{p}", bold: true, size: 18 }}),
        new TextRun({{ text: "  |  {s}", size: 18, color: "595959" }}),
      ]
    }})] }}) }},
    footers: {{ default: new Footer({{ children: [new Paragraph({{
      border: {{ top: {{ style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 }} }},
      children: [
        new TextRun({{ text: "CONFIDENTIAL — NAFDAC Submission    Page ", size: 16, color: "808080" }}),
        new TextRun({{ children: [PageNumber.CURRENT], size: 16, color: "808080" }}),
      ]
    }})] }}) }},"""


def _para_js(text: str, bold: bool = False, indent: int = 0) -> str:
    b = "true" if bold else "false"
    ind = f", indent: {{ left: {indent} }}" if indent else ""
    return f'new Paragraph({{ {ind} children: [new TextRun({{ text: `{_je(text)}`, bold: {b}, size: 22 }})] }}),'


def _h1(text: str) -> str:
    return f'new Paragraph({{ heading: HeadingLevel.HEADING_1, children: [new TextRun("{_je(text)}")] }}),'


def _h2(text: str) -> str:
    return f'new Paragraph({{ heading: HeadingLevel.HEADING_2, children: [new TextRun("{_je(text)}")] }}),'


def _h3(text: str) -> str:
    return f'new Paragraph({{ heading: HeadingLevel.HEADING_3, children: [new TextRun("{_je(text)}")] }}),'


def _blank() -> str:
    return 'new Paragraph({ children: [] }),'


def _bullet(text: str) -> str:
    return f'new Paragraph({{ bullet: {{ level: 0 }}, children: [new TextRun({{ text: `{_je(text)}`, size: 22 }})] }}),'


# ═══════════════════════════════════════════════════════════════════════════════
# SmPC GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_smpc(
    submission_root: str,
    resolved_spec: Optional[dict] = None,
    drug_name_for_spec: Optional[str] = None,
) -> bool:
    """
    Generate the SmPC (Summary of Product Characteristics) DOCX.
    Saved to Module1/1.3_Product_Information/1.3.1_SmPC/smpc.docx
    """
    from nafdac_structure import load_manifest, config_from_manifest

    manifest = load_manifest(submission_root)
    config   = config_from_manifest(submission_root)

    # Load resolved spec
    fields = {}
    if resolved_spec:
        fields = resolved_spec.get("fields", {})
    else:
        drug_key  = drug_name_for_spec or config.drug_name
        import re
        spec_slug = re.sub(r"[^a-z0-9]+", "-", drug_key.lower()).strip("-")
        spec_path = Path("pharmacopoeia_db") / "resolved" / f"{spec_slug}.json"
        if spec_path.exists():
            data   = json.loads(spec_path.read_text(encoding="utf-8"))
            fields = data.get("fields", {})

    dp       = _get_drug_profile(config.drug_name)
    drug     = _je(_v(fields, "drug_name", config.drug_name))
    prod     = _je(config.full_product_name)
    strength = _je(config.strength)
    form     = _je(config.dosage_form)
    formula  = _je(_v(fields, "molecular_formula"))
    mw       = _je(str(_v(fields, "molecular_weight")))
    desc     = _je(_v(fields, "description"))
    storage  = _je(dp.get("storage", _v(fields, "storage")))
    applicant = _je(config.applicant)
    mfr       = _je(config.manufacturer)
    date_str  = _je(config.submission_date)

    out_path = (Path(submission_root) / "Module1" / "1.3_Product_Information"
                / "1.3.1_SmPC" / "smpc.docx")

    children = "\n      ".join([
        # Section 1
        _h1("1. NAME OF THE MEDICINAL PRODUCT"),
        _para_js(f"{prod}"),
        _blank(),

        # Section 2
        _h1("2. QUALITATIVE AND QUANTITATIVE COMPOSITION"),
        _para_js(f"Each tablet contains {strength} of {drug} (as {drug})."),
        _blank(),
        _para_js("Excipients with known effect:", bold=True),
        _para_js("For the full list of excipients, see section 6.1."),
        _blank(),

        # Section 3
        _h1("3. PHARMACEUTICAL FORM"),
        _para_js(f"{form}. {desc}."),
        _blank(),

        # Section 4
        _h1("4. CLINICAL PARTICULARS"),
        _h2("4.1 Therapeutic indications"),
        _para_js(dp.get("indications", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.2 Posology and method of administration"),
        _para_js("Posology", bold=True),
        _para_js(f"Adults: {dp.get('standard_dose', '[TO BE COMPLETED]')}. The maximum recommended dose is {dp.get('max_dose', '[TO BE COMPLETED]')}."),
        _para_js("Elderly patients", bold=True),
        _para_js("In general, dose selection for elderly patients should be cautious, starting at the low end of the dosing range."),
        _para_js("Paediatric population", bold=True),
        _para_js("The safety and efficacy in children below 18 years has not been established."),
        _para_js("Method of administration", bold=True),
        _para_js("For oral use. The tablets should be swallowed whole with water."),
        _blank(),

        _h2("4.3 Contraindications"),
        _para_js(dp.get("contraindications", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.4 Special warnings and precautions for use"),
        _para_js(dp.get("warnings", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.5 Interaction with other medicinal products and other forms of interaction"),
        _para_js(dp.get("interactions", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.6 Fertility, pregnancy and lactation"),
        _para_js("Pregnancy", bold=True),
        _para_js(dp.get("pregnancy", "[TO BE COMPLETED]")),
        _para_js("Breast-feeding", bold=True),
        _para_js(dp.get("lactation", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.7 Effects on ability to drive and use machines"),
        _para_js(dp.get("driving", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.8 Undesirable effects"),
        _para_js(dp.get("side_effects", "[TO BE COMPLETED]")),
        _blank(),

        _h2("4.9 Overdose"),
        _para_js(dp.get("overdose", "[TO BE COMPLETED]")),
        _blank(),

        # Section 5
        _h1("5. PHARMACOLOGICAL PROPERTIES"),
        _h2("5.1 Pharmacodynamic properties"),
        _para_js(f"Pharmacotherapeutic group: {dp.get('class', '[TO BE COMPLETED]')}"),
        _para_js(f"ATC code: {dp.get('atc_code', '[TO BE COMPLETED]')}"),
        _blank(),
        _para_js("Mechanism of action", bold=True),
        _para_js(dp.get("mechanism", "[TO BE COMPLETED]")),
        _blank(),

        _h2("5.2 Pharmacokinetic properties"),
        _para_js("Absorption", bold=True),
        _para_js(dp.get("pk_absorption", "[TO BE COMPLETED]")),
        _para_js("Distribution", bold=True),
        _para_js(dp.get("pk_distribution", "[TO BE COMPLETED]")),
        _para_js("Metabolism", bold=True),
        _para_js(dp.get("pk_metabolism", "[TO BE COMPLETED]")),
        _para_js("Elimination", bold=True),
        _para_js(dp.get("pk_elimination", "[TO BE COMPLETED]")),
        _blank(),

        _h2("5.3 Preclinical safety data"),
        _para_js("Non-clinical data reveal no special hazard for humans based on conventional studies of safety pharmacology, repeated dose toxicity, genotoxicity, carcinogenic potential, and toxicity to reproduction."),
        _blank(),

        # Section 6
        _h1("6. PHARMACEUTICAL PARTICULARS"),
        _h2("6.1 List of excipients"),
        _para_js("Microcrystalline cellulose, calcium hydrogen phosphate, sodium starch glycolate, magnesium stearate, film coat (Opadry White)."),
        _blank(),

        _h2("6.2 Incompatibilities"),
        _para_js("Not applicable."),
        _blank(),

        _h2("6.3 Shelf life"),
        _para_js(dp.get("shelf_life", "3 years")),
        _blank(),

        _h2("6.4 Special precautions for storage"),
        _para_js(storage),
        _blank(),

        _h2("6.5 Nature and contents of container"),
        _para_js(dp.get("container", "[TO BE COMPLETED]")),
        _blank(),

        _h2("6.6 Special precautions for disposal"),
        _para_js("No special requirements for disposal. Any unused medicinal product or waste material should be disposed of in accordance with local requirements."),
        _blank(),

        # Section 7-10
        _h1("7. MARKETING AUTHORISATION HOLDER"),
        _para_js(applicant),
        _blank(),

        _h1("8. MARKETING AUTHORISATION NUMBER(S)"),
        _para_js("[TO BE ASSIGNED BY NAFDAC]"),
        _blank(),

        _h1("9. DATE OF FIRST AUTHORISATION/RENEWAL OF THE AUTHORISATION"),
        _para_js("[TO BE COMPLETED AFTER APPROVAL]"),
        _blank(),

        _h1("10. DATE OF REVISION OF THE TEXT"),
        _para_js(date_str),
    ])

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Header, Footer,
         HeadingLevel, AlignmentType, BorderStyle, PageNumber }} = require('docx');
const fs = require('fs');

const doc = new Document({{
  {_STYLES_JS}
  sections: [{{
    {_A4_JS}
    {_hf_js(config.full_product_name, 'Summary of Product Characteristics')}
    children: [
      {children}
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('SmPC generated: ' + buf.length + ' bytes');
}});
"""
    ok = _run_node(js, out_path)
    if ok:
        print(f"  ✓ SmPC generated: {out_path}")
    else:
        print(f"  ✗ SmPC generation failed")
    return ok


# ═══════════════════════════════════════════════════════════════════════════════
# PIL GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pil(
    submission_root: str,
    resolved_spec: Optional[dict] = None,
    drug_name_for_spec: Optional[str] = None,
) -> bool:
    """
    Generate the PIL (Patient Information Leaflet) DOCX.
    Saved to Module1/1.3_Product_Information/1.3.2_PIL/pil.docx
    """
    from nafdac_structure import load_manifest, config_from_manifest

    manifest = load_manifest(submission_root)
    config   = config_from_manifest(submission_root)

    fields = {}
    if resolved_spec:
        fields = resolved_spec.get("fields", {})
    else:
        drug_key  = drug_name_for_spec or config.drug_name
        import re
        spec_slug = re.sub(r"[^a-z0-9]+", "-", drug_key.lower()).strip("-")
        spec_path = Path("pharmacopoeia_db") / "resolved" / f"{spec_slug}.json"
        if spec_path.exists():
            data   = json.loads(spec_path.read_text(encoding="utf-8"))
            fields = data.get("fields", {})

    dp       = _get_drug_profile(config.drug_name)
    drug     = _je(_v(fields, "drug_name", config.drug_name))
    prod     = _je(config.full_product_name)
    strength = _je(config.strength)
    form     = _je(config.dosage_form.lower())
    storage  = _je(dp.get("storage", _v(fields, "storage")))
    applicant = _je(config.applicant)

    out_path = (Path(submission_root) / "Module1" / "1.3_Product_Information"
                / "1.3.2_PIL" / "pil.docx")

    children = "\n      ".join([
        # Header box
        _para_js(f"PACKAGE LEAFLET: INFORMATION FOR THE USER", bold=True),
        _para_js(f"{prod}"),
        _para_js(f"Read all of this leaflet carefully before you start taking this medicine because it contains important information for you."),
        _bullet("Keep this leaflet. You may need to read it again."),
        _bullet("If you have any further questions, ask your doctor or pharmacist."),
        _bullet("This medicine has been prescribed for you only. Do not pass it on to others."),
        _bullet("If you get any side effects, talk to your doctor or pharmacist."),
        _blank(),

        # Section 1
        _h1(f"1. What {prod} is and what it is used for"),
        _para_js(f"{prod} contains {strength} of {drug}."),
        _blank(),
        _para_js(dp.get("indications", "[TO BE COMPLETED]")),
        _blank(),

        # Section 2
        _h1(f"2. What you need to know before you take {prod}"),
        _h2(f"Do NOT take {prod} if you:"),
        _para_js(dp.get("contraindications", "[TO BE COMPLETED]").replace(". ", "\n").split("\n")[0]),
        _blank(),

        _h2("Warnings and precautions"),
        _para_js("Talk to your doctor or pharmacist before taking this medicine."),
        _para_js(dp.get("warnings", "[TO BE COMPLETED]")),
        _blank(),

        _h2("Other medicines and this medicine"),
        _para_js("Tell your doctor or pharmacist if you are taking, have recently taken or might take any other medicines."),
        _para_js(dp.get("interactions", "[TO BE COMPLETED]")),
        _blank(),

        _h2("Pregnancy and breast-feeding"),
        _para_js(dp.get("pregnancy", "[TO BE COMPLETED]")),
        _para_js(dp.get("lactation", "[TO BE COMPLETED]")),
        _blank(),

        _h2("Driving and using machines"),
        _para_js(dp.get("driving", "[TO BE COMPLETED]")),
        _blank(),

        # Section 3
        _h1(f"3. How to take {prod}"),
        _para_js(f"Always take this medicine exactly as your doctor has told you."),
        _blank(),
        _para_js("Adults:", bold=True),
        _para_js(f"The usual dose is {dp.get('standard_dose', '[TO BE COMPLETED]')}. The maximum dose is {dp.get('max_dose', '[TO BE COMPLETED]')}."),
        _blank(),
        _para_js("Method of administration:", bold=True),
        _para_js(f"Swallow the {form} whole with a glass of water. This medicine can be taken with or without food."),
        _blank(),
        _para_js("If you take more than you should:", bold=True),
        _para_js(dp.get("overdose", "Contact your doctor or nearest hospital emergency department immediately.")[:200]),
        _blank(),
        _para_js("If you forget to take this medicine:", bold=True),
        _para_js("Take it as soon as you remember. However, if it is nearly time for your next dose, skip the missed dose and take the next one at the normal time. Do not take a double dose to make up for a forgotten dose."),
        _blank(),

        # Section 4
        _h1("4. Possible side effects"),
        _para_js("Like all medicines, this medicine can cause side effects, although not everybody gets them."),
        _blank(),
        _para_js(dp.get("side_effects", "[TO BE COMPLETED]")),
        _blank(),
        _para_js("Reporting of side effects", bold=True),
        _para_js("If you get any side effects, talk to your doctor or pharmacist. You can also report side effects directly to NAFDAC. By reporting side effects you can help provide more information on the safety of this medicine."),
        _blank(),

        # Section 5
        _h1(f"5. How to store {prod}"),
        _para_js(f"Keep this medicine out of the sight and reach of children."),
        _blank(),
        _para_js(storage),
        _blank(),
        _para_js("Do not use this medicine after the expiry date which is stated on the carton and blister after EXP. The expiry date refers to the last day of that month."),
        _blank(),
        _para_js("Do not throw away any medicines via wastewater or household waste. Ask your pharmacist how to throw away medicines you no longer use. These measures will help protect the environment."),
        _blank(),

        # Section 6
        _h1("6. Contents of the pack and other information"),
        _h2(f"What {prod} contains"),
        _para_js(f"The active substance is {drug} {strength}."),
        _para_js("The other ingredients are: microcrystalline cellulose, calcium hydrogen phosphate, sodium starch glycolate, magnesium stearate, film coat (Opadry White)."),
        _blank(),

        _h2(f"What {prod} looks like and contents of the pack"),
        _para_js("White to off-white film-coated tablets. Available in blister packs."),
        _blank(),

        _h2("Marketing Authorisation Holder and Manufacturer"),
        _para_js(applicant),
        _blank(),

        _para_js("This leaflet was last approved: [DATE]"),
    ])

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Header, Footer,
         HeadingLevel, AlignmentType, BorderStyle, PageNumber }} = require('docx');
const fs = require('fs');

const doc = new Document({{
  {_STYLES_JS}
  sections: [{{
    {_A4_JS}
    {_hf_js(config.full_product_name, 'Patient Information Leaflet')}
    children: [
      {children}
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('PIL generated: ' + buf.length + ' bytes');
}});
"""
    ok = _run_node(js, out_path)
    if ok:
        print(f"  ✓ PIL generated: {out_path}")
    else:
        print(f"  ✗ PIL generation failed")
    return ok