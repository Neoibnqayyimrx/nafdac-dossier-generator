"""
ingestion/pdf_parser.py
=======================
Extracts structured content from an existing NAFDAC dossier in .pdf format
using pdfplumber. Handles:
  - Single-column and multi-column layouts
  - Embedded tables (with and without ruled lines)
  - Header/footer stripping
  - Section heading detection from font size and bold approximation

Returns the same ParsedDossier structure as docx_parser so the rest
of the pipeline (template_extractor, etc.) is format-agnostic.

Usage:
    from ingestion.pdf_parser import parse_dossier_pdf
    result = parse_dossier_pdf("path/to/dossier.pdf", "Amoxicillin 500mg")
    result.print_summary()
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from ingestion.docx_parser import (
    DossierSection,
    ParsedDossier,
    ParsedTable,
    _guess_module,
)


# ── Constants ────────────────────────────────────────────────────────────────

# Font size thresholds for heading detection.
# Typical NAFDAC dossier PDFs use ~14pt for H1, ~12pt for H2, ~11pt for H3.
# These are approximate — pdfplumber reports sizes in pts.
_H1_SIZE_MIN = 13.5
_H2_SIZE_MIN = 11.5
_H3_SIZE_MIN = 10.5
_BODY_SIZE_MAX = 11.0

# Strip headers/footers: ignore text in top/bottom N% of page height
_HEADER_MARGIN_FRAC = 0.06   # top 6%
_FOOTER_MARGIN_FRAC = 0.06   # bottom 6%

# Multi-column threshold: if text bbox midpoint x < this fraction of page width
# it's likely the left column of a 2-column layout
_COLUMN_SPLIT_FRAC = 0.52


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_likely_heading(word_group: list[dict]) -> tuple[bool, int]:
    """
    Given a list of pdfplumber word dicts on one line, guess if it's a heading.
    Returns (is_heading, level).
    """
    if not word_group:
        return False, 0

    sizes = [w.get("size", 0) for w in word_group if w.get("size")]
    if not sizes:
        return False, 0

    avg_size = sum(sizes) / len(sizes)
    text = " ".join(w["text"] for w in word_group).strip()

    # Very short lines (less than 3 chars) are not headings
    if len(text) < 3:
        return False, 0

    if avg_size >= _H1_SIZE_MIN:
        return True, 1
    if avg_size >= _H2_SIZE_MIN:
        return True, 2
    if avg_size >= _H3_SIZE_MIN:
        # Extra check: bold flag or ALL CAPS or numbered pattern
        is_bold = any(
            "bold" in (w.get("fontname") or "").lower() or
            "black" in (w.get("fontname") or "").lower()
            for w in word_group
        )
        is_numbered = bool(re.match(r"^\d+[\.\d]*\s", text))
        is_caps = text.isupper() and len(text) > 4
        if is_bold or is_numbered or is_caps:
            return True, 3

    return False, 0


def _words_to_lines(words: list[dict]) -> list[list[dict]]:
    """
    Group pdfplumber word dicts into lines by their top-y coordinate.
    Words within 2pt of each other vertically are on the same line.
    """
    if not words:
        return []

    lines: list[list[dict]] = []
    current_line: list[dict] = [words[0]]
    current_top = words[0]["top"]

    for word in words[1:]:
        if abs(word["top"] - current_top) <= 2:
            current_line.append(word)
        else:
            lines.append(sorted(current_line, key=lambda w: w["x0"]))
            current_line = [word]
            current_top = word["top"]

    if current_line:
        lines.append(sorted(current_line, key=lambda w: w["x0"]))

    return lines


def _line_to_text(line: list[dict]) -> str:
    """Convert a list of word dicts to a single string."""
    return " ".join(w["text"] for w in line).strip()


def _strip_header_footer(words: list[dict], page_height: float) -> list[dict]:
    """Remove words in top/bottom margin (likely page headers/footers)."""
    top_cut = page_height * _HEADER_MARGIN_FRAC
    bottom_cut = page_height * (1 - _FOOTER_MARGIN_FRAC)
    return [w for w in words if top_cut < w["top"] < bottom_cut]


def _detect_columns(words: list[dict], page_width: float) -> tuple[list[dict], list[dict]]:
    """
    Split words into left and right columns for 2-column layouts.
    Returns (left_words, right_words). For single-column, right_words is empty.
    """
    split_x = page_width * _COLUMN_SPLIT_FRAC

    # Check if there's a meaningful gap in x-distribution suggesting 2 columns
    midpoints = [w["x0"] + (w["x1"] - w["x0"]) / 2 for w in words]
    left_count = sum(1 for m in midpoints if m < split_x)
    right_count = sum(1 for m in midpoints if m >= split_x)

    # Only split if both columns have substantial content (> 15% of words each)
    total = len(words)
    if total > 0 and left_count / total > 0.15 and right_count / total > 0.15:
        left = sorted([w for w in words if w["x0"] < split_x], key=lambda w: (w["top"], w["x0"]))
        right = sorted([w for w in words if w["x0"] >= split_x], key=lambda w: (w["top"], w["x0"]))
        return left, right

    return words, []


# ── Table extraction ─────────────────────────────────────────────────────────

def _extract_pdf_tables(page: "pdfplumber.page.Page", section_heading: str) -> list[ParsedTable]:
    """Extract all tables from a pdfplumber page."""
    parsed_tables = []

    try:
        tables = page.extract_tables({
            "vertical_strategy": "lines_strict",
            "horizontal_strategy": "lines_strict",
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 3,
        })
    except Exception:
        tables = []

    # Fallback: try with more lenient strategy
    if not tables:
        try:
            tables = page.extract_tables({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 5,
            })
        except Exception:
            tables = []

    for raw_table in tables:
        if not raw_table or len(raw_table) < 2:
            continue

        # Clean cells
        cleaned: list[list[str]] = []
        for row in raw_table:
            cleaned_row = [
                (cell or "").replace("\n", " ").strip()
                for cell in row
            ]
            if any(cell for cell in cleaned_row):  # skip blank rows
                cleaned.append(cleaned_row)

        if not cleaned:
            continue

        # Determine headers
        first_row = cleaned[0]
        looks_like_header = (
            all(cell for cell in first_row) and
            not all(re.match(r"^\d+\.?\d*$", cell) for cell in first_row if cell)
        )

        if looks_like_header and len(cleaned) > 1:
            headers = first_row
            data_rows = cleaned[1:]
        else:
            headers = [f"col_{i}" for i in range(len(first_row))]
            data_rows = cleaned

        rows_as_dicts = []
        for row in data_rows:
            padded = row + [""] * (len(headers) - len(row))
            rows_as_dicts.append(dict(zip(headers, padded[: len(headers)])))

        parsed_tables.append(ParsedTable(
            section_heading=section_heading,
            headers=headers,
            rows=rows_as_dicts,
            raw_rows=cleaned,
        ))

    return parsed_tables


# ── Main parser ──────────────────────────────────────────────────────────────

class PdfParser:
    """
    Parses a NAFDAC dossier .pdf file into a ParsedDossier.

    Parameters
    ----------
    path : str | Path
    drug_name_hint : str
    """

    def __init__(self, path: str | Path, drug_name_hint: str = "") -> None:
        self.path = Path(path)
        self.drug_name_hint = drug_name_hint

        if not self.path.exists():
            raise FileNotFoundError(f"PDF not found: {self.path}")
        if self.path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a .pdf file, got: {self.path.suffix}")

    def parse(self) -> ParsedDossier:
        result = ParsedDossier(
            source_path=self.path,
            drug_name_hint=self.drug_name_hint,
        )

        all_sections: list[DossierSection] = []
        all_raw_tables: list[ParsedTable] = []

        current_section = DossierSection(
            heading="[PREAMBLE]",
            heading_level=0,
            paragraphs=[],
            tables=[],
        )

        with pdfplumber.open(str(self.path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_height = page.height
                page_width = page.width

                # ── Extract tables from this page first ──────────────────────
                page_tables = _extract_pdf_tables(page, current_section.heading)

                # ── Extract words, strip header/footer ──────────────────────
                words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=True,
                    extra_attrs=["size", "fontname"],
                )
                words = _strip_header_footer(words, page_height)

                # ── Handle multi-column layout ───────────────────────────────
                left_words, right_words = _detect_columns(words, page_width)
                column_sets = [left_words]
                if right_words:
                    column_sets.append(right_words)

                for col_words in column_sets:
                    lines = _words_to_lines(col_words)

                    for line in lines:
                        text = _line_to_text(line)
                        if not text or len(text) < 2:
                            continue

                        is_heading, level = _is_likely_heading(line)

                        if is_heading:
                            # Save current section
                            if current_section.paragraphs or current_section.tables:
                                current_section.raw_text = "\n".join(current_section.paragraphs)
                                current_section.module_guess = _guess_module(
                                    current_section.heading, current_section.raw_text
                                )
                                all_sections.append(current_section)

                            current_section = DossierSection(
                                heading=text,
                                heading_level=level,
                                paragraphs=[],
                                tables=[],
                            )

                            if level == 1 and not result.detected_title:
                                result.detected_title = text
                        else:
                            current_section.paragraphs.append(text)

                # Attach page tables to current section
                for pt in page_tables:
                    pt.section_heading = current_section.heading
                    current_section.tables.append(pt)
                    all_raw_tables.append(pt)

        # Final section
        if current_section.paragraphs or current_section.tables:
            current_section.raw_text = "\n".join(current_section.paragraphs)
            current_section.module_guess = _guess_module(
                current_section.heading, current_section.raw_text
            )
            all_sections.append(current_section)

        result.sections = all_sections
        result.raw_tables = all_raw_tables
        result.total_paragraphs = sum(len(s.paragraphs) for s in all_sections)
        result.total_tables = len(all_raw_tables)
        result.total_words = sum(s.word_count() for s in all_sections)

        return result


# ── Entry point ──────────────────────────────────────────────────────────────

def parse_dossier_pdf(path: str | Path, drug_name_hint: str = "") -> ParsedDossier:
    """Entry point called by CLI ingest command for PDF files."""
    parser = PdfParser(path, drug_name_hint)
    return parser.parse()


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <path_to_dossier.pdf> [drug_name]")
        sys.exit(1)
    path = sys.argv[1]
    drug = sys.argv[2] if len(sys.argv) > 2 else ""
    result = parse_dossier_pdf(path, drug)
    result.print_summary()
