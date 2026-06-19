"""
module_generators.py
=====================
Generates Module 1-3 DOCX documents for a NAFDAC CTD submission.
Uses the resolved spec (from spec_resolver.py) and submission config
(from nafdac_structure.py) to populate all sections.

Modules generated
-----------------
  Module 1:
    1.1  Cover Letter
    1.2  Application Form
    1.3.1 SmPC  (see smpc_pil_generator.py — step 4.3)
    1.3.2 PIL   (see smpc_pil_generator.py — step 4.3)

  Module 2:
    2.1  CTD Table of Contents
    2.2  Introduction
    2.3  Quality Overall Summary (QOS)

  Module 3:
    3.1  Table of Contents
    3.2.S.1  Drug Substance — General Information
    3.2.S.3  Characterisation
    3.2.S.4  Control of Drug Substance
    3.2.P.1  Drug Product — Description and Composition
    3.2.P.5  Control of Drug Product

Usage
-----
  from module_generators import generate_all_modules

  generate_all_modules(
      submission_root = "submissions/Amlodipine_Besylate_10mg_Tablets",
      resolved_spec   = spec,   # from spec_resolver.resolve_spec()
  )

CLI (via cli.py)
----------------
  python cli.py generate-modules --submission submissions/Amlodipine_Besylate_10mg_Tablets
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _v(resolved_fields: dict, field: str, default: str = "[NOT AVAILABLE]") -> str:
    """Get a field value from resolved spec, returning default if empty."""
    entry = resolved_fields.get(field, {})
    val   = entry.get("value") if isinstance(entry, dict) else entry
    if val is None:
        return default
    if isinstance(val, dict):
        return json.dumps(val, indent=2)
    if isinstance(val, list):
        if not val:
            return default
        # Format list of identification tests or related substances
        parts = []
        for item in val:
            if isinstance(item, dict):
                parts.append(item.get("criterion") or item.get("name") or str(item))
            else:
                parts.append(str(item))
        return "; ".join(parts[:3])
    return str(val).strip()


def _assay_str(resolved_fields: dict) -> str:
    """Format assay dict as a readable string."""
    entry = resolved_fields.get("assay", {})
    val   = entry.get("value") if isinstance(entry, dict) else entry
    if not val or not isinstance(val, dict):
        return "[NOT AVAILABLE]"
    limits = val.get("limits", {})
    method = val.get("method", "")
    if limits and limits.get("min") and limits.get("max"):
        return f"{limits['min']}% to {limits['max']}% ({method})"
    return method or "[NOT AVAILABLE]"


def _lod_str(resolved_fields: dict) -> str:
    """Format loss on drying dict."""
    entry = resolved_fields.get("loss_on_drying", {})
    val   = entry.get("value") if isinstance(entry, dict) else entry
    if not val or not isinstance(val, dict):
        return "[NOT AVAILABLE]"
    pct  = val.get("limit_pct")
    temp = val.get("temperature_c")
    meth = val.get("method", "")
    parts = []
    if pct:
        parts.append(f"NMT {pct}%")
    if temp:
        parts.append(f"dried at {temp}°C")
    if meth:
        parts.append(f"({meth})")
    return " ".join(parts) or "[NOT AVAILABLE]"


# Project root = directory containing module_generators.py
_PROJECT_ROOT = Path(__file__).parent.resolve()


def _generate_docx_from_js(js_code: str, out_path: Path) -> bool:
    """
    Write JS to a temp file IN THE PROJECT ROOT and run with Node.js.
    Writing to the project root ensures Node resolves node_modules correctly.
    Returns True on success.
    """
    # Write temp JS file into project root (not system temp) so node_modules resolves
    tmp_js = _PROJECT_ROOT / f"_tmp_docgen_{out_path.stem}.js"
    tmp_js.write_text(js_code, encoding="utf-8")

    try:
        result = subprocess.run(
            ["node", str(tmp_js)],
            capture_output=True, text=True, timeout=60,
            cwd=str(_PROJECT_ROOT),   # run from project root
        )
        if result.returncode != 0:
            log.error("Node.js error for %s:\n%s", out_path.name, result.stderr[:500])
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        log.info("Generated: %s", out_path)
        return True
    except subprocess.TimeoutExpired:
        log.error("Node.js timeout for %s", out_path.name)
        return False
    except FileNotFoundError:
        log.error("Node.js not found. Install from https://nodejs.org/")
        return False
    finally:
        tmp_js.unlink(missing_ok=True)


def _js_escape(text: str) -> str:
    """Escape a string for safe embedding in a JS template literal."""
    return (text
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
            .replace("\n", " ")
            .replace("\r", ""))


def _docx_header_footer_js(full_product_name: str, section_title: str) -> str:
    """Return JS snippet for header/footer."""
    prod = _js_escape(full_product_name)
    sect = _js_escape(section_title)
    return f"""
    headers: {{
      default: new Header({{
        children: [new Paragraph({{
          border: {{ bottom: {{ style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 }} }},
          children: [
            new TextRun({{ text: "{prod}", bold: true, size: 18, font: "Arial" }}),
            new TextRun({{ text: "  |  {sect}", size: 18, font: "Arial", color: "595959" }}),
          ]
        }})]
      }})
    }},
    footers: {{
      default: new Footer({{
        children: [new Paragraph({{
          border: {{ top: {{ style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 }} }},
          children: [
            new TextRun({{ text: "CONFIDENTIAL — For NAFDAC Submission Only    Page ", size: 16, font: "Arial", color: "808080" }}),
            new TextRun({{ children: [PageNumber.CURRENT], size: 16, font: "Arial", color: "808080" }}),
          ]
        }})]
      }})
    }},"""


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT STYLES (shared across all modules)
# ═══════════════════════════════════════════════════════════════════════════════

_DOCX_STYLES_JS = """
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "1F3864" },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 220, after: 110 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "404040" },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ]
  },"""

_A4_PAGE_JS = """
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1440, right: 1080, bottom: 1440, left: 1800 }
      }
    },"""


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3.2.S.1 — DRUG SUBSTANCE GENERAL INFORMATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m3_s1(
    out_path: Path,
    fields: dict,
    config: Any,
    structure_image_path: Optional[str] = None,
) -> bool:
    """Generate 3.2.S.1 General Information DOCX."""

    drug_name  = _js_escape(_v(fields, "drug_name", config.drug_name))
    inn        = _js_escape(config.inn or config.drug_name)
    formula    = _js_escape(_v(fields, "molecular_formula"))
    mw         = _js_escape(str(_v(fields, "molecular_weight")))
    iupac      = _js_escape(_v(fields, "iupac_name"))
    smiles     = _js_escape(_v(fields, "smiles"))
    inchikey   = _js_escape(_v(fields, "inchikey"))
    desc       = _js_escape(_v(fields, "description"))
    storage    = _js_escape(_v(fields, "storage"))
    prod_name  = _js_escape(config.full_product_name)

    # Image handling
    image_js = ""
    if structure_image_path and Path(structure_image_path).exists():
        img_path = structure_image_path.replace("\\", "/")
        image_js = f"""
      new Paragraph({{
        alignment: AlignmentType.CENTER,
        children: [new ImageRun({{
          data: fs.readFileSync("{img_path}"),
          transformation: {{ width: 200, height: 200 }},
          type: "png",
        }})]
      }}),
      new Paragraph({{
        alignment: AlignmentType.CENTER,
        children: [new TextRun({{ text: "Figure 1: Chemical structure of {drug_name}", italics: true, size: 20 }})]
      }}),"""

    hf_js = _docx_header_footer_js(config.full_product_name, "3.2.S.1 General Information")

    border = "{ style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' }"
    borders_js = f"{{ top: {border}, bottom: {border}, left: {border}, right: {border} }}"

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         Header, Footer, ImageRun, HeadingLevel, AlignmentType,
         BorderStyle, WidthType, ShadingType, PageNumber }} = require('docx');
const fs = require('fs');

const border = {border};
const borders = {borders_js};
const cellOpts = (w) => ({{ borders, width: {{ size: w, type: WidthType.DXA }},
  margins: {{ top: 80, bottom: 80, left: 120, right: 120 }} }});
const hCell = (text, w) => new TableCell({{ ...cellOpts(w),
  shading: {{ fill: 'D5E8F0', type: ShadingType.CLEAR }},
  children: [new Paragraph({{ children: [new TextRun({{ text, bold: true, size: 22 }})] }})] }});
const dCell = (text, w) => new TableCell({{ ...cellOpts(w),
  children: [new Paragraph({{ children: [new TextRun({{ text, size: 22 }})] }})] }});

const doc = new Document({{
  {_DOCX_STYLES_JS}
  sections: [{{
    {_A4_PAGE_JS}
    {hf_js}
    children: [
      new Paragraph({{ heading: HeadingLevel.HEADING_1,
        children: [new TextRun("3.2.S.1 General Information")] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.1.1 Nomenclature")] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [2708, 6318],
        rows: [
          new TableRow({{ children: [ hCell("Approved Name (INN)", 2708), dCell("{inn}", 6318) ] }}),
          new TableRow({{ children: [ hCell("Pharmacopoeial Name", 2708), dCell("{drug_name}", 6318) ] }}),
          new TableRow({{ children: [ hCell("IUPAC Name", 2708), dCell("{iupac}", 6318) ] }}),
          new TableRow({{ children: [ hCell("Molecular Formula", 2708), dCell("{formula}", 6318) ] }}),
          new TableRow({{ children: [ hCell("Molecular Weight", 2708), dCell("{mw} g/mol", 6318) ] }}),
          new TableRow({{ children: [ hCell("InChIKey", 2708), dCell("{inchikey}", 6318) ] }}),
          new TableRow({{ children: [ hCell("CAS Number", 2708), dCell("[SEE FORMULA FIELD]", 6318) ] }}),
        ]
      }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.1.2 Structure")] }}),

      new Paragraph({{ children: [new TextRun({{ text: "SMILES: ", bold: true }}),
        new TextRun({{ text: "{smiles}", font: "Courier New", size: 20 }})] }}),

      {image_js}

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.1.3 General Properties")] }}),

      new Paragraph({{ children: [new TextRun({{ text: "Appearance: ", bold: true }}),
        new TextRun("{desc}")] }}),

      new Paragraph({{ children: [new TextRun({{ text: "Storage: ", bold: true }}),
        new TextRun("{storage}")] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.1.4 Pharmacopoeial Status")] }}),

      new Paragraph({{ children: [
        new TextRun("The drug substance {drug_name} is described in the British Pharmacopoeia (BP 2024) and the United States Pharmacopeia (USP 43). The BP monograph specification is used as the primary reference for this dossier.")
      ]}})
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('Generated: {out_path.name} (' + buf.length + ' bytes)');
}});
"""
    return _generate_docx_from_js(js, out_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3.2.S.4 — CONTROL OF DRUG SUBSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m3_s4(out_path: Path, fields: dict, config: Any) -> bool:
    """Generate 3.2.S.4 Control of Drug Substance DOCX."""

    drug_name = _js_escape(_v(fields, "drug_name", config.drug_name))
    assay_str = _js_escape(_assay_str(fields))
    lod_str   = _js_escape(_lod_str(fields))
    desc      = _js_escape(_v(fields, "description"))
    storage   = _js_escape(_v(fields, "storage"))
    hf_js     = _docx_header_footer_js(config.full_product_name, "3.2.S.4 Control of Drug Substance")

    border   = "{ style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' }"
    borders_js = f"{{ top: {border}, bottom: {border}, left: {border}, right: {border} }}"

    # Build identification tests rows
    id_entry = fields.get("identification", {})
    id_val   = id_entry.get("value") if isinstance(id_entry, dict) else []
    id_rows  = []
    if isinstance(id_val, list) and id_val:
        for item in id_val[:5]:
            if isinstance(item, dict):
                test   = _js_escape(item.get("test", "A"))
                method = _js_escape(item.get("method", ""))
                crit   = _js_escape((item.get("criterion") or "")[:100])
                id_rows.append(
                    f"new TableRow({{ children: [ dCell('{test}', 1000), dCell('{method}', 2500), dCell('{crit}', 5526) ] }}),"
                )
    if not id_rows:
        id_rows = ["new TableRow({ children: [ dCell('A', 1000), dCell('IR Spectrophotometry', 2500), dCell('Complies with BP reference spectrum', 5526) ] }),"]
    id_rows_js = "\n          ".join(id_rows)

    # Related substances
    rs_entry = fields.get("related_substances", {})
    rs_val   = rs_entry.get("value") if isinstance(rs_entry, dict) else []
    rs_text  = "[SEE BP MONOGRAPH]"
    if isinstance(rs_val, list) and rs_val:
        rs_text = "; ".join(
            (item.get("name") or "")[:60] for item in rs_val[:3]
            if isinstance(item, dict)
        ) or rs_text
    rs_text = _js_escape(rs_text)

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         Header, Footer, HeadingLevel, AlignmentType,
         BorderStyle, WidthType, ShadingType, PageNumber }} = require('docx');
