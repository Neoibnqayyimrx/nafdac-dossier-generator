"""
placeholder_generator.py — Phase 8 (Complete)
Generates professional placeholder DOCX files for all CTD sections
that require manufacturer/applicant-supplied data.

Every placeholder contains:
  - Correct ICH CTD section heading
  - Yellow warning box: DRAFT — REQUIRES APPLICANT DATA
  - Guidance text explaining what the section must contain (per ICH/NAFDAC)
  - Required information table with pending status fields
  - Footer: DRAFT — NOT FOR SUBMISSION UNTIL COMPLETED

For N/A sections (Module 4 for generics):
  - Green box: NOT APPLICABLE + regulatory basis

Dependencies:
  - docx (npm: docx) must be installed: npm install docx
  - Node.js must be available on PATH
  - module_generators.py must define SubmissionConfig and _v()
"""

from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).parent.resolve()


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL HELPER — mirrors module_generators._v() to avoid circular imports
# ═══════════════════════════════════════════════════════════════════════════════

def _v(fields: dict, key: str, default: str = "") -> str:
    """Return fields[key] if present and non-empty, else default."""
    if fields and key in fields and fields[key]:
        return str(fields[key])
    return default


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _js_escape(text: str) -> str:
    """Escape a string for safe embedding inside a JS template literal."""
    return (text
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
            .replace("\n", " ")
            .replace("\r", "")
            .replace('"', '\\"'))


def _generate_docx_from_js(js_code: str, out_path: Path) -> bool:
    """Write js_code to a temp file, execute with Node, return success."""
    tmp_js = _PROJECT_ROOT / f"_tmp_placeholder_{out_path.stem}.js"
    tmp_js.write_text(js_code, encoding="utf-8")
    try:
        result = subprocess.run(
            ["node", str(tmp_js)],
            capture_output=True, text=True, timeout=60,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            print(f"    Node.js error for {out_path.name}: {result.stderr[:400]}")
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return True
    except FileNotFoundError:
        print("    ERROR: Node.js not found on PATH. Install Node.js to generate DOCX files.")
        return False
    except Exception as e:
        print(f"    Error generating {out_path.name}: {e}")
        return False
    finally:
        tmp_js.unlink(missing_ok=True)


# ─── shared JS fragments ──────────────────────────────────────────────────────

_STYLES_JS = """
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "1F3864" },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: "404040" },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ]
  },"""

_A4_JS = """
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1440, right: 1080, bottom: 1440, left: 1800 }
      }
    },"""


# ═══════════════════════════════════════════════════════════════════════════════
# CORE GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_placeholder(
    out_path: Path,
    section_id: str,
    section_title: str,
    config: Any,
    guidance_text: str,
    required_fields: list[tuple[str, str]],
    is_not_applicable: bool = False,
    na_reason: str = "",
    extra_sections: list[tuple[str, str]] | None = None,
) -> bool:
    """
    Generate a professional placeholder DOCX.

    Args:
        out_path:           Output file path.
        section_id:         ICH CTD section number e.g. "3.2.S.2"
        section_title:      Full section title.
        config:             SubmissionConfig instance.
        guidance_text:      What this section must contain per ICH/NAFDAC guidelines.
        required_fields:    List of (field_name, description) tuples for the status table.
        is_not_applicable:  If True, shows N/A notice instead of placeholder warning.
        na_reason:          Regulatory basis for N/A.
        extra_sections:     List of (subsection_heading, guidance_text) for subsections.
    """
    prod   = _js_escape(config.full_product_name)
    drug   = _js_escape(config.drug_name)
    appl   = _js_escape(config.applicant)
    sec_id = _js_escape(section_id)
    sec_t  = _js_escape(section_title)
    guid   = _js_escape(guidance_text)
    na_r   = _js_escape(na_reason)
    out_p  = str(out_path).replace("\\", "/")

    # Build required-fields table rows
    field_rows_js = ""
    for fname, fdesc in (required_fields or []):
        fn = _js_escape(fname)
        fd = _js_escape(fdesc)
        field_rows_js += f"""
          new TableRow({{ children: [
            dCell("{fn}", 2800),
            dCell("{fd}", 4500),
            dCell("[ ] Pending", 1726),
          ]}}),"""

    # Build extra subsection paragraphs
    extra_js = ""
    for sub_heading, sub_text in (extra_sections or []):
        sh = _js_escape(sub_heading)
        st = _js_escape(sub_text)
        extra_js += f"""
      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("{sh}")] }}),
      new Paragraph({{ children: [new TextRun({{ text: "{st}", italics: true, color: "595959" }})] }}),
      new Paragraph({{ children: [] }}),"""

    # Notice box
    if is_not_applicable:
        notice_color       = "E2EFDA"
        notice_text_color  = "375A23"
        notice_label       = "NOT APPLICABLE"
        notice_detail      = na_r or "This section is not applicable for multisource (generic) pharmaceutical products per NAFDAC guidelines."
    else:
        notice_color       = "FFF2CC"
        notice_text_color  = "7F6000"
        notice_label       = "PLACEHOLDER — APPLICANT ACTION REQUIRED"
        notice_detail      = "This document is a structured placeholder. The applicant must supply the required information before submission to NAFDAC."

    nl = _js_escape(notice_label)
    nd = _js_escape(notice_detail)

    required_block_js = "" if is_not_applicable else f"""
      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("Required Information")] }}),
      new Paragraph({{ children: [new TextRun({{ text: "The following information must be provided by the applicant. All fields marked Pending must be completed before submission.", size: 20 }})] }}),
      new Paragraph({{ children: [] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [2800, 4500, 1726],
        rows: [
          new TableRow({{ children: [
            hCell("Information Required", 2800),
            hCell("Description / Guidance", 4500),
            hCell("Status", 1726),
          ]}}),
          {field_rows_js}
        ]
      }}),
      new Paragraph({{ children: [] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("Submission Checklist")] }}),
      new Paragraph({{ children: [new TextRun("Before submitting this section to NAFDAC, confirm:")] }}),
      new Paragraph({{ children: [new TextRun("[ ]  All required information in the table above has been provided")] }}),
      new Paragraph({{ children: [new TextRun("[ ]  All data has been reviewed and approved by the Qualified Person / Responsible Pharmacist")] }}),
      new Paragraph({{ children: [new TextRun("[ ]  Supporting documents and raw data are available for inspection")] }}),
      new Paragraph({{ children: [new TextRun("[ ]  All references to pharmacopoeial methods specify the edition used")] }}),
    """

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         Header, Footer, HeadingLevel, AlignmentType,
         BorderStyle, WidthType, ShadingType, PageNumber }} = require('docx');
const fs = require('fs');

