"""
ingestion/template_extractor.py
================================
Steps 2.3 + 2.4 + 2.5 combined.

Takes a ParsedDossier (from docx_parser or pdf_parser) and:

  2.3 — Detects variable fields using regex + spaCy blank tokenizer:
         drug name, manufacturer, strength, dosage form, dates,
         batch numbers, storage conditions, shelf life, test limits,
         ATC codes, pharmacopoeia references, registration numbers.

  2.4 — Replaces detected variables with Jinja2 {{ placeholder }} syntax
         and generates .jinja2 template strings per section.

  2.5 — Saves .jinja2 template files into the templates/ folder,
         organised by module (module1_admin/, module2_quality/, etc.)
         and returns a TemplateLibrary manifest.

Usage:
    from ingestion.template_extractor import TemplateExtractor
    extractor = TemplateExtractor(parsed_dossier, drug_name_hint="Amoxicillin 500mg")
    library = extractor.extract_and_save(templates_root="templates/")
    library.print_summary()
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import spacy
from jinja2 import Environment

from ingestion.docx_parser import ParsedDossier, DossierSection, ParsedTable

# ── spaCy blank model (no download needed) ───────────────────────────────────
_nlp = spacy.blank("en")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.3  VARIABLE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DetectedVariable:
    """One detected variable field in a text."""
    original_text: str          # Exact matched text in source
    placeholder: str            # Jinja2 placeholder e.g. {{ drug.name }}
    category: str               # e.g. "drug_name", "manufacturer", "date"
    start: int                  # Character offset in source text
    end: int                    # Character offset in source text


# Each pattern: (category, jinja_placeholder, compiled_regex)
# Patterns are applied in order — more specific first.
def _build_patterns(drug_name_hint: str) -> list[tuple[str, str, re.Pattern]]:
    # Escape the hint for regex use; split into parts (name + strength if provided)
    hint_parts = drug_name_hint.strip().split()
    drug_name_words = [p for p in hint_parts if not re.match(r"^\d", p)]
    strength_words  = [p for p in hint_parts if re.match(r"^\d", p)]

    drug_name_re  = r"\b" + r"\s+".join(re.escape(w) for w in drug_name_words) + r"\b" if drug_name_words else r"(?!)"
    strength_re   = r"\b" + r"\s*".join(re.escape(w) for w in strength_words)  + r"\b" if strength_words else r"(?!)"

    patterns = [
        # ── Drug identity ────────────────────────────────────────────────────
        ("drug_name_strength",
         "{{ drug.name }} {{ drug.strength }}",
         re.compile(drug_name_re + r"\s+" + strength_re, re.IGNORECASE)
        ),
        ("drug_name",
         "{{ drug.name }}",
         re.compile(drug_name_re, re.IGNORECASE)
        ),
        ("strength",
         "{{ drug.strength }}",
         re.compile(r"\b\d+\s*(?:mg|mcg|g|ml|%|IU|µg)(?:/\d+\s*(?:mg|ml))?\b", re.IGNORECASE)
        ),
        ("dosage_form",
         "{{ drug.dosage_form }}",
         re.compile(
             r"\b(?:hard\s+gelatin\s+capsules?|soft\s+gelatin\s+capsules?|"
             r"film[\-\s]coated\s+tablets?|uncoated\s+tablets?|"
             r"capsules?|tablets?|syrup|suspension|injection|"
             r"cream|ointment|gel|suppositories|patches?|solution)\b",
             re.IGNORECASE,
         )
        ),
        ("route_of_administration",
         "{{ drug.route_of_administration }}",
         re.compile(
             r"\b(?:oral|intravenous|intramuscular|subcutaneous|topical|"
             r"rectal|transdermal|inhalation|ophthalmic|otic|nasal)\b",
             re.IGNORECASE,
         )
        ),
        ("atc_code",
         "{{ drug.atc_code }}",
         re.compile(r"\b[A-Z]\d{2}[A-Z]{2}\d{2}\b")
        ),

        # ── Manufacturer / applicant ─────────────────────────────────────────
        ("manufacturer_name",
         "{{ manufacturer.name }}",
         re.compile(
             r"\b(?:[A-Z][A-Za-z]+\s+){1,5}"
             r"(?:Pharmaceuticals?|Pharma|Laboratories?|Labs?|"
             r"Industries|Healthcare|Chemicals?|Manufacturing|Limited|Ltd\.?|PLC|Inc\.?|GmbH)\b"
         )
        ),

        # ── Dates ────────────────────────────────────────────────────────────
        ("date",
         "{{ submission_date }}",
         re.compile(
             r"\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|"
             r"August|September|October|November|December)\s+\d{4}|"
             r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b",
             re.IGNORECASE,
         )
        ),
        ("expiry_date",
         "{{ expiry_date }}",
         re.compile(r"\bexpir(?:y|es?|ation)\s+date\s*:?\s*[\w\s,/\-]+\b", re.IGNORECASE)
        ),

        # ── Batch / lot numbers ──────────────────────────────────────────────
        ("batch_number",
         "{{ batch_number }}",
         re.compile(
             r"\b(?:batch|lot)\s*(?:no\.?|number|#)?\s*:?\s*[A-Z0-9\-]{4,15}\b",
             re.IGNORECASE,
         )
        ),

        # ── Storage & stability ──────────────────────────────────────────────
        ("shelf_life",
         "{{ storage.shelf_life }}",
         re.compile(
             r"\b(?:shelf[\-\s]life|expiry period)\s*(?:of|:)?\s*\d+\s*months?\b",
             re.IGNORECASE,
         )
        ),
        ("storage_condition",
         "{{ storage.storage_conditions }}",
         re.compile(
             r"\bstore\s+(?:below|at|between|in|away from)\s+[^\.\n]{5,60}",
             re.IGNORECASE,
         )
        ),
        ("temperature",
         "{{ storage.temperature }}",
         re.compile(r"\b(?:below\s+)?(?:\d+)\s*°?\s*C\b", re.IGNORECASE)
        ),

        # ── Pharmacopoeia references ─────────────────────────────────────────
        ("pharmacopoeia_ref",
         "{{ drug.pharmacopoeia_standard }}",
         re.compile(
             r"\b(?:British\s+Pharmacopoeia|BP|United\s+States\s+Pharmacopeia|USP|"
             r"European\s+Pharmacopoeia|EP|International\s+Pharmacopoeia|Ph\.?\s*Int)\b"
             r"(?:\s+\d{4})?",
             re.IGNORECASE,
         )
        ),
        ("pharmacopoeia_year",
         "{{ pharmacopoeia_year }}",
         re.compile(r"\b(?:BP|USP|EP)\s+(\d{4})\b", re.IGNORECASE)
        ),

        # ── Specifications / test limits ─────────────────────────────────────
        ("assay_limit",
         "{{ specifications.assay_limit }}",
         re.compile(
             r"\b\d{2,3}\.?\d*\s*%\s*(?:to|–|-)\s*\d{2,3}\.?\d*\s*%\b",
             re.IGNORECASE,
         )
        ),
        ("nmt_limit",
         "{{ specifications.nmt_limit }}",
         re.compile(r"\bN[LM]T\s+\d+\.?\d*\s*%\b", re.IGNORECASE)
        ),

        # ── NAFDAC registration number ───────────────────────────────────────
        ("nafdac_number",
         "{{ registration.nafdac_registration_number }}",
         re.compile(r"\bNAFDAC\s*(?:Reg\.?\s*)?No\.?\s*:?\s*[A-Z0-9/\-]{5,20}\b", re.IGNORECASE)
        ),

        # ── Pack size ────────────────────────────────────────────────────────
        ("pack_size",
         "{{ storage.pack_size }}",
         re.compile(
             r"\b(?:blister\s+pack\s+of\s+\d+|pack\s+of\s+\d+|"
             r"\d+\s*(?:tablets?|capsules?)\s*(?:x\s*\d+\s*(?:strips?|blisters?)?)?)\b",
             re.IGNORECASE,
         )
        ),

        # ── Molecular formula ────────────────────────────────────────────────
        ("molecular_formula",
         "{{ drug.molecular_formula }}",
         re.compile(r"\b[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*){2,}\b")
        ),
        ("molecular_weight",
         "{{ drug.molecular_weight }}",
         re.compile(r"\b\d{2,4}\.?\d*\s*g/mol\b", re.IGNORECASE)
        ),

        # ── CAS number ───────────────────────────────────────────────────────
        ("cas_number",
         "{{ drug.cas_number }}",
         re.compile(r"\bCAS\s*(?:No\.?|Number)?\s*:?\s*\d{2,7}-\d{2}-\d\b", re.IGNORECASE)
        ),
    ]

    return [(cat, ph, pat) for cat, ph, pat in patterns]


def detect_variables(text: str, drug_name_hint: str) -> list[DetectedVariable]:
    """
    Find all variable fields in a block of text.
    Returns a list of DetectedVariable sorted by start position.
    Overlapping matches are resolved by keeping the longest match.
    """
    patterns = _build_patterns(drug_name_hint)
    found: list[DetectedVariable] = []

    for category, placeholder, pattern in patterns:
        for m in pattern.finditer(text):
            found.append(DetectedVariable(
                original_text=m.group(0),
                placeholder=placeholder,
                category=category,
                start=m.start(),
                end=m.end(),
            ))

    # Sort by start, then by length descending (longer match wins)
    found.sort(key=lambda v: (v.start, -(v.end - v.start)))

    # Remove overlapping matches (keep first/longest)
    deduplicated: list[DetectedVariable] = []
    last_end = -1
    for v in found:
        if v.start >= last_end:
            deduplicated.append(v)
            last_end = v.end

    return deduplicated


# ═══════════════════════════════════════════════════════════════════════════════
# 2.4  JINJA2 TEMPLATE GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def templatize_text(text: str, drug_name_hint: str) -> tuple[str, list[DetectedVariable]]:
    """
    Replace all detected variables in text with Jinja2 placeholders.
    Returns (templatized_text, list_of_detected_variables).
    """
    variables = detect_variables(text, drug_name_hint)

    if not variables:
        return text, []

    # Build replacement by walking through text segments
    result_parts = []
    prev_end = 0

    for var in variables:
        result_parts.append(text[prev_end:var.start])   # literal text before match
        result_parts.append(var.placeholder)             # Jinja2 placeholder
        prev_end = var.end

    result_parts.append(text[prev_end:])                 # remaining literal text
    return "".join(result_parts), variables


def templatize_table(table: ParsedTable, drug_name_hint: str) -> ParsedTable:
    """
    Templatize all cell values in a ParsedTable.
    Returns a new ParsedTable with placeholder-replaced cells.
    """
    new_rows = []
    for row_dict in table.rows:
        new_row = {}
        for col, val in row_dict.items():
            templatized, _ = templatize_text(val, drug_name_hint)
            new_row[col] = templatized
        new_rows.append(new_row)

    new_raw_rows = []
    for raw_row in table.raw_rows:
        new_raw_row = []
        for cell in raw_row:
            templatized, _ = templatize_text(cell, drug_name_hint)
            new_raw_row.append(templatized)
        new_raw_rows.append(new_raw_row)

    return ParsedTable(
        section_heading=table.section_heading,
        headers=table.headers,
        rows=new_rows,
        raw_rows=new_raw_rows,
    )


@dataclass
class TemplatizedSection:
    """A dossier section converted to a Jinja2 template."""
    original_heading: str
    template_heading: str
    heading_level: int
    module: str
    paragraphs: list[str]          # Templatized paragraph texts
    tables: list[ParsedTable]      # Templatized tables
    detected_variables: list[DetectedVariable]
    filename: str = ""             # Assigned during save step


def templatize_section(section: DossierSection, drug_name_hint: str) -> TemplatizedSection:
    """Convert one DossierSection into a TemplatizedSection."""
    all_vars: list[DetectedVariable] = []

    template_heading, h_vars = templatize_text(section.heading, drug_name_hint)
    all_vars.extend(h_vars)

    template_paragraphs = []
    for para in section.paragraphs:
        tp, p_vars = templatize_text(para, drug_name_hint)
        template_paragraphs.append(tp)
        all_vars.extend(p_vars)

    template_tables = []
    for tbl in section.tables:
        template_tables.append(templatize_table(tbl, drug_name_hint))

    return TemplatizedSection(
        original_heading=section.heading,
        template_heading=template_heading,
        heading_level=section.heading_level,
        module=section.module_guess or "unclassified",
        paragraphs=template_paragraphs,
        tables=template_tables,
        detected_variables=all_vars,
    )


def render_jinja2_template(ts: TemplatizedSection) -> str:
    """
    Convert a TemplatizedSection into a .jinja2 file string.
    Format: heading + paragraphs + tables as pipe-delimited text blocks.
    """
    lines = []

    # Heading marker
    prefix = "#" * max(ts.heading_level, 1)
    lines.append(f"{prefix} {ts.template_heading}")
    lines.append("")

    # Paragraphs
    for para in ts.paragraphs:
        if para.strip():
            lines.append(para)
            lines.append("")

    # Tables rendered as Jinja2-friendly pipe tables
    for tbl in ts.tables:
        if not tbl.headers:
            continue
        lines.append("{# TABLE #}")
        lines.append("| " + " | ".join(tbl.headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(tbl.headers)) + " |")
        for row in tbl.rows:
            row_vals = [str(row.get(h, "")) for h in tbl.headers]
            lines.append("| " + " | ".join(row_vals) + " |")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 2.5  TEMPLATE LIBRARY SAVER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TemplateManifestEntry:
    filename: str
    module: str
    original_heading: str
    variable_count: int
    variable_categories: list[str]


@dataclass
class TemplateLibrary:
    source_drug: str
    source_file: str
    templates_root: str
    entries: list[TemplateManifestEntry] = field(default_factory=list)
    total_variables_detected: int = 0

    def print_summary(self) -> None:
        from rich.console import Console
        from rich.table import Table as RichTable
        console = Console()
        console.print(f"\n[bold green]Template Library Built[/bold green]")
        console.print(f"  Source drug  : {self.source_drug}")
        console.print(f"  Source file  : {self.source_file}")
        console.print(f"  Templates    : {len(self.entries)}")
        console.print(f"  Total vars   : {self.total_variables_detected}")
        console.print()
        tbl = RichTable(title="Saved Templates", show_lines=True)
        tbl.add_column("Module", style="yellow")
        tbl.add_column("File", style="cyan")
        tbl.add_column("Vars", justify="right")
        tbl.add_column("Categories")
        for entry in self.entries:
            tbl.add_row(
                entry.module,
                entry.filename,
                str(entry.variable_count),
                ", ".join(sorted(set(entry.variable_categories)))[:60],
            )
        console.print(tbl)

    def save_manifest(self, path: str | Path) -> None:
        manifest = {
            "source_drug": self.source_drug,
            "source_file": self.source_file,
            "templates_root": self.templates_root,
            "total_variables": self.total_variables_detected,
            "entries": [
                {
                    "filename": e.filename,
                    "module": e.module,
                    "original_heading": e.original_heading,
                    "variable_count": e.variable_count,
                    "variable_categories": e.variable_categories,
                }
                for e in self.entries
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)


def _safe_filename(heading: str, max_len: int = 50) -> str:
    """Convert a heading to a filesystem-safe filename."""
    text = unicodedata.normalize("NFKD", heading)
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", "_", text.strip()).lower()
    text = re.sub(r"_+", "_", text)
    return text[:max_len].strip("_")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXTRACTOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class TemplateExtractor:
    """
    Orchestrates steps 2.3 + 2.4 + 2.5.

    Parameters
    ----------
    parsed_dossier : ParsedDossier
        Output from DocxParser or PdfParser.
    drug_name_hint : str
        The drug name+strength from --drug CLI flag.
    """

    def __init__(self, parsed_dossier: ParsedDossier, drug_name_hint: str = "") -> None:
        self.dossier = parsed_dossier
        self.drug_name_hint = drug_name_hint or parsed_dossier.drug_name_hint

    def extract_and_save(self, templates_root: str | Path = "templates/") -> TemplateLibrary:
        """
        Run full extraction and save .jinja2 files.
        Returns a TemplateLibrary manifest.
        """
        root = Path(templates_root)
        root.mkdir(parents=True, exist_ok=True)

        # Ensure module subdirs exist
        for mod in [
            "module1_admin", "module2_quality", "module3_quality",
            "module4_safety", "module5_efficacy", "module5_pil_smpc", "unclassified"
        ]:
            (root / mod).mkdir(exist_ok=True)

        library = TemplateLibrary(
            source_drug=self.drug_name_hint,
            source_file=str(self.dossier.source_path),
            templates_root=str(root),
        )

        # Track filenames to avoid overwriting if two sections have same heading
        used_filenames: dict[str, int] = {}

        for section in self.dossier.sections:
            if section.is_empty():
                continue

            ts = templatize_section(section, self.drug_name_hint)

            # Build filename
            base_name = _safe_filename(ts.original_heading) or "section"
            if base_name in used_filenames:
                used_filenames[base_name] += 1
                base_name = f"{base_name}_{used_filenames[base_name]}"
            else:
                used_filenames[base_name] = 1

            filename = f"{base_name}.jinja2"
            ts.filename = filename

            # Write .jinja2 file
            module_dir = root / ts.module
            output_path = module_dir / filename
            jinja_content = render_jinja2_template(ts)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"{{#\n  Source: {self.dossier.source_path.name}\n")
                f.write(f"  Drug  : {self.drug_name_hint}\n")
                f.write(f"  Module: {ts.module}\n")
                f.write(f"  Vars  : {len(ts.detected_variables)}\n#}}\n\n")
                f.write(jinja_content)

            # Build manifest entry
            var_categories = [v.category for v in ts.detected_variables]
            entry = TemplateManifestEntry(
                filename=str(output_path.relative_to(root)),
                module=ts.module,
                original_heading=ts.original_heading,
                variable_count=len(ts.detected_variables),
                variable_categories=var_categories,
            )
            library.entries.append(entry)
            library.total_variables_detected += len(ts.detected_variables)

        # Save manifest JSON
        manifest_path = root / "manifest.json"
        library.save_manifest(manifest_path)

        return library


# ── CLI-facing function ──────────────────────────────────────────────────────

def extract_templates(
    parsed_dossier: ParsedDossier,
    drug_name_hint: str,
    templates_root: str | Path = "templates/",
) -> TemplateLibrary:
    """Entry point called by CLI ingest command after parsing."""
    extractor = TemplateExtractor(parsed_dossier, drug_name_hint)
    return extractor.extract_and_save(templates_root)


if __name__ == "__main__":
    import sys
    from ingestion.docx_parser import parse_dossier_docx

    if len(sys.argv) < 3:
        print("Usage: python template_extractor.py <dossier.docx> <drug_name>")
        sys.exit(1)

    dossier = parse_dossier_docx(sys.argv[1], sys.argv[2])
    library = extract_templates(dossier, sys.argv[2])
    library.print_summary()