const fs = require('fs');

const border = {border};
const borders = {borders_js};
const cellOpts = (w) => ({{ borders, width: {{ size: w, type: WidthType.DXA }},
  margins: {{ top: 80, bottom: 80, left: 120, right: 120 }} }});
const hCell = (text, w) => new TableCell({{ ...cellOpts(w),
  shading: {{ fill: 'D5E8F0', type: ShadingType.CLEAR }},
  children: [new Paragraph({{ children: [new TextRun({{ text, bold: true, size: 22 }})] }})] }});
const dCell = (text, w) => new TableCell({{ ...cellOpts(w),
  children: [new Paragraph({{ children: [new TextRun({{ text, size: 22 }})] }})] }});

const doc = new Document({{
  {_DOCX_STYLES_JS}
  sections: [{{
    {_A4_PAGE_JS}
    {hf_js}
    children: [
      new Paragraph({{ heading: HeadingLevel.HEADING_1,
        children: [new TextRun("3.2.S.4 Control of Drug Substance")] }}),

      new Paragraph({{ children: [new TextRun(
        "The drug substance {drug_name} is controlled in accordance with the British Pharmacopoeia (BP 2024) specification. The tests and acceptance criteria set out below are applied to each batch of drug substance."
      )]}}) ,

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.4.1 Specification")] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [2708, 3159, 3159],
        rows: [
          new TableRow({{ children: [
            hCell("Test", 2708), hCell("Method", 3159), hCell("Acceptance Criteria", 3159)
          ]}}),
          new TableRow({{ children: [
            dCell("Description", 2708), dCell("Visual", 3159), dCell("{desc}", 3159)
          ]}}),
          new TableRow({{ children: [
            dCell("Assay", 2708), dCell("HPLC (BP 2024)", 3159), dCell("{assay_str}", 3159)
          ]}}),
          new TableRow({{ children: [
            dCell("Related Substances", 2708), dCell("HPLC (BP 2024)", 3159), dCell("{rs_text}", 3159)
          ]}}),
          new TableRow({{ children: [
            dCell("Loss on Drying", 2708), dCell("BP 2.2.32", 3159), dCell("{lod_str}", 3159)
          ]}}),
          new TableRow({{ children: [
            dCell("Storage", 2708), dCell("—", 3159), dCell("{storage}", 3159)
          ]}}),
        ]
      }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.4.2 Analytical Procedures")] }}),

      new Paragraph({{ children: [new TextRun(
        "All analytical procedures are as described in the current edition of the British Pharmacopoeia (BP 2024). Copies of the relevant monograph sections are provided in the appendices."
      )]}}) ,

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.4.3 Identification Tests")] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [1000, 2500, 5526],
        rows: [
          new TableRow({{ children: [ hCell("Test", 1000), hCell("Method", 2500), hCell("Criterion", 5526) ] }}),
          {id_rows_js}
        ]
      }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.4.4 Batch Analyses")] }}),

      new Paragraph({{ children: [new TextRun(
        "Batch analysis data for three pilot-scale batches of {drug_name} are provided in the appendices. All batches complied with the specification."
      )]}}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.S.4.5 Justification of Specification")] }}),

      new Paragraph({{ children: [new TextRun(
        "The specification is based on the British Pharmacopoeia (BP 2024) monograph for {drug_name}. The pharmacopoeial specification is considered appropriate for this well-established active substance."
      )]}})
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('Generated: {out_path.name} (' + buf.length + ' bytes)');
}});
"""
    return _generate_docx_from_js(js, out_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 2.3 — QUALITY OVERALL SUMMARY (QOS)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m2_qos(out_path: Path, fields: dict, config: Any) -> bool:
    """Generate 2.3 Quality Overall Summary DOCX."""

    drug_name  = _js_escape(_v(fields, "drug_name", config.drug_name))
    formula    = _js_escape(_v(fields, "molecular_formula"))
    mw         = _js_escape(str(_v(fields, "molecular_weight")))
    desc       = _js_escape(_v(fields, "description"))
    assay_str  = _js_escape(_assay_str(fields))
    storage    = _js_escape(_v(fields, "storage"))
    prod_name  = _js_escape(config.full_product_name)
    applicant  = _js_escape(config.applicant)
    mfr        = _js_escape(config.manufacturer)
    strength   = _js_escape(config.strength)
    form       = _js_escape(config.dosage_form)
    hf_js      = _docx_header_footer_js(config.full_product_name, "2.3 Quality Overall Summary")

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         Header, Footer, HeadingLevel, AlignmentType,
         BorderStyle, WidthType, ShadingType, PageNumber }} = require('docx');
const fs = require('fs');

const border = {{ style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' }};
const borders = {{ top: border, bottom: border, left: border, right: border }};
const cellOpts = (w) => ({{ borders, width: {{ size: w, type: WidthType.DXA }},
  margins: {{ top: 80, bottom: 80, left: 120, right: 120 }} }});
const hCell = (text, w) => new TableCell({{ ...cellOpts(w),
  shading: {{ fill: 'D5E8F0', type: ShadingType.CLEAR }},
  children: [new Paragraph({{ children: [new TextRun({{ text, bold: true, size: 22 }})] }})] }});
const dCell = (text, w) => new TableCell({{ ...cellOpts(w),
  children: [new Paragraph({{ children: [new TextRun({{ text, size: 22 }})] }})] }});

const doc = new Document({{
  {_DOCX_STYLES_JS}
  sections: [{{
    {_A4_PAGE_JS}
    {hf_js}
    children: [
      new Paragraph({{ heading: HeadingLevel.HEADING_1,
        children: [new TextRun("2.3 Quality Overall Summary")] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("2.3.S Drug Substance")] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_3,
        children: [new TextRun("2.3.S.1 General Information")] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [3000, 6026],
        rows: [
          new TableRow({{ children: [ hCell("INN", 3000), dCell("{drug_name}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Molecular Formula", 3000), dCell("{formula}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Molecular Weight", 3000), dCell("{mw} g/mol", 6026) ] }}),
          new TableRow({{ children: [ hCell("Appearance", 3000), dCell("{desc}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Pharmacopoeial Status", 3000), dCell("BP 2024", 6026) ] }}),
          new TableRow({{ children: [ hCell("Storage", 3000), dCell("{storage}", 6026) ] }}),
        ]
      }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_3,
        children: [new TextRun("2.3.S.4 Control of Drug Substance")] }}),

      new Paragraph({{ children: [new TextRun(
        "The drug substance {drug_name} is controlled according to the BP 2024 specification. " +
        "The assay limits are {assay_str}. All batches have been shown to comply with the specification."
      )]}}) ,

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("2.3.P Drug Product")] }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_3,
        children: [new TextRun("2.3.P.1 Description and Composition")] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [3000, 6026],
        rows: [
          new TableRow({{ children: [ hCell("Product Name", 3000), dCell("{prod_name}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Dosage Form", 3000), dCell("{form}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Strength", 3000), dCell("{strength}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Applicant", 3000), dCell("{applicant}", 6026) ] }}),
          new TableRow({{ children: [ hCell("Manufacturer", 3000), dCell("{mfr}", 6026) ] }}),
        ]
      }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_3,
        children: [new TextRun("2.3.P.5 Control of Drug Product")] }}),

      new Paragraph({{ children: [new TextRun(
        "The drug product {prod_name} is tested in accordance with the specifications detailed in Module 3.2.P.5. " +
        "All release specifications are based on pharmacopoeial methods and established product knowledge."
      )]}})
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('Generated: {out_path.name} (' + buf.length + ' bytes)');
}});
"""
    return _generate_docx_from_js(js, out_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 1.1 — COVER LETTER
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m1_cover_letter(out_path: Path, fields: dict, config: Any) -> bool:
    """Generate Module 1.1 Cover Letter DOCX."""

    drug_name  = _js_escape(_v(fields, "drug_name", config.drug_name))
    prod_name  = _js_escape(config.full_product_name)
    applicant  = _js_escape(config.applicant)
    mfr        = _js_escape(config.manufacturer)
    country    = _js_escape(config.country_of_mfr)
    date_str   = _js_escape(config.submission_date)
    sub_type   = _js_escape(config.submission_type.replace("_", " ").title())
    hf_js      = _docx_header_footer_js(config.full_product_name, "Module 1 — Cover Letter")

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Header, Footer,
         HeadingLevel, AlignmentType, BorderStyle, PageNumber }} = require('docx');
const fs = require('fs');

const doc = new Document({{
  {_DOCX_STYLES_JS}
  sections: [{{
    {_A4_PAGE_JS}
    {hf_js}
    children: [
      new Paragraph({{ children: [new TextRun({{ text: "{date_str}", size: 22 }})] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun({{ text: "The Director General", bold: true, size: 22 }})] }}),
      new Paragraph({{ children: [new TextRun("National Agency for Food and Drug Administration and Control (NAFDAC)")] }}),
      new Paragraph({{ children: [new TextRun("Plot 2032, Olusegun Obasanjo Way, Zone 7, Wuse District")] }}),
      new Paragraph({{ children: [new TextRun("PMB 21, Garki, Abuja, Nigeria")] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun({{ text: "Dear Director General,", size: 22 }})] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("RE: Application for {sub_type} — {prod_name}")] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun(
        "We, {applicant}, hereby submit this application for the registration of {prod_name} " +
        "manufactured by {mfr}, {country}, with the National Agency for Food and Drug Administration and Control (NAFDAC)."
      )]}}) ,
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun(
        "This submission is presented in the ICH Common Technical Document (CTD) format as required by NAFDAC guidelines. " +
        "All information provided is accurate and complete to the best of our knowledge. We confirm that the product complies " +
        "with all applicable NAFDAC requirements and international quality standards."
      )]}}) ,
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun(
        "We enclose the following modules in support of this application:"
      )]}}) ,
      new Paragraph({{ children: [new TextRun("\\u2022  Module 1: Administrative Information and Prescribing Information")] }}),
      new Paragraph({{ children: [new TextRun("\\u2022  Module 2: CTD Summaries")] }}),
      new Paragraph({{ children: [new TextRun("\\u2022  Module 3: Quality")] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun(
        "We look forward to a favourable review of this application and remain available to provide any additional information required."
      )]}}) ,
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun("Yours faithfully,")] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [] }}),
      new Paragraph({{ children: [new TextRun({{ text: "_______________________________", color: "808080" }})] }}),
      new Paragraph({{ children: [new TextRun({{ text: "Authorised Signatory", bold: true }})] }}),
      new Paragraph({{ children: [new TextRun("{applicant}")] }}),
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('Generated: {out_path.name} (' + buf.length + ' bytes)');
}});
"""
    return _generate_docx_from_js(js, out_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3.2.P.1 — DRUG PRODUCT DESCRIPTION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_m3_p1(out_path: Path, fields: dict, config: Any) -> bool:
    """Generate 3.2.P.1 Description and Composition of Drug Product DOCX."""

    drug_name = _js_escape(_v(fields, "drug_name", config.drug_name))
    desc      = _js_escape(_v(fields, "description"))
    prod_name = _js_escape(config.full_product_name)
    strength  = _js_escape(config.strength)
    form      = _js_escape(config.dosage_form)
    mfr       = _js_escape(config.manufacturer)
    hf_js     = _docx_header_footer_js(config.full_product_name, "3.2.P.1 Description and Composition")

    # Parse strength number
    strength_num = ''.join(filter(str.isdigit, config.strength)) or '10'

    border = "{ style: BorderStyle.SINGLE, size: 1, color: 'CCCCCC' }"
    borders_js = f"{{ top: {border}, bottom: {border}, left: {border}, right: {border} }}"

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         Header, Footer, HeadingLevel, AlignmentType,
         BorderStyle, WidthType, ShadingType, PageNumber }} = require('docx');
const fs = require('fs');

const border = {border};
const borders = {borders_js};
const cellOpts = (w) => ({{ borders, width: {{ size: w, type: WidthType.DXA }},
  margins: {{ top: 80, bottom: 80, left: 120, right: 120 }} }});
const hCell = (text, w) => new TableCell({{ ...cellOpts(w),
  shading: {{ fill: 'D5E8F0', type: ShadingType.CLEAR }},
  children: [new Paragraph({{ children: [new TextRun({{ text, bold: true, size: 22 }})] }})] }});
const dCell = (text, w) => new TableCell({{ ...cellOpts(w),
  children: [new Paragraph({{ children: [new TextRun({{ text, size: 22 }})] }})] }});

const doc = new Document({{
  {_DOCX_STYLES_JS}
  sections: [{{
    {_A4_PAGE_JS}
    {hf_js}
    children: [
      new Paragraph({{ heading: HeadingLevel.HEADING_1,
        children: [new TextRun("3.2.P.1 Description and Composition of the Drug Product")] }}),

      new Paragraph({{ children: [new TextRun(
        "{prod_name} is a solid oral dosage form manufactured by {mfr}. " +
        "Each tablet contains {strength} of {drug_name} as the active pharmaceutical ingredient."
      )]}}) ,

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.P.1.1 Description")] }}),

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [2500, 6526],
        rows: [
          new TableRow({{ children: [ hCell("Product Name", 2500), dCell("{prod_name}", 6526) ] }}),
          new TableRow({{ children: [ hCell("Dosage Form", 2500), dCell("{form}", 6526) ] }}),
          new TableRow({{ children: [ hCell("Strength", 2500), dCell("{strength} {drug_name}", 6526) ] }}),
          new TableRow({{ children: [ hCell("Route of Admin.", 2500), dCell("Oral", 6526) ] }}),
          new TableRow({{ children: [ hCell("Physical Description", 2500), dCell("White to off-white film-coated tablet", 6526) ] }}),
          new TableRow({{ children: [ hCell("Pack Size", 2500), dCell("[TO BE COMPLETED]", 6526) ] }}),
        ]
      }}),

      new Paragraph({{ heading: HeadingLevel.HEADING_2,
        children: [new TextRun("3.2.P.1.2 Composition")] }}),

      new Paragraph({{ children: [new TextRun(
        "The qualitative and quantitative composition of {prod_name} is presented in the table below. " +
        "All excipients are of pharmacopoeial grade."
      )]}}) ,

      new Table({{
        width: {{ size: 9026, type: WidthType.DXA }},
        columnWidths: [3000, 1800, 1800, 2426],
        rows: [
          new TableRow({{ children: [
            hCell("Component", 3000), hCell("Grade", 1800),
            hCell("Amount per tablet", 1800), hCell("Function", 2426)
          ]}}),
          new TableRow({{ children: [
            dCell("{drug_name}", 3000), dCell("BP/USP", 1800),
            dCell("{strength_num} mg", 1800), dCell("Active substance", 2426)
          ]}}),
          new TableRow({{ children: [
            dCell("Microcrystalline Cellulose", 3000), dCell("Ph.Eur./NF", 1800),
            dCell("[X] mg", 1800), dCell("Diluent/Binder", 2426)
          ]}}),
          new TableRow({{ children: [
            dCell("Calcium Hydrogen Phosphate", 3000), dCell("Ph.Eur./NF", 1800),
            dCell("[X] mg", 1800), dCell("Diluent", 2426)
          ]}}),
          new TableRow({{ children: [
            dCell("Sodium Starch Glycolate", 3000), dCell("Ph.Eur./NF", 1800),
            dCell("[X] mg", 1800), dCell("Disintegrant", 2426)
          ]}}),
          new TableRow({{ children: [
            dCell("Magnesium Stearate", 3000), dCell("Ph.Eur./NF", 1800),
            dCell("[X] mg", 1800), dCell("Lubricant", 2426)
          ]}}),
          new TableRow({{ children: [
            dCell("Film coat (Opadry White)", 3000), dCell("NF", 1800),
            dCell("[X] mg", 1800), dCell("Film coating", 2426)
          ]}}),
          new TableRow({{ children: [
            hCell("Total tablet weight", 3000), hCell("", 1800),
            hCell("[X] mg", 1800), hCell("", 2426)
          ]}}),
        ]
      }}),

      new Paragraph({{ children: [new TextRun(
        "Note: Quantities marked [X] are to be completed from the product development data. " +
        "All excipients are compendial grade and their specifications are provided in Module 3.2.P.4."
      ), ]}})
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{str(out_path).replace(chr(92), '/')}", buf);
  console.log('Generated: {out_path.name} (' + buf.length + ' bytes)');
}});
"""
    return _generate_docx_from_js(js, out_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER GENERATE FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_all_modules(
    submission_root: str,
    resolved_spec: Optional[dict] = None,
    drug_name_for_spec: Optional[str] = None,
) -> dict:
    """
    Generate all pending DOCX files for a submission.

    Parameters
    ----------
    submission_root     : str   Path to the submission folder.
    resolved_spec       : dict  Output from spec_resolver.resolve_spec() (optional).
                                If None, tries to load from pharmacopoeia_db/resolved/.
    drug_name_for_spec  : str   Drug name to use for loading resolved spec.

    Returns
    -------
    dict  {generated: int, failed: int, skipped: int, files: list[str]}
    """
    from nafdac_structure import load_manifest, config_from_manifest, get_docx_path, update_document_status

    root     = Path(submission_root)
    manifest = load_manifest(submission_root)
    config   = config_from_manifest(submission_root)

    # Load resolved spec if not provided
    if resolved_spec is None:
        drug_key = drug_name_for_spec or config.drug_name
        spec_slug = drug_key.lower().replace(" ", "-")
        spec_path = Path("pharmacopoeia_db") / "resolved" / f"{spec_slug}.json"
        if not spec_path.exists():
            # Try normalised name
            import re
            spec_slug = re.sub(r"[^a-z0-9]+", "-", drug_key.lower()).strip("-")
            spec_path = Path("pharmacopoeia_db") / "resolved" / f"{spec_slug}.json"

        if spec_path.exists():
            resolved_spec = json.loads(spec_path.read_text(encoding="utf-8"))
            print(f"  Loaded spec: {spec_path.name}")
        else:
            print(f"  WARNING: No resolved spec found for '{drug_key}'")
            print(f"  Run: python cli.py resolve-spec \"{drug_key}\" --save")
            resolved_spec = {"fields": {}, "drug_name": config.drug_name}

    fields = resolved_spec.get("fields", {})

    # Structure image path
    struct_path = None
    struct_entry = fields.get("structure_image_path", {})
    if isinstance(struct_entry, dict):
        struct_path = struct_entry.get("value")

    # Generator dispatch table
  
    generators = {
        "1.1_cover_letter.docx":               lambda p: generate_m1_cover_letter(p, fields, config),
        "2.3_quality_overall_summary.docx":    lambda p: generate_m2_qos(p, fields, config),
        "3.2.S.1_general_information.docx":    lambda p: generate_m3_s1(p, fields, config, struct_path),
        "3.2.S.4.1_specifications.docx":       lambda p: generate_m3_s4(p, fields, config),
        "3.2.P.1_description_composition.docx": lambda p: generate_m3_p1(p, fields, config),
    }

    summary = {"generated": 0, "failed": 0, "skipped": 0, "files": []}
    total   = len(manifest.get("documents", []))

    print(f"\n{'='*60}")
    print(f"  Generating Module documents for: {config.full_product_name}")
    print(f"{'='*60}")

    for i, doc_entry in enumerate(manifest.get("documents", []), 1):
        filename = doc_entry["filename"]
        out_path = Path(doc_entry["path"])

        if filename not in generators:
            print(f"  [{i:2d}/{total}] SKIP  {filename}  (generator not yet implemented)")
            summary["skipped"] += 1
            continue

        print(f"  [{i:2d}/{total}] GEN   {filename}")
        try:
            ok = generators[filename](out_path)
            if ok:
                summary["generated"] += 1
                summary["files"].append(str(out_path))
                update_document_status(submission_root, filename, "generated")
            else:
                summary["failed"] += 1
                update_document_status(submission_root, filename, "failed")
        except Exception as exc:
            print(f"           ERROR: {exc}")
            summary["failed"] += 1

    print(f"\n  ── Generation complete ──")
    print(f"     Generated : {summary['generated']}")
    print(f"     Skipped   : {summary['skipped']}  (generators coming in next steps)")
    print(f"     Failed    : {summary['failed']}")
    return summary