const bord = {{ style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" }};
const borders = {{ top: bord, bottom: bord, left: bord, right: bord }};
const noticeBord = {{ style: BorderStyle.SINGLE, size: 4, color: "{notice_text_color}" }};
const noticeBorders = {{ top: noticeBord, bottom: noticeBord, left: noticeBord, right: noticeBord }};

const cellOpts = (w) => ({{ borders, width: {{ size: w, type: WidthType.DXA }},
  margins: {{ top: 80, bottom: 80, left: 120, right: 120 }} }});
const hCell = (text, w) => new TableCell({{ ...cellOpts(w),
  shading: {{ fill: "D5E8F0", type: ShadingType.CLEAR }},
  children: [new Paragraph({{ children: [new TextRun({{ text, bold: true, size: 20 }})] }})] }});
const dCell = (text, w) => new TableCell({{ ...cellOpts(w),
  children: [new Paragraph({{ children: [new TextRun({{ text, size: 20 }})] }})] }});
const noticeCell = (text, w) => new TableCell({{
  borders: noticeBorders,
  width: {{ size: w, type: WidthType.DXA }},
  shading: {{ fill: "{notice_color}", type: ShadingType.CLEAR }},
  margins: {{ top: 120, bottom: 120, left: 180, right: 180 }},
  children: [new Paragraph({{ children: [new TextRun({{ text, bold: true, size: 22, color: "{notice_text_color}" }})] }}),
             new Paragraph({{ children: [new TextRun({{ text: "{nd}", size: 20, color: "{notice_text_color}" }})] }})]
}});

const doc = new Document({{
  {_STYLES_JS}
  sections: [{{
    {_A4_JS}
    headers: {{
      default: new Header({{
        children: [new Paragraph({{
          border: {{ bottom: {{ style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 }} }},
          children: [
            new TextRun({{ text: "{prod}", bold: true, size: 18, font: "Arial" }}),
            new TextRun({{ text: "  |  Section {sec_id} — {sec_t}", size: 18, font: "Arial", color: "595959" }}),
          ]
        }})]
      }})
    }},
    footers: {{
      default: new Footer({{
        children: [new Paragraph({{
          border: {{ top: {{ style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 }} }},
          children: [
            new TextRun({{ text: "DRAFT — NOT FOR SUBMISSION UNTIL COMPLETED    Applicant: {appl}    Page ", size: 16, font: "Arial", color: "808080" }}),
            new TextRun({{ children: [PageNumber.CURRENT], size: 16, font: "Arial", color: "808080" }}),
          ]
        }})]
      }})
    }},
    children: [
      new Paragraph({{ heading: HeadingLevel.HEADING_1,
        children: [new TextRun("{sec_id}  {sec_t}")] }}),

      new Paragraph({{ children: [new TextRun({{ text: "Product: ", bold: true }}), new TextRun("{prod}")] }}),
      new Paragraph({{ children: [new TextRun({{ text: "Drug substance: ", bold: true }}), new TextRun("{drug}")] }}),
      new Paragraph({{ children: [new TextRun({{ text: "Applicant: ", bold: true }}), new TextRun("{appl}")] }}),
      new Paragraph({{ children: [] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [9026],
        rows: [new TableRow({{ children: [noticeCell("{nl}", 9026)] }})]
      }}),

      new Paragraph({{ children: [] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("Regulatory Guidance")] }}),
      new Paragraph({{ children: [new TextRun({{ text: "{guid}", italics: {"true" if not is_not_applicable else "false"} }})] }}),
      new Paragraph({{ children: [] }}),

      {extra_js}

      {required_block_js}
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{out_p}", buf);
  console.log('Generated: {out_path.name} (' + buf.length + ' bytes)');
}});
"""
    return _generate_docx_from_js(js, out_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — ADMINISTRATIVE / REGIONAL
# ═══════════════════════════════════════════════════════════════════════════════

def generate_all_admin_placeholders(submission_root: str, config: Any) -> dict:
    """Generate all 18 Module 1.2 administrative placeholder documents."""
    root = Path(submission_root)
    results: dict = {"generated": 0, "failed": 0, "files": []}

    admin_docs = [
        ("1.2.1", "Application Form",
         "The NAFDAC Application Form (Form 5A) must be completed in full. "
         "Available from NAFDAC offices or nafdac.gov.ng.",
         [("Product name", "Full product name as registered"),
          ("Dosage form", "e.g. Tablets, Capsules"),
          ("Strength", "e.g. 10mg"),
          ("Applicant name", "Legal name of applicant company"),
          ("Applicant address", "Full registered address"),
          ("Manufacturer name", "Name of manufacturer"),
          ("Manufacturer address", "Full address of manufacturing site"),
          ("Signature", "Authorised signatory"),
          ("Date", "Date of application")],
         "Module1/1.2_Administrative_Information/1.2.1_Application_Form",
         "1.2.1_application_form.docx"),

        ("1.2.2", "Registration Form",
         "NAFDAC Product Registration Form. Complete all fields accurately.",
         [("Registration category", "e.g. New Product, Variation, Renewal"),
          ("Product type", "e.g. Finished pharmaceutical product"),
          ("Therapeutic category", "ATC classification"),
          ("Route of administration", "e.g. Oral"),
          ("Pack size(s)", "All pack sizes to be registered")],
         "Module1/1.2_Administrative_Information/1.2.2_Registration_Form",
         "1.2.2_registration_form.docx"),

        ("1.2.3", "Certificate of Incorporation",
         "Certified copy of Certificate of Incorporation of the applicant company "
         "issued by the Corporate Affairs Commission (CAC) Nigeria.",
         [("Company name", "Exact legal name as on certificate"),
          ("RC Number", "CAC registration number"),
          ("Date of incorporation", "As on certificate"),
          ("Certified copy", "Must be certified by a notary or CAC")],
         "Module1/1.2_Administrative_Information/1.2.3_Certificate_of_Incorporation",
         "1.2.3_certificate_of_incorporation.docx"),

        ("1.2.4", "Power of Attorney",
         "Notarised Power of Attorney authorising the applicant to act on behalf "
         "of the manufacturer for NAFDAC registration purposes.",
         [("Grantor", "Manufacturer name and address"),
          ("Grantee", "Applicant name and address"),
          ("Scope", "Authority granted for NAFDAC registration"),
          ("Notarisation", "Notarised and apostilled where required"),
          ("Validity period", "Must cover the registration period")],
         "Module1/1.2_Administrative_Information/1.2.4_Power_of_Attorney",
         "1.2.4_power_of_attorney.docx"),

        ("1.2.5", "Notarized Declaration of Applicant",
         "Statutory declaration by the applicant confirming accuracy of all "
         "information submitted in the dossier.",
         [("Declaration text", "Standard NAFDAC declaration wording"),
          ("Signatory", "Authorised officer of applicant company"),
          ("Commissioner for Oaths", "Sworn before a Commissioner for Oaths"),
          ("Date", "Date of declaration")],
         "Module1/1.2_Administrative_Information/1.2.5_Notarized_Declaration",
         "1.2.5_notarized_declaration.docx"),

        ("1.2.6", "Contract Manufacturing Agreement",
         "If product is manufactured under contract, provide the Contract "
         "Manufacturing Agreement between the applicant and manufacturer. "
         "If own manufacture, provide self-declaration.",
         [("Parties", "Manufacturer and applicant names"),
          ("Scope of agreement", "Products covered"),
          ("Quality responsibilities", "Who is responsible for QC/QA"),
          ("Duration", "Agreement validity period"),
          ("Signatures", "Authorised signatories of both parties")],
         "Module1/1.2_Administrative_Information/1.2.6_Contract_Manufacturing",
         "1.2.6_contract_manufacturing_agreement.docx"),

        ("1.2.7", "Certificate of Pharmaceutical Product (CPP)",
         "WHO-format Certificate of Pharmaceutical Product issued by the "
         "regulatory authority of the country of manufacture. "
         "Must be original or certified copy, not older than 3 years.",
         [("Issuing authority", "National regulatory authority of country of manufacture"),
          ("Product name", "As on certificate"),
          ("Manufacturer", "Name and address"),
          ("Market authorisation status", "Whether product is authorised in country of manufacture"),
          ("Certificate date", "Must not be older than 3 years"),
          ("Apostille", "Required for non-Commonwealth countries")],
         "Module1/1.2_Administrative_Information/1.2.7_CPP",
         "1.2.7_certificate_of_pharmaceutical_product.docx"),

        ("1.2.8", "GMP Certificate",
         "Current GMP Certificate issued by the national regulatory authority "
         "of the country of manufacture, or NAFDAC GMP inspection certificate. "
         "Must cover the manufacturing site and product type.",
         [("Issuing authority", "NRA of country of manufacture"),
          ("Manufacturing site", "Name and address of site"),
          ("Scope", "Product types covered by the certificate"),
          ("Issue date", "Date of issuance"),
          ("Expiry date", "Must be current at time of submission"),
          ("Certified copy", "Must be certified")],
         "Module1/1.2_Administrative_Information/1.2.8_GMP_Certificate",
         "1.2.8_gmp_certificate.docx"),

        ("1.2.9", "Manufacturing Authorization",
         "Manufacturing Authorisation (MA) or Manufacturing Licence issued by "
         "the competent authority of the country of manufacture.",
         [("Licence number", "As on document"),
          ("Issuing authority", "Regulatory authority name"),
          ("Holder", "Name of licence holder"),
          ("Activities authorised", "e.g. manufacture, quality control, packaging"),
          ("Validity", "Must be current")],
         "Module1/1.2_Administrative_Information/1.2.9_Manufacturing_Authorization",
         "1.2.9_manufacturing_authorization.docx"),

        ("1.2.10", "Evidence of Trademark Registration",
         "Evidence of trademark registration for the brand name of the product "
         "in Nigeria (where a brand name is used).",
         [("Brand name", "Exact brand name to be registered"),
          ("Registration number", "Nigerian trademark registration number"),
          ("Class", "Trademark class (pharmaceutical products = Class 5)"),
          ("Registered proprietor", "Must match applicant name")],
         "Module1/1.2_Administrative_Information/1.2.10_Trademark",
         "1.2.10_trademark_registration.docx"),

        ("1.2.11", "Superintendent Pharmacist Annual Licence",
         "Current Annual Licence to Practice of the Superintendent Pharmacist "
         "responsible for the applicant's pharmaceutical operations.",
         [("Pharmacist name", "Full name of Superintendent Pharmacist"),
          ("PCN registration number", "Pharmacists Council of Nigeria number"),
          ("Year of licence", "Must be current year"),
          ("Premises", "Pharmaceutical premises covered")],
         "Module1/1.2_Administrative_Information/1.2.11_Superintendent_Pharmacist",
         "1.2.11_superintendent_pharmacist.docx"),

        ("1.2.12", "Certificate of Registration and Retention of Premises",
         "Current Certificate of Registration and Retention of the applicant's "
         "pharmaceutical premises issued by PCN.",
         [("Premises name", "Registered name of premises"),
          ("Premises address", "Full address"),
          ("PCN certificate number", "As on certificate"),
          ("Type of premises", "e.g. pharmaceutical wholesaler, distributor"),
          ("Validity", "Must be current")],
         "Module1/1.2_Administrative_Information/1.2.12_Premises_Certificate",
         "1.2.12_premises_certificate.docx"),

        ("1.2.13", "Evidence of Previous Market Authorization",
         "If applicable: copy of existing NAFDAC registration certificate "
         "for this product or a closely related product.",
         [("NAFDAC registration number", "If already registered"),
          ("Product name", "As previously registered"),
          ("Date of registration", "Original registration date"),
          ("Applicability", "State if not applicable")],
         "Module1/1.2_Administrative_Information/1.2.13_Previous_Market_Auth",
         "1.2.13_previous_market_authorization.docx"),

        ("1.2.14", "GMP Inspection Invitation Letter",
         "Letter from the applicant inviting NAFDAC to conduct a GMP "
         "inspection of the manufacturing site (required for new manufacturers).",
         [("Addressed to", "Director General, NAFDAC"),
          ("Site details", "Full address of manufacturing site"),
          ("Products to be inspected", "List of products manufactured at site"),
          ("Proposed dates", "Suggested inspection dates"),
          ("Contact person", "Name and contact details of site contact")],
         "Module1/1.2_Administrative_Information/1.2.14_GMP_Inspection_Invite",
         "1.2.14_gmp_inspection_invitation.docx"),

        ("1.2.15", "Certificate of Suitability (CEP/EDMF)",
         "Certificate of Suitability of the European Pharmacopoeia (CEP) "
         "or equivalent, where applicable for the drug substance.",
         [("CEP number", "EDQM certificate number"),
          ("Drug substance", "Name of API covered"),
          ("Manufacturer", "API manufacturer name and site"),
          ("Issue date", "Date of issuance"),
          ("Applicability", "State Not Applicable if CEP not used")],
         "Module1/1.2_Administrative_Information/1.2.15_CEP",
         "1.2.15_cep.docx"),

        ("1.2.16", "APIMF Letter of Access",
         "Letter of Access for Active Pharmaceutical Ingredient Master File (APIMF) "
         "authorising NAFDAC to review the restricted part of the APIMF, "
         "where applicable.",
         [("APIMF holder", "Name of APIMF holder"),
          ("Applicant", "Name of applicant granted access"),
          ("APIMF reference", "APIMF number or reference"),
          ("Applicability", "State Not Applicable if no APIMF used")],
         "Module1/1.2_Administrative_Information/1.2.16_APIMF_Access",
         "1.2.16_apimf_letter_of_access.docx"),

        ("1.2.17", "Biowaiver Request (BCS-based)",
         "Request for biowaiver based on Biopharmaceutics Classification System (BCS) "
         "in lieu of conducting an in vivo bioavailability/bioequivalence study.",
         [("BCS class", "Class I, II, III, or IV"),
          ("Solubility data", "Solubility at pH 1.2, 4.5, 6.8"),
          ("Permeability data", "Evidence of high permeability"),
          ("Dissolution data", "Rapid dissolution in all three pH media"),
          ("Applicability", "State Not Applicable if BE study conducted")],
         "Module1/1.2_Administrative_Information/1.2.17_Biowaiver_BCS",
         "1.2.17_biowaiver_bcs.docx"),

        ("1.2.18", "Biowaiver Request (Additional Strength)",
         "Request for biowaiver for additional strength(s) based on "
         "proportional similarity of formulation.",
         [("Reference strength", "Strength for which BE study was conducted"),
          ("Additional strength(s)", "Strength(s) for which biowaiver is requested"),
          ("Proportionality", "Evidence that formulations are proportionally similar"),
          ("Applicability", "State Not Applicable if not applicable")],
         "Module1/1.2_Administrative_Information/1.2.18_Biowaiver_Strength",
         "1.2.18_biowaiver_strength.docx"),
    ]

    for sec_id, title, guidance, fields, folder, filename in admin_docs:
        folder_path = root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        out_p = folder_path / filename
        ok = generate_placeholder(out_p, sec_id, title, config, guidance, fields)
        if ok:
            results["generated"] += 1
            results["files"].append(str(out_p))
        else:
            results["failed"] += 1

    return results


def generate_m1_labelling_placeholder(out_path: Path, config: Any) -> bool:
    """1.3.2 Labelling — Outer and Inner Labels."""
    return generate_placeholder(
        out_path, "1.3.2", "Labelling — Outer and Inner Labels", config,
        "Artwork and text for all labels (outer carton, primary label, foil/blister back). "
        "Must comply with NAFDAC labelling requirements and include all mandatory elements.",
        [("Outer carton", "Product name, strength, dosage form, quantity, batch no., expiry date, storage, manufacturer, NAFDAC no."),
         ("Primary label", "Same mandatory elements formatted for primary container"),
         ("Blister/foil text", "Product name, strength, batch no., expiry date, manufacturer"),
         ("NAFDAC registration number", "To be assigned upon approval — use PENDING"),
         ("Barcode", "GS1 barcode with GTIN"),
         ("Braille", "Include Braille of product name if required"),
         ("Languages", "English (mandatory) — additional languages as applicable")],
    )


def generate_m1_pil_placeholder(out_path: Path, config: Any) -> bool:
    """1.3.1 Product Information / Patient Information Leaflet (PIL)."""
    return generate_placeholder(
        out_path, "1.3.1", "Product Information Leaflet (PIL)", config,
        "Patient Information Leaflet (PIL) or Package Insert for "
        f"{config.full_product_name}. Must comply with NAFDAC labelling guidelines "
        "and include all mandatory sections in plain language accessible to patients.",
        [("Product name and strength", "Brand name (if any), INN, strength, dosage form"),
         ("Indications", "Approved therapeutic indications in patient-friendly language"),
         ("Dosage and administration", "Dosing instructions for each indication and patient group"),
         ("Contraindications", "Absolute contraindications with reasons"),
         ("Warnings and precautions", "Special warnings, precautions, drug interactions"),
         ("Side effects", "Common, uncommon, and rare adverse effects — by frequency"),
         ("Overdose", "Symptoms of overdose and management"),
         ("Storage", "Storage conditions as per approved labelling"),
         ("Manufacturer details", "Name and address of manufacturer and local distributor"),
         ("NAFDAC number", "To be inserted upon approval")],
    )


def generate_m1_specimen_label_placeholder(out_path: Path, config: Any) -> bool:
    """1.3.3 Mock-up / Specimen Labels."""
    return generate_placeholder(
        out_path, "1.3.3", "Mock-up / Specimen Labels", config,
        "Colour mock-up (artwork proofs) or black-and-white specimen copies of all "
        "proposed packaging components. Must reflect the final artwork to be used "
        "for the marketed product.",
        [("Outer carton artwork", "Final colour artwork for outer carton — all faces"),
         ("Primary label artwork", "Label artwork for bottle, sachet or tube"),
         ("Blister/foil artwork", "Artwork for blister face and aluminium foil back"),
         ("Package insert / PIL", "Folded package insert specimen"),
         ("Format", "PDF format preferred; clearly legible at 100% scale"),
         ("Version control", "Include version number and date on each artwork")],
    )


def generate_m1_bti_placeholder(out_path: Path, config: Any) -> bool:
    """1.4.1 Bioequivalence Trial Information (BTI)."""
    return generate_placeholder(
        out_path, "1.4.1", "Bioequivalence Trial Information (BTI)", config,
        "NAFDAC-specific regional document. The BTI form provides information about "
        "the bioequivalence (BE) study conducted for this generic product. "
        "Required for all oral solid dosage forms unless a biowaiver has been granted.",
        [("Reference product", "Name, strength, manufacturer of reference (innovator) product used in BE study"),
         ("Reference product source", "Country where reference product was sourced"),
         ("Study centre", "Name and country of BE study centre — must be NAFDAC-accredited or WHO-recognised"),
         ("Study design", "Crossover or parallel, number of subjects, fed/fasted"),
         ("PK parameters", "Cmax, AUC0-t, AUC0-inf for test and reference"),
         ("90% CI — Cmax", "90% confidence interval for Cmax ratio (acceptance: 80.00-125.00%)"),
         ("90% CI — AUC", "90% confidence interval for AUC ratio (acceptance: 80.00-125.00%)"),
         ("BE conclusion", "Whether bioequivalence was demonstrated"),
         ("Ethics approval", "Ethics committee approval reference"),
         ("Regulatory approval", "Approval from regulatory authority where study was conducted")],
    )


def generate_m1_qis_placeholder(out_path: Path, config: Any) -> bool:
    """1.4.2 Quality Information Summary (QIS)."""
    return generate_placeholder(
        out_path, "1.4.2", "Quality Information Summary (QIS)", config,
        "NAFDAC-specific regional summary of quality information. The QIS provides "
        "a concise overview of the key quality aspects of the product for NAFDAC reviewers.",
        [("Drug substance summary", "INN, source, pharmacopoeial compliance, specification"),
         ("Drug product summary", "Composition, manufacturing site, batch size"),
         ("Specifications summary", "Key specification tests and limits for DS and DP"),
         ("Stability summary", "Proposed shelf life and storage condition"),
         ("Container closure", "Primary packaging type and specification"),
         ("GMP status", "GMP certification status of manufacturing site"),
         ("BE status", "Bioequivalence status or biowaiver justification")],
    )


def generate_all_m1_placeholders(submission_root: str, config: Any) -> dict:
    """
    Generate ALL Module 1 placeholders:
    1.2 Administrative (18 docs) + 1.3 Product Information + 1.4 Regional.
    """
    root = Path(submission_root)
    results: dict = {"generated": 0, "failed": 0, "files": []}

    def _run(fn, *args):
        ok = fn(*args)
        if ok:
            results["generated"] += 1
            results["files"].append(str(args[0]))
        else:
            results["failed"] += 1

    # 1.2 Administrative — 18 documents
    admin_res = generate_all_admin_placeholders(submission_root, config)
    results["generated"] += admin_res["generated"]
    results["failed"]    += admin_res["failed"]
    results["files"]     += admin_res["files"]

    # 1.3 Product Information
    pi_folder = root / "Module1/1.3_Product_Information"
    pi_folder.mkdir(parents=True, exist_ok=True)
    _run(generate_m1_pil_placeholder,
         pi_folder / "1.3.1_patient_information_leaflet.docx", config)
    _run(generate_m1_labelling_placeholder,
         pi_folder / "1.3.2_labelling.docx", config)
    _run(generate_m1_specimen_label_placeholder,
         pi_folder / "1.3.3_specimen_labels.docx", config)

    # 1.4 Regional
    reg_folder = root / "Module1/1.4_Regional_Information"
    reg_folder.mkdir(parents=True, exist_ok=True)
    _run(generate_m1_bti_placeholder,
         reg_folder / "1.4.1_bioequivalence_trial_information.docx", config)
    _run(generate_m1_qis_placeholder,
         reg_folder / "1.4.2_quality_information_summary.docx", config)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — DRUG SUBSTANCE (S) SECTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m3_s1_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.1 Drug Substance — General Information."""
    drug    = _v(fields, "drug_name", config.drug_name)
    formula = _v(fields, "molecular_formula", "[INSERT MOLECULAR FORMULA]")
    mw      = _v(fields, "molecular_weight",  "[INSERT MW]")
    cas     = _v(fields, "cas_number",         "[INSERT CAS NUMBER]")
    return generate_placeholder(
        out_path, "3.2.S.1", f"Drug Substance — General Information ({drug})", config,
        f"General information on the drug substance {drug}. "
        "Per ICH Q6A, this section must include the nomenclature, structure, and "
        "general physicochemical properties of the drug substance.",
        [("INN / Approved name", f"International Non-proprietary Name: {drug}"),
         ("Chemical name (IUPAC)", "Full systematic IUPAC chemical name"),
         ("CAS number", f"CAS Registry Number: {cas}"),
         ("Molecular formula", f"Molecular formula: {formula}"),
         ("Molecular weight", f"Relative molecular mass: {mw}"),
         ("Structural formula", "Structural formula or graphic representation"),
         ("Pharmacopoeial compliance", "State compendium (BP/USP/EP/IP) and edition, or 'Non-pharmacopoeial'"),
         ("Physical description", "Appearance, colour, physical state at room temperature"),
         ("Solubility", "Solubility in water and common organic solvents at 25°C"),
         ("pKa", "Ionisation constant(s), if applicable"),
         ("Polymorphism", "Known polymorphic forms and which is used in the product")],
        extra_sections=[
            ("3.2.S.1.1 Nomenclature",
             "Provide: INN, chemical name (IUPAC), CAS number, company code (if any), and any other names used."),
            ("3.2.S.1.2 Structure",
             "Provide the structural formula, molecular formula, and relative molecular mass. "
             "For chiral compounds, identify the stereochemistry."),
            ("3.2.S.1.3 General Properties",
             "Provide physicochemical properties: appearance, solubility, melting point, "
             "pKa, optical rotation (if chiral), polymorphism, hygroscopicity."),
        ]
    )


def generate_m3_s2_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.2 Drug Substance — Manufacture."""
    drug = _v(fields, "drug_name", config.drug_name)
    return generate_placeholder(
        out_path, "3.2.S.2", f"Drug Substance — Manufacture ({drug})", config,
        "This section describes the manufacturing process for the drug substance. "
        "Per ICH Q11, it must include: manufacturer name and address, description of "
        "manufacturing process with process controls, control of materials (starting "
        "materials, reagents, solvents), control of critical steps and intermediates, "
        "process validation data, and manufacturing process development history.",
        [("3.2.S.2.1 Manufacturer", "Name, address and responsibility of each manufacturer including contractors and testing laboratories"),
         ("3.2.S.2.2 Manufacturing process", "Flow chart and detailed narrative of manufacturing process with in-process controls"),
         ("3.2.S.2.3 Control of materials", "Specifications for starting materials, reagents, solvents and auxiliary materials"),
         ("3.2.S.2.4 Critical steps", "Identification of critical steps and critical intermediates with acceptance criteria"),
         ("3.2.S.2.5 Process validation", "Process validation protocol and results for commercial scale batches"),
         ("3.2.S.2.6 Process development", "Summary of development history and changes made during development")],
        extra_sections=[
            ("3.2.S.2.1 Manufacturer",
             "Provide the name and address of all manufacturers involved in the manufacture and testing of the drug substance, including contract manufacturers and analytical laboratories."),
            ("3.2.S.2.2 Description of Manufacturing Process and Process Controls",
             "Provide a flow chart that includes all steps and in-process controls. Provide a narrative description referencing the flow chart."),
            ("3.2.S.2.3 Control of Materials",
             "List all materials used in the manufacturing process. Include specifications and the source of each material."),
            ("3.2.S.2.4 Control of Critical Steps and Intermediates",
             "Identify all critical process steps. For each critical step, provide acceptance criteria for in-process controls."),
            ("3.2.S.2.5 Process Validation and/or Evaluation",
             "Provide process validation protocol and results. For biotechnology products, include evaluation data."),
            ("3.2.S.2.6 Manufacturing Process Development",
             "Provide a summary of the development history of the manufacturing process."),
        ]
    )


def generate_m3_s3_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.3 Drug Substance — Characterisation."""
    drug    = _v(fields, "drug_name", config.drug_name)
    formula = _v(fields, "molecular_formula", "[FORMULA]")
    return generate_placeholder(
        out_path, "3.2.S.3", f"Drug Substance — Characterisation ({drug})", config,
        "This section provides evidence of the elucidation of the structure and other "
        "characteristics of the drug substance. Per ICH Q6A, it must include: "
        "structure elucidation (spectroscopic data — IR, NMR, MS, UV), "
        "stereochemistry, physicochemical properties, and characterisation of impurities.",
        [("3.2.S.3.1 Structure elucidation", f"IR, 1H-NMR, 13C-NMR, MS spectra with interpretation. Molecular formula: {formula}"),
         ("3.2.S.3.1 Stereochemistry", "Absolute configuration or racemate status"),
         ("3.2.S.3.1 Polymorphism", "Characterisation of polymorphic forms and their relevance"),
         ("3.2.S.3.2 Impurities", "List of potential and actual impurities with chemical names, structures and sources"),
         ("3.2.S.3.2 Degradation products", "Known degradation products from stress testing"),
         ("3.2.S.3.2 Elemental impurities", "Per ICH Q3D — risk assessment or data")],
        extra_sections=[
            ("3.2.S.3.1 Elucidation of Structure and Other Characteristics",
             "Provide spectral data (IR, NMR, MS) with interpretation confirming the proposed structure. Include data for the reference standard."),
            ("3.2.S.3.2 Impurities",
             "Provide a table of all known impurities including synthesis-related impurities and potential degradation products. Reference BP/USP limits where applicable."),
        ]
    )


def generate_m3_s4_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.4 Drug Substance — Control of Drug Substance."""
    drug        = _v(fields, "drug_name", config.drug_name)
    pharmacopeia = _v(fields, "pharmacopeia", "BP / USP")
    return generate_placeholder(
        out_path, "3.2.S.4", f"Drug Substance — Control of Drug Substance ({drug})", config,
        f"This section covers the specification, analytical procedures, validation, "
        f"and batch analysis for the drug substance {drug}. "
        f"Per ICH Q6A and the {pharmacopeia}, the specification must include tests for "
        "identity, assay, purity, related substances, residual solvents (ICH Q3C), "
        "elemental impurities (ICH Q3D), and any other critical quality attributes.",
        [("3.2.S.4.1 Specification", f"Full specification table: test, method reference, acceptance criteria — must align with {pharmacopeia} monograph or exceed it"),
         ("3.2.S.4.2 Analytical procedures", f"Reference to {pharmacopeia} methods or full in-house method descriptions"),
         ("3.2.S.4.3 Validation of analytical procedures", "Analytical method validation reports per ICH Q2(R1) for all non-pharmacopoeial methods"),
         ("3.2.S.4.4 Batch analyses", "CoA and batch analysis data for minimum 3 batches (pilot or production scale)"),
         ("3.2.S.4.5 Justification of specification", "Justification for each acceptance criterion, especially limits not in the pharmacopoeia")],
        extra_sections=[
            ("3.2.S.4.1 Specification",
             "Provide a table listing all tests, the analytical procedure reference (e.g. BP 2024, method X), and the acceptance criterion. "
             "Minimum required tests: Description, Identification (2 independent methods), Assay, Related substances, Residual solvents, Water content, Heavy metals/Elemental impurities, Microbial limits (if applicable)."),
            ("3.2.S.4.2 Analytical Procedures",
             "For pharmacopoeial methods: state the compendium and edition. "
             "For in-house methods: provide the full validated method including principle, equipment, reagents, system suitability, procedure, and calculations."),
            ("3.2.S.4.3 Validation of Analytical Procedures",
             "Provide validation data per ICH Q2(R1) for all non-compendial methods. Include: specificity, linearity, range, accuracy, precision (repeatability and intermediate precision), LOD, LOQ, robustness."),
            ("3.2.S.4.4 Batch Analyses",
             "Provide Certificates of Analysis for a minimum of 3 representative batches. Present results in tabular form. Confirm all results comply with specification."),
            ("3.2.S.4.5 Justification of Specification",
             "Justify acceptance criteria that differ from the pharmacopoeial monograph. Provide statistical analysis of batch data to support proposed limits."),
        ]
    )


def generate_m3_s5_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.5 Drug Substance — Reference Standards."""
    drug = _v(fields, "drug_name", config.drug_name)
    return generate_placeholder(
        out_path, "3.2.S.5", f"Drug Substance — Reference Standards ({drug})", config,
        "Information on the reference standards or reference materials used for testing "
        "the drug substance. Primary and secondary (working) standards must be described. "
        "Characterisation data for non-pharmacopoeial standards must be provided.",
        [("Primary standard", "Source (BP/USP/EP/in-house), lot number, characterisation data"),
         ("Secondary/working standard", "Preparation method, characterisation against primary"),
         ("Storage conditions", "Temperature, humidity, container"),
         ("Expiry/re-qualification", "Validity period and re-qualification protocol"),
         ("CoA", "Certificate of Analysis for each lot used")],
    )


def generate_m3_s6_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.6 Drug Substance — Container Closure System."""
    drug    = _v(fields, "drug_name", config.drug_name)
    storage = _v(fields, "storage", "Store below 25°C in a dry place")
    return generate_placeholder(
        out_path, "3.2.S.6", f"Drug Substance — Container Closure System ({drug})", config,
        f"Description of the container closure system used for storage and shipment of "
        f"the drug substance. Storage condition: {storage}. "
        "Per ICH Q1A, suitability of the container closure must be demonstrated.",
        [("Container type", "e.g. HDPE drum, double polyethylene bags"),
         ("Material of construction", "Grade and specification of container and closure"),
         ("Supplier", "Name and address of supplier"),
         ("Specification", "Reference to material specification"),
         ("Quantity", "Fill quantity per container"),
         ("Suitability data", "Data demonstrating suitability — extractables/leachables if applicable")],
    )


def generate_m3_s7_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.S.7 Drug Substance — Stability."""
    drug    = _v(fields, "drug_name", config.drug_name)
    storage = _v(fields, "storage", "Store below 25°C")
    return generate_placeholder(
        out_path, "3.2.S.7", f"Drug Substance — Stability ({drug})", config,
        f"Stability data for the drug substance per ICH Q1A(R2). "
        f"Proposed storage condition: {storage}. "
        "Long-term and accelerated stability studies must be conducted in the proposed container closure system.",
        [("3.2.S.7.1 Stability summary", "Summary of stability conclusions and proposed retest period/shelf life"),
         ("3.2.S.7.1 Stability protocol", "ICH Q1A-compliant protocol: conditions, time points, tests"),
         ("3.2.S.7.2 Post-approval protocol", "Post-approval stability commitment and protocol"),
         ("3.2.S.7.3 Long-term data", "Stability data at 25°C/60%RH (Zone IVb: 30°C/65%RH or 30°C/75%RH)"),
         ("3.2.S.7.3 Accelerated data", "Stability data at 40°C/75%RH — minimum 6 months"),
         ("3.2.S.7.3 Stress testing", "Photolysis, hydrolysis, oxidation, thermal degradation data"),
         ("Retest period", "Proposed retest period with justification")],
        extra_sections=[
            ("3.2.S.7.1 Stability Summary and Conclusion",
             "Provide a tabular summary of all stability studies conducted. State the proposed retest period and storage conditions."),
            ("3.2.S.7.2 Post-Approval Stability Protocol and Commitment",
             "Describe the commitment to place the first three production batches on long-term stability and annually thereafter."),
            ("3.2.S.7.3 Stability Data",
             "Provide tabulated stability data for all studies. Include assay, related substances, appearance, and other relevant parameters at each time point."),
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — DRUG PRODUCT (P) SECTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m3_p1_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.1 Drug Product — Description and Composition."""
    drug    = _v(fields, "drug_name", config.drug_name)
    strength = _v(fields, "strength", "[INSERT STRENGTH]")
    form    = config.dosage_form
    return generate_placeholder(
        out_path, "3.2.P.1", f"Drug Product — Description and Composition ({config.full_product_name})", config,
        f"This section provides the description and full qualitative and quantitative "
        f"composition of {config.full_product_name} ({form}). "
        "Per ICH Q6A, this must include all components of the drug product: active "
        "substance(s), excipients, and packaging components relevant to the formulation.",
        [("Product description", f"Physical description: shape, colour, dimensions (e.g. white, round, biconvex tablet, diameter X mm)"),
         ("Strength", f"Amount of active per dosage unit: {strength}"),
         ("Quantitative composition", "Complete table of ALL ingredients per dosage unit and per batch — include function of each excipient"),
         ("Active substance(s)", f"INN, amount per unit, grade/specification reference, supplier"),
         ("Excipients", "Each excipient: name, amount per unit, function, grade, compendial status"),
         ("Coating (if applicable)", "Coating composition with quantities"),
         ("Overages", "Declare any overages with justification"),
         ("Reference to pharmacopoeia", "State the pharmacopoeia and edition for each compendial ingredient")],
        extra_sections=[
            ("3.2.P.1 Description",
             "Describe the appearance of the product as it will be presented to the patient. "
             "Include: colour, shape, surface markings (for tablets), dimensions, and any film coating."),
            ("3.2.P.1 Composition",
             "Provide a complete composition table. For each ingredient state: name (INN for API), "
             "reference standard/grade, quantity per unit dose, quantity per batch, and function. "
             "The sum of all ingredients must equal 100% or the total batch weight."),
        ]
    )


def generate_m3_p2_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.2 Drug Product — Pharmaceutical Development."""
    return generate_placeholder(
        out_path, "3.2.P.2", f"Drug Product — Pharmaceutical Development ({config.full_product_name})", config,
        f"This section describes the pharmaceutical development of {config.full_product_name}. "
        "Per ICH Q8(R2), it must explain the choice of formulation components and process, "
        "and demonstrate understanding of how formulation and process variables affect product quality.",
        [("3.2.P.2.1.1 Drug Substance compatibility", "Compatibility of drug substance with excipients — stress testing data"),
         ("3.2.P.2.1.2 Excipient selection", "Rationale for choice and level of each excipient"),
         ("3.2.P.2.2.1 Formulation development", "Evolution of formulation from early development to final formula"),
         ("3.2.P.2.2.2 Overages", "Justification for any overages (normally not permitted without justification)"),
         ("3.2.P.2.2.3 Physicochemical properties", "Relevant physicochemical properties of the drug substance and their impact on formulation"),
         ("3.2.P.2.3 Manufacturing process development", "Development history of manufacturing process, including scale-up"),
         ("3.2.P.2.4 Container closure system", "Development rationale for choice of container closure"),
         ("3.2.P.2.5 Microbiological attributes", "Justification of microbiological specifications for non-sterile product")],
    )


def generate_m3_p3_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.3 Drug Product — Manufacture."""
    return generate_placeholder(
        out_path, "3.2.P.3", f"Drug Product — Manufacture ({config.full_product_name})", config,
        "This section describes the manufacture of the finished drug product. "
        "Per ICH CTD M4Q, it must include: manufacturer details, batch formula, "
        "manufacturing process description with flow chart, critical steps with controls, "
        "and process validation data.",
        [("3.2.P.3.1 Manufacturer", "Name, address and GMP authorisation of drug product manufacturer"),
         ("3.2.P.3.2 Batch formula", "Quantitative composition per batch — complete batch formula with batch size"),
         ("3.2.P.3.3 Manufacturing process", "Flow chart and step-by-step manufacturing process narrative"),
         ("3.2.P.3.3 In-process controls", "In-process tests and acceptance criteria for each critical step"),
         ("3.2.P.3.4 Critical steps", "Identification of critical process steps with justification"),
         ("3.2.P.3.5 Process validation", "Process validation protocol and results for commercial-scale batches")],
    )


def generate_m3_p4_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.4 Drug Product — Control of Excipients."""
    return generate_placeholder(
        out_path, "3.2.P.4", f"Drug Product — Control of Excipients ({config.full_product_name})", config,
        "Specifications and analytical procedures for all excipients in the formulation. "
        "Pharmacopoeial excipients: reference to monograph suffices. "
        "Non-pharmacopoeial excipients: full specifications required per ICH Q6A.",
        [("3.2.P.4.1 Specifications", "List all excipients with their specifications (Ph.Eur./BP/NF or in-house)"),
         ("3.2.P.4.2 Analytical procedures", "Reference to pharmacopoeial methods or in-house methods"),
         ("3.2.P.4.3 Validation", "Validation data for non-pharmacopoeial analytical methods"),
         ("3.2.P.4.4 Justification", "Justification for any non-pharmacopoeial specifications"),
         ("3.2.P.4.5 Human/animal origin", "Confirmation of BSE/TSE compliance for excipients of animal origin"),
         ("3.2.P.4.6 Novel excipients", "Full characterisation package for any novel excipients (not required if all excipients are compendial)")],
    )


def generate_m3_p5_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.5 Drug Product — Control of Drug Product."""
    pharmacopeia = _v(fields, "pharmacopeia", "BP / USP")
    return generate_placeholder(
        out_path, "3.2.P.5", f"Drug Product — Control of Drug Product ({config.full_product_name})", config,
        f"This section covers the specification, analytical procedures, validation, "
        f"and batch analysis for the finished drug product {config.full_product_name}. "
        f"Per ICH Q6A and {pharmacopeia}, the specification must cover all critical "
        "quality attributes of the finished dosage form.",
        [("3.2.P.5.1 Specification", "Full specification table: test, method reference, acceptance criteria"),
         ("3.2.P.5.2 Analytical procedures", f"Reference to {pharmacopeia} or full description of in-house methods"),
         ("3.2.P.5.3 Validation", "Method validation data per ICH Q2(R1) for all non-pharmacopoeial methods"),
         ("3.2.P.5.4 Batch analyses", "CoA and batch analysis results for minimum 3 batches (pilot or commercial)"),
         ("3.2.P.5.5 Characterisation of impurities", "Identification and qualification of degradation products"),
         ("3.2.P.5.6 Justification of specification", "Justification for proposed acceptance criteria")],
        extra_sections=[
            ("3.2.P.5.1 Specification",
             "Provide a complete specification table. "
             "Mandatory tests for oral solid dosage forms include: Description, Identification, Assay, "
             "Dissolution, Disintegration (if applicable), Uniformity of dosage units (mass or content), "
             "Related substances/Degradation products, Water content, Microbial limits."),
            ("3.2.P.5.2 Analytical Procedures",
             "For pharmacopoeial tests: cite the compendium, edition, and monograph. "
             "For in-house procedures: provide the complete validated method document."),
            ("3.2.P.5.3 Validation of Analytical Procedures",
             "For all non-compendial methods, provide ICH Q2(R1) validation data: "
             "specificity, linearity, range, accuracy, precision, LOD/LOQ, robustness."),
            ("3.2.P.5.4 Batch Analyses",
             "Tabulate CoA results for at least 3 representative batches. "
             "All results must be within the proposed specification limits."),
            ("3.2.P.5.5 Characterisation of Impurities",
             "List all known degradation products. Provide identification and qualification thresholds per ICH Q3B(R2)."),
            ("3.2.P.5.6 Justification of Specification",
             "Provide scientific justification for each acceptance criterion. "
             "Justify any deviation from pharmacopoeial limits. Provide statistical analysis of batch data."),
        ]
    )


def generate_m3_p6_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.6 Drug Product — Reference Standards."""
    return generate_placeholder(
        out_path, "3.2.P.6", f"Drug Product — Reference Standards ({config.full_product_name})", config,
        "Reference standards or reference materials used for testing the drug product. "
        "Same reference standards used for drug substance testing may be referenced here.",
        [("Primary standard", "Source and characterisation — may reference 3.2.S.5"),
         ("Impurity standards", "Reference standards for specified impurities/degradation products"),
         ("Working standards", "Preparation and qualification of working standards")],
    )


def generate_m3_p7_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.7 Drug Product — Container Closure System."""
    return generate_placeholder(
        out_path, "3.2.P.7", f"Drug Product — Container Closure System ({config.full_product_name})", config,
        "Description and specification of the container closure system for the drug product. "
        "Must demonstrate suitability: protection, compatibility, safety, and performance.",
        [("Primary packaging", "Type, material specification, supplier — e.g. HDPE bottle, PVC/aluminium blister"),
         ("Secondary packaging", "Outer carton, leaflet, shipper specifications"),
         ("Material specification", "Grade: food grade/pharmaceutical grade, compendial compliance"),
         ("Suitability data", "Compatibility study data — extractables/leachables if applicable"),
         ("Pack sizes", "All pack configurations to be marketed"),
         ("Labelling", "Reference to 1.3.2 Labelling section")],
    )


def generate_m3_p8_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """3.2.P.8 Drug Product — Stability."""
    storage = _v(fields, "storage", "Store below 25°C, protect from moisture")
    return generate_placeholder(
        out_path, "3.2.P.8", f"Drug Product — Stability ({config.full_product_name})", config,
        f"Stability data for {config.full_product_name} per ICH Q1A(R2). "
        f"Proposed storage: {storage}. "
        "Stability studies must be conducted in the proposed marketed container closure system.",
        [("3.2.P.8.1 Stability summary", "Summary of all stability studies with conclusions and proposed shelf life"),
         ("3.2.P.8.1 Storage condition", f"Proposed storage condition: {storage}"),
         ("3.2.P.8.2 Post-approval commitment", "Commitment to continue long-term studies after approval"),
         ("3.2.P.8.3 Long-term data", "Stability data at 30°C/75%RH (Nigeria: Zone IVb) — minimum 12 months"),
         ("3.2.P.8.3 Accelerated data", "Stability data at 40°C/75%RH — minimum 6 months"),
         ("3.2.P.8.3 Tests performed", "Appearance, assay, dissolution, degradation products, water content at each time point"),
         ("Shelf life", "Proposed shelf life in months with justification")],
        extra_sections=[
            ("3.2.P.8.1 Stability Summary and Conclusions",
             "Provide a brief summary of all stability studies. State the proposed shelf life and storage conditions. Confirm that the product is stable for the proposed shelf life."),
            ("3.2.P.8.2 Post-Approval Stability Protocol and Commitment",
             "State the commitment to place the first three production batches on long-term stability and to continue testing annually."),
            ("3.2.P.8.3 Stability Data",
             "Provide all stability data in tabular form. Each table should include: batch number, batch size, manufacturing date, container/closure, storage condition, time points tested, and results."),
        ]
    )


def generate_all_m3_placeholders(submission_root: str, fields: dict, config: Any) -> dict:
    """
    Generate ALL Module 3 placeholder documents:
    3.2.S.1–S.7 (Drug Substance) and 3.2.P.1–P.8 (Drug Product).
    """
    root = Path(submission_root)
    results: dict = {"generated": 0, "failed": 0, "files": []}

    def _run(fn, path, *args):
        path.parent.mkdir(parents=True, exist_ok=True)
        ok = fn(path, *args)
        if ok:
            results["generated"] += 1
            results["files"].append(str(path))
        else:
            results["failed"] += 1

    s_root = root / "Module3/3.2_Body_of_Data/3.2.S_Drug_Substance"
    p_root = root / "Module3/3.2_Body_of_Data/3.2.P_Drug_Product"

    # ── Drug Substance ───────────────────────────────────────────────────────
    _run(generate_m3_s1_placeholder, s_root / "3.2.S.1_General_Information/3.2.S.1_general_information.docx",       fields, config)
    _run(generate_m3_s2_placeholder, s_root / "3.2.S.2_Manufacture/3.2.S.2_manufacture.docx",                       fields, config)
    _run(generate_m3_s3_placeholder, s_root / "3.2.S.3_Characterisation/3.2.S.3_characterisation.docx",             fields, config)
    _run(generate_m3_s4_placeholder, s_root / "3.2.S.4_Control_of_DS/3.2.S.4_control_of_drug_substance.docx",       fields, config)
    _run(generate_m3_s5_placeholder, s_root / "3.2.S.5_Reference_Standards/3.2.S.5_reference_standards.docx",       fields, config)
    _run(generate_m3_s6_placeholder, s_root / "3.2.S.6_Container_Closure/3.2.S.6_container_closure_system.docx",    fields, config)
    _run(generate_m3_s7_placeholder, s_root / "3.2.S.7_Stability/3.2.S.7_stability.docx",                           fields, config)

    # ── Drug Product ──────────────────────────────────────────────────────────
    _run(generate_m3_p1_placeholder, p_root / "3.2.P.1_Description_Composition/3.2.P.1_description_composition.docx",   fields, config)
    _run(generate_m3_p2_placeholder, p_root / "3.2.P.2_Pharmaceutical_Development/3.2.P.2_pharmaceutical_development.docx", fields, config)
    _run(generate_m3_p3_placeholder, p_root / "3.2.P.3_Manufacture/3.2.P.3_manufacture.docx",                            fields, config)
    _run(generate_m3_p4_placeholder, p_root / "3.2.P.4_Control_Excipients/3.2.P.4_control_of_excipients.docx",           fields, config)
    _run(generate_m3_p5_placeholder, p_root / "3.2.P.5_Control_of_DP/3.2.P.5_control_of_drug_product.docx",              fields, config)
    _run(generate_m3_p6_placeholder, p_root / "3.2.P.6_Reference_Standards/3.2.P.6_reference_standards.docx",            fields, config)
    _run(generate_m3_p7_placeholder, p_root / "3.2.P.7_Container_Closure/3.2.P.7_container_closure_system.docx",         fields, config)
    _run(generate_m3_p8_placeholder, p_root / "3.2.P.8_Stability/3.2.P.8_stability.docx",                                fields, config)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — N/A FOR GENERICS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_not_applicable_declaration(
    out_path: Path,
    module_num: str,
    config: Any,
    reason: str,
) -> bool:
    """Generate a Not Applicable declaration for modules N/A for generics."""
    return generate_placeholder(
        out_path,
        f"Module {module_num}",
        f"Module {module_num} — Not Applicable Declaration",
        config,
        reason,
        [],
        is_not_applicable=True,
        na_reason=reason,
    )


def generate_module4_na(submission_root: str, config: Any) -> dict:
    """
    Generate Module 4 Not Applicable declaration.
    Module 4 (Non-clinical Study Reports) is not required for generic products.
    """
    root = Path(submission_root)
    results: dict = {"generated": 0, "failed": 0, "files": []}
    out_p = root / "Module4/Module4_Not_Applicable.docx"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    ok = generate_not_applicable_declaration(
        out_p, "4",
        config,
        "Module 4 (Non-clinical Study Reports) is NOT APPLICABLE for multisource "
        "(generic) pharmaceutical products registered under NAFDAC Guidelines for "
        "Registration of Generic Medicines. Non-clinical studies are not required "
        "when the product is bioequivalent to a reference listed drug and the "
        "drug substance safety profile is established through the innovator's dossier "
        "and scientific literature. Refer to Section 5.3 (Module 5) for biopharmaceutic studies.",
    )
    if ok:
        results["generated"] += 1
        results["files"].append(str(out_p))
    else:
        results["failed"] += 1
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 5 — CLINICAL / BIOPHARMACEUTIC STUDIES
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m5_be_placeholder(out_path: Path, fields: dict, config: Any) -> bool:
    """5.3.1 Bioequivalence Study Reports."""
    return generate_placeholder(
        out_path, "5.3.1", f"Reports of Biopharmaceutic Studies — {config.full_product_name}", config,
        "Full bioequivalence (BE) or bioavailability (BA) study reports. "
        "Per NAFDAC Guidelines for Multisource Generic Products, only section 5.3.1 "
        "is applicable. The complete BE study report must be provided.",
        [("5.3.1.1 BA study report", "Full study report for any absolute BA studies"),
         ("5.3.1.2 BE study report", "Full comparative BA/BE study report — must follow ICH E3 format"),
         ("5.3.1.2 Study protocol", "Approved study protocol with all amendments"),
         ("5.3.1.2 Ethics approval", "Ethics committee approval and informed consent forms"),
         ("5.3.1.2 Analytical method", "Validated bioanalytical method for drug plasma concentration measurement"),
         ("5.3.1.2 Statistical analysis", "Complete statistical analysis report with PK parameters"),
         ("5.3.1.2 Individual data", "Individual subject PK data and concentration-time profiles"),
         ("5.3.1.4 Bioanalytical report", "Full bioanalytical method validation report (ICH M10)")],
    )


def generate_m5_lit_refs_placeholder(out_path: Path, config: Any) -> bool:
    """5.4 Literature References."""
    return generate_placeholder(
        out_path, "5.4", f"Literature References — {config.full_product_name}", config,
        "Copies of key literature references cited in the Module 5 clinical overview "
        "and summaries. For generic products, literature supporting the safety and "
        "efficacy of the reference listed drug may be cited in lieu of original studies.",
        [("Published BE studies", "Any published bioequivalence studies for this drug substance/formulation"),
         ("Pharmacokinetic literature", "Key published PK studies for the active substance"),
         ("Safety literature", "Published safety data supporting the established safety profile"),
         ("Citation format", "Vancouver format; provide copies of papers cited")],
    )


def generate_all_m5_placeholders(submission_root: str, fields: dict, config: Any) -> dict:
    """
    Generate all Module 5 placeholder documents applicable to generic products.
    For generics: only 5.3.1 (BE studies) and 5.4 (literature references) apply.
    """
    root = Path(submission_root)
    results: dict = {"generated": 0, "failed": 0, "files": []}

    def _run(fn, path, *args):
        path.parent.mkdir(parents=True, exist_ok=True)
        ok = fn(path, *args)
        if ok:
            results["generated"] += 1
            results["files"].append(str(path))
        else:
            results["failed"] += 1

    m5_root = root / "Module5/5.3_Reports_of_Studies"

    _run(generate_m5_be_placeholder,
         m5_root / "5.3.1_Biopharmaceutic_Studies/5.3.1_bioequivalence_study_report.docx",
         fields, config)
    _run(generate_m5_lit_refs_placeholder,
         root / "Module5/5.4_Literature_References/5.4_literature_references.docx",
         config)

    # N/A declarations for sections 5.3.2–5.3.7 (not required for generics)
    na_sections = [
        ("5.3.2", "Bioavailability Studies — Not Applicable for generic products where full BE study is provided."),
        ("5.3.3", "PK Studies — Not Applicable. No additional PK studies are required for generic products."),
        ("5.3.4", "PK/PD Studies — Not Applicable for generic products."),
        ("5.3.5", "Clinical Study Reports — Not Applicable. Generic products do not require new clinical efficacy studies."),
        ("5.3.6", "Post-marketing Study Reports — Not Applicable at time of initial registration."),
        ("5.3.7", "Case Reports and Individual Patient Listings — Not Applicable for generic products."),
    ]
    for sec_id, reason in na_sections:
        out_p = m5_root / f"{sec_id}_Not_Applicable/{sec_id.replace('.', '_')}_not_applicable.docx"
        out_p.parent.mkdir(parents=True, exist_ok=True)
        ok = generate_not_applicable_declaration(out_p, sec_id, config, reason)
        if ok:
            results["generated"] += 1
            results["files"].append(str(out_p))
        else:
            results["failed"] += 1

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED / UTILITY GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_literature_references_placeholder(
    out_path: Path,
    section_id: str,
    config: Any,
) -> bool:
    """Generic literature references placeholder for any module."""
    return generate_placeholder(
        out_path, section_id, "Literature References", config,
        "List all literature references cited in this module. "
        "Use Vancouver citation format. Include only peer-reviewed publications, "
        "regulatory guidelines, and pharmacopoeial references.",
        [("References", "Numbered list of all citations in Vancouver format"),
         ("Access", "Confirm that copies of key references are available for inspection")],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_all_placeholders(
    submission_root: str,
    config: Any,
    fields: dict | None = None,
    modules: list[str] | None = None,
) -> dict:
    """
    Generate ALL placeholder documents for a complete NAFDAC CTD submission.

    Args:
        submission_root:  Root directory of the submission folder structure.
        config:           SubmissionConfig instance.
        fields:           Optional dict of product-specific fields (drug_name,
                          molecular_formula, molecular_weight, cas_number,
                          strength, storage, pharmacopeia, etc.).
        modules:          Optional list to limit generation, e.g. ['M1', 'M3'].
                          Defaults to all modules.

    Returns:
        Aggregated results dict with keys: generated, failed, files, by_module.
    """
    fields = fields or {}
    run_all = not modules
    run = lambda m: run_all or m in (modules or [])

    total: dict = {"generated": 0, "failed": 0, "files": [], "by_module": {}}

    def _merge(label: str, res: dict) -> None:
        total["generated"]        += res.get("generated", 0)
        total["failed"]           += res.get("failed",    0)
        total["files"]            += res.get("files",     [])
        total["by_module"][label]  = res
        _print_summary(label, res)

    def _print_summary(label: str, res: dict) -> None:
        g, f = res.get("generated", 0), res.get("failed", 0)
        status = "✓" if f == 0 else "⚠"
        print(f"  {status}  {label}: {g} generated, {f} failed")

    print(f"\n{'='*60}")
    print(f"  NAFDAC CTD Placeholder Generator")
    print(f"  Product : {config.full_product_name}")
    print(f"  Applicant: {config.applicant}")
    print(f"{'='*60}\n")

    if run("M1"):
        print("► Module 1 — Administrative / Regional")
        _merge("Module 1", generate_all_m1_placeholders(submission_root, config))

    if run("M3"):
        print("► Module 3 — Quality (Drug Substance + Drug Product)")
        _merge("Module 3", generate_all_m3_placeholders(submission_root, fields, config))

    if run("M4"):
        print("► Module 4 — Non-clinical (N/A for generics)")
        _merge("Module 4", generate_module4_na(submission_root, config))

    if run("M5"):
        print("► Module 5 — Clinical / Biopharmaceutic")
        _merge("Module 5", generate_all_m5_placeholders(submission_root, fields, config))

    print(f"\n{'='*60}")
    print(f"  TOTAL GENERATED : {total['generated']}")
    print(f"  TOTAL FAILED    : {total['failed']}")
    print(f"{'='*60}\n")

    return total