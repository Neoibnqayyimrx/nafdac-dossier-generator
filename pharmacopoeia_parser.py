"""
pharmacopoeia_parser.py
=======================
Parses British Pharmacopoeia (BP) HTML files and United States Pharmacopeia
(USP) PDF files, extracting structured data for the NAFDAC dossier generator.

Format routing
--------------
  BP  → HTML parsed with BeautifulSoup (pharmacopoeia.com structure)
        Source: one .html file per monograph
        Location: pharmacopoeia_db/BP/BP 2024/BP 2024 (EP 11.3)/monographs/

  USP → PDF parsed with pdfplumber (hybrid PDFs from uspnf.com)
        Source: one .pdf file per monograph, named "USP-NF <Drug Name>.pdf"
        Location: pharmacopoeia_db/USP/USP 43-NF38/USP 43 A to Z/<Letter>/
        NOTE: Page 1 is image-rendered (DEFINITION/IDENTIFICATION/ASSAY
              unextractable). Pages 2+ are text-based. Fields from page 1
              are filled by PubChem (step 3.3) via the spec_resolver (step 3.4).

Extracted fields (both sources)
--------------------------------
  drug_name             : str
  source                : "BP" | "USP"
  edition               : str | None
  molecular_formula     : str | None
  description           : str | None
  identification        : list[dict]
  assay                 : dict  {method, limits, units, raw}
  related_substances    : list[dict]
  dissolution           : dict
  storage               : str | None
  microbial_limits      : dict
  loss_on_drying        : dict | None
  water_content         : dict | None
  uniformity            : dict | None
  impurities            : list[dict]
  raw_sections          : dict
  parse_warnings        : list[str]

Usage
-----
  from pharmacopoeia_parser import parse_monograph
  result = parse_monograph("monographs/metformin-hydrochloride.html", source="BP")
  result = parse_monograph("M/USP-NF Metformin Hydrochloride.pdf",   source="USP")

CLI
---
  python pharmacopoeia_parser.py metformin-hydrochloride.html --source BP --validate
  python pharmacopoeia_parser.py "USP-NF Metformin Hydrochloride.pdf" --source USP
  python pharmacopoeia_parser.py metformin-hydrochloride.html --source BP --sections-only
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _clean(text: str) -> str:
    text = text.replace("\xa0", " ")   # non-breaking space
    text = text.replace("\u2009", " ")  # thin space
    text = text.replace("\u202f", " ")  # narrow no-break space
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _infer_method(text: str) -> str:
    t = text.upper()
    if "INFRARED" in t or re.search(r"\bIR\b", t):
        return "IR spectrophotometry"
    if "HPLC" in t or "HIGH-PERFORMANCE LIQUID" in t or "LIQUID CHROMATOGRAPHY" in t:
        return "HPLC"
    if re.search(r"\bLC\b", t):
        return "HPLC"
    if "TLC" in t or "THIN-LAYER" in t or "THIN LAYER" in t:
        return "TLC"
    if "ULTRAVIOLET" in t or re.search(r"\bUV\b", t):
        return "UV spectrophotometry"
    if "MELTING POINT" in t or "MELTING-POINT" in t:
        return "Melting point"
    if "RAMAN" in t:
        return "Raman spectroscopy"
    if "GAS CHROMATOGRAPHY" in t or re.search(r"\bGC\b", t):
        return "GC"
    if "TITRAT" in t:
        return "Titration"
    if "CHEMICAL" in t or "REACTION" in t or "COLOUR" in t or "COLOR" in t:
        return "Chemical test"
    return "Unspecified"


# shared limit patterns
_ASSAY_RANGE_RE = re.compile(
    r"(\d{2,3}(?:\.\d+)?)\s*(?:per\s+cent)?\s*%?\s*(?:per\s+cent\s+)?(?:to|\u2013|\u2014|-)\s*(\d{2,3}(?:\.\d+)?)\s*(?:per\s+cent|%)?",
    re.IGNORECASE,
)
_ASSAY_NLT_RE = re.compile(
    r"(?:not\s+less\s+than|NLT)\s+(\d{2,3}(?:\.\d+)?)\s*(?:per\s+cent|%)", re.IGNORECASE)
_ASSAY_NMT_RE = re.compile(
    r"(?:not\s+more\s+than|NMT)\s+(\d{2,3}(?:\.\d+)?)\s*(?:per\s+cent|%)", re.IGNORECASE)
_LIMIT_RE  = re.compile(r"NMT\s+(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*(?:per\s+cent|%)", re.IGNORECASE)
_RRT_RE    = re.compile(r"RRT\s*[:\s]\s*(\d+\.\d+)", re.IGNORECASE)
_LOD_TEMP_RE = re.compile(r"(\d{2,3})\s*°?\s*[Cc]")
_TAMC_RE = re.compile(
    r"(?:TAMC|Total\s+Aerobic\s+Microbial\s+Count)[^\d]*(\d[\d\s×xX10^]*)\s*(?:CFU|cfu)", re.IGNORECASE)
_TYMC_RE = re.compile(
    r"(?:TYMC|Total\s+(?:Yeast|Combined\s+Mold)[^\d]*Count)[^\d]*(\d[\d\s×xX10^]*)\s*(?:CFU|cfu)", re.IGNORECASE)
_PATHOGENS = [
    "Escherichia coli", "Salmonella", "Staphylococcus aureus",
    "Pseudomonas aeruginosa", "Clostridium",
]


def _extract_assay_limits(raw: str) -> Optional[dict]:
    m = _ASSAY_RANGE_RE.search(raw)
    if m:
        return {"min": float(m.group(1)), "max": float(m.group(2))}
    nlt = _ASSAY_NLT_RE.search(raw)
    nmt = _ASSAY_NMT_RE.search(raw)
    if nlt or nmt:
        return {
            "min": float(nlt.group(1)) if nlt else None,
            "max": float(nmt.group(1)) if nmt else None,
        }
    return None


def _extract_dissolution_fields(raw: str) -> dict:
    result: dict[str, Any] = {
        "apparatus": None, "medium": None, "rpm": None,
        "time_min": None, "limit_pct": None,
        "method": _infer_method(raw), "raw": _clean(raw)[:600],
    }
    m = re.search(r"[Aa]pparatus\s+(\d+|[IV]+)", raw)
    if m:
        result["apparatus"] = f"Apparatus {m.group(1)}"
    m = re.search(r"[Mm]edium\s*[:\-]?\s*(.+?)(?:;|\n|,\s*\d)", raw)
    if m:
        result["medium"] = _clean(m.group(1))[:120]
    m = re.search(r"(\d+)\s*rpm", raw, re.IGNORECASE)
    if m:
        result["rpm"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:minutes?|mins?|h(?:ours?)?)", raw, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        result["time_min"] = val * 60 if "h" in m.group(0).lower() else val
    m = re.search(r"Q\s*=?\s*(\d+)\s*%", raw, re.IGNORECASE) or \
        re.search(r"(?:NLT|not\s+less\s+than)\s+(\d+)\s*%", raw, re.IGNORECASE)
    if m:
        result["limit_pct"] = int(m.group(1))
    return result


def _extract_microbial_fields(raw: str) -> dict:
    result: dict[str, Any] = {
        "TAMC": None, "TYMC": None,
        "pathogens": [], "method": "Ph. Eur. 2.6.12 / USP <61><62>",
        "raw": _clean(raw)[:500],
    }
    m = _TAMC_RE.search(raw)
    if m:
        result["TAMC"] = m.group(1).strip() + " CFU/g"
    m = _TYMC_RE.search(raw)
    if m:
        result["TYMC"] = m.group(1).strip() + " CFU/g"
    for p in _PATHOGENS:
        if re.search(re.escape(p), raw, re.IGNORECASE):
            result["pathogens"].append(p)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# BP  ──  HTML PARSER  (BeautifulSoup)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_bp_html(html_path: str) -> dict:
    """
    Parse a BP Online HTML monograph (pharmacopoeia.com structure).

    Key HTML anchors:
      Drug name    : <h1 class="euro">
      Edition      : <div class="version-title"><strong>Edition: …</strong>
      Mol formula  : <div class="para_formula">
      Main sections: <h2 class="mainheading"> inside <section class="section">
      Sub-sections : <h3 class="sub_general"> inside <div class="subsection">
      Ident tests  : <div class="para_num1"> / <div class="para_num1bottom">
      Storage      : <h3 class="sub_general"> with text "Storage" OR
                     standalone <section> with <h2>STORAGE</h2>
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("beautifulsoup4 is required. Run: python -m pip install beautifulsoup4 lxml")

    warnings: list[str] = []

    with open(html_path, encoding="utf-8", errors="replace") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    # ── Drug name ─────────────────────────────────────────────────────────────
    h1 = soup.find("h1", class_="euro")
    # Strip the "Maximise" button text injected by pharmacopoeia.com full-screen button
    drug_name = re.sub(r"\s*Maximise\s*", "", h1.get_text()).strip() if h1 else Path(html_path).stem.replace("-", " ").title()
    drug_name = _clean(drug_name)

    # ── Edition ───────────────────────────────────────────────────────────────
    vt = soup.find("div", class_="version-title")
    edition = None
    if vt:
        m = re.search(r"Edition:\s*(.+?)(?:\(|$)", vt.get_text())
        edition = m.group(1).strip() if m else _clean(vt.get_text())[:60]
    if not edition:
        m = re.search(r"BP\s+(\d{4})", html[:3000])
        edition = f"BP {m.group(1)}" if m else None

    # ── Molecular formula ─────────────────────────────────────────────────────
    molecular_formula = None
    pf = soup.find("div", class_="para_formula")
    if pf:
        for sub in pf.find_all("sub"):
            sub.replace_with(sub.get_text())
        molecular_formula = _clean(pf.get_text())[:80]

    # ── Collect main sections ─────────────────────────────────────────────────
    raw_sections: dict[str, str] = {}
    section_soups: dict[str, Any] = {}

    for section in soup.find_all("section", class_="section"):
        h2 = section.find("h2", class_="mainheading")
        if not h2:
            continue
        heading = _clean(h2.get_text()).upper()
        raw_sections[heading] = _clean(section.get_text())[:2000]
        section_soups[heading] = section

    if not raw_sections:
        warnings.append("No <h2 class='mainheading'> sections found.")

    # ── Storage: check sub-sections across all sections ───────────────────────
    # BP Metformin puts Storage as a <h3 class="sub_general"> inside TESTS or
    # as a standalone section. We scan all sub-sections for it.
    storage = None
    for sec_name, sec_node in section_soups.items():
        for subsec in sec_node.find_all("div", class_="subsection"):
            h3 = subsec.find("h3", class_="sub_general")
            if h3 and re.search(r"^storage$", _clean(h3.get_text()), re.IGNORECASE):
                h3.decompose()
                storage = _clean(subsec.get_text())[:300]
                break
        if storage:
            break
    # Fallback: look for a <section> whose h2 contains STORAGE
    if not storage and "STORAGE" in section_soups:
        raw_stor = _clean(section_soups["STORAGE"].get_text())
        storage = raw_stor[:300]

    # ── Description ───────────────────────────────────────────────────────────
    description = None
    for key in ("CHARACTERS", "DESCRIPTION", "DEFINITION"):
        sec = section_soups.get(key)
        if not sec:
            continue
        app_div = sec.find("div", class_="subsection")
        if app_div:
            h3 = app_div.find("h3")
            if h3:
                h3.decompose()
            description = _clean(app_div.get_text())[:600]
        else:
            description = _clean(sec.get_text())[:600]
        break

    # ── Assay ──────────────────────────────────────────────────────────────────
    assay: dict[str, Any] = {"method": None, "limits": None, "units": "%w/w", "raw": None}
    assay_sec = section_soups.get("ASSAY")
    if assay_sec:
        raw_assay = _clean(assay_sec.get_text())
        assay["method"] = _infer_method(raw_assay)
        assay["limits"] = _extract_assay_limits(raw_assay)
        assay["raw"]    = raw_assay[:600]

    # Fallback: DEFINITION > Content sub-section
    # BP glues "Content" directly to the number: "Content98.5 per cent to 101.0 per cent"
    # so we search the Content <h3 class="sub_general"> sub-section specifically.
    if not assay["limits"]:
        def_sec = section_soups.get("DEFINITION")
        if def_sec:
            # First try the dedicated Content sub-section
            for subsec in def_sec.find_all("div", class_="subsection"):
                h3 = subsec.find("h3", class_="sub_general")
                if h3 and re.search(r"^content$", _clean(h3.get_text()), re.IGNORECASE):
                    content_text = _clean(subsec.get_text())
                    # Insert space before digit if glued: "Content98.5" → "Content 98.5"
                    content_text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", content_text)
                    assay["limits"] = _extract_assay_limits(content_text)
                    if assay["limits"]:
                        assay["method"] = assay["method"] or "See Assay section"
                        assay["raw"]    = assay["raw"] or content_text[:300]
                    break
            # Broader fallback: full DEFINITION text with same space-insertion fix
            if not assay["limits"]:
                raw_def = _clean(def_sec.get_text())
                raw_def = re.sub(r"([A-Za-z])(\d)", r"\1 \2", raw_def)
                assay["limits"] = _extract_assay_limits(raw_def)
                if assay["limits"] and not assay["method"]:
                    assay["method"] = "See Assay section"
                    assay["raw"]    = raw_def[:600]

    # ── Identification ─────────────────────────────────────────────────────────
    identification: list[dict] = []
    id_sec = section_soups.get("IDENTIFICATION")
    if id_sec:
        test_divs = id_sec.find_all("div", class_=re.compile(r"para_num1"))
        if test_divs:
            for div in test_divs:
                text = _clean(div.get_text())
                marker_m = re.match(r"^([A-Z])\.\s*", text)
                marker = marker_m.group(1) if marker_m else "?"
                body   = text[marker_m.end():] if marker_m else text
                identification.append({
                    "test":      marker,
                    "method":    _infer_method(body),
                    "criterion": body[:400],
                })
        else:
            raw_id = _clean(id_sec.get_text())
            identification.append({
                "test": "A", "method": _infer_method(raw_id),
                "criterion": raw_id[:600],
            })

    # ── Related substances (sub-section of TESTS) ─────────────────────────────
    related_substances: list[dict] = []
    tests_sec = section_soups.get("TESTS")
    if tests_sec:
        for subsec in tests_sec.find_all("div", class_="subsection"):
            h3 = subsec.find("h3")
            if not h3:
                continue
            h3_text = _clean(h3.get_text()).upper()
            if "RELATED" in h3_text or "IMPURIT" in h3_text:
                raw_rs = _clean(subsec.get_text())
                blocks = re.split(r"\n\s*\n|\n(?=[A-Z][a-z])", raw_rs)
                for block in blocks:
                    block = _clean(block)
                    if len(block) < 15:
                        continue
                    lm = _LIMIT_RE.search(block)
                    rm = _RRT_RE.search(block)
                    limit_val = None
                    if lm:
                        limit_val = float(lm.group(1) or lm.group(2))
                    related_substances.append({
                        "name":       block[:80],
                        "limit":      limit_val,
                        "limit_unit": "%",
                        "rrt":        float(rm.group(1)) if rm else None,
                        "method":     _infer_method(block),
                    })
                break

    # ── Dissolution ────────────────────────────────────────────────────────────
    dissolution: dict = {"apparatus": None, "medium": None, "rpm": None,
                         "time_min": None, "limit_pct": None, "method": None, "raw": None}
    if "DISSOLUTION" in section_soups:
        dissolution = _extract_dissolution_fields(_clean(section_soups["DISSOLUTION"].get_text()))

    # ── Microbial limits ───────────────────────────────────────────────────────
    microbial_limits: dict = {"TAMC": None, "TYMC": None,
                               "pathogens": [], "method": None, "raw": None}
    for key in ("MICROBIAL CONTAMINATION", "MICROBIAL EXAMINATION", "MICROBIAL LIMITS"):
        if key in section_soups:
            microbial_limits = _extract_microbial_fields(raw_sections[key])
            break

    # ── Loss on drying (sub-section of TESTS) ─────────────────────────────────
    loss_on_drying = None
    if tests_sec:
        for subsec in tests_sec.find_all("div", class_="subsection"):
            h3 = subsec.find("h3")
            if h3 and re.search(r"loss\s+on\s+drying", _clean(h3.get_text()), re.IGNORECASE):
                lod_raw = _clean(subsec.get_text())
                lm = _LIMIT_RE.search(lod_raw)
                tm = _LOD_TEMP_RE.search(lod_raw)
                limit_val = None
                if lm:
                    limit_val = float(lm.group(1) or lm.group(2))
                loss_on_drying = {
                    "limit_pct":     limit_val,
                    "temperature_c": int(tm.group(1)) if tm else None,
                    "method":        "Gravimetric (Ph. Eur. 2.2.32)",
                }
                break
    if not loss_on_drying and "LOSS ON DRYING" in section_soups:
        lod_raw = _clean(section_soups["LOSS ON DRYING"].get_text())
        lm = _LIMIT_RE.search(lod_raw)
        tm = _LOD_TEMP_RE.search(lod_raw)
        limit_val = None
        if lm:
            limit_val = float(lm.group(1) or lm.group(2))
        loss_on_drying = {
            "limit_pct":     limit_val,
            "temperature_c": int(tm.group(1)) if tm else None,
            "method":        "Gravimetric (Ph. Eur. 2.2.32)",
        }

    # ── Water content ──────────────────────────────────────────────────────────
    water_content = None
    for key in ("WATER", "WATER CONTENT", "WATER DETERMINATION"):
        if key in section_soups:
            raw_w = _clean(section_soups[key].get_text())
            lm = _LIMIT_RE.search(raw_w)
            limit_val = float(lm.group(1) or lm.group(2)) if lm else None
            water_content = {
                "limit_pct": limit_val,
                "method": "Karl Fischer titration" if re.search(r"karl|fischer", raw_w, re.I)
                          else "Gravimetric",
            }
            break

    # ── Uniformity ─────────────────────────────────────────────────────────────
    uniformity = None
    for key in ("UNIFORMITY OF CONTENT", "CONTENT UNIFORMITY", "UNIFORMITY OF DOSAGE UNITS"):
        if key in section_soups:
            raw_u = _clean(section_soups[key].get_text())
            crit_m = re.search(r"AV\s*[≤<=]\s*(\d+(?:\.\d+)?)", raw_u)
            uniformity = {
                "method": "Ph. Eur. 2.9.6 / USP <905>",
                "criterion": (f"AV ≤ {crit_m.group(1)}" if crit_m
                              else "Meets requirements" if "meets requirements" in raw_u.lower()
                              else _clean(raw_u)[:200]),
            }
            break

    # ── Impurities section ─────────────────────────────────────────────────────
    impurities: list[dict] = []
    if "IMPURITIES" in section_soups:
        raw_imp = _clean(section_soups["IMPURITIES"].get_text())
        for block in re.split(r"\n\s*\n|\n(?=[A-Z]\.\s)", raw_imp):
            block = _clean(block)
            if len(block) < 10:
                continue
            lm = _LIMIT_RE.search(block)
            rm = _RRT_RE.search(block)
            limit_val = None
            if lm:
                limit_val = float(lm.group(1) or lm.group(2))
            impurities.append({
                "name":       block[:80],
                "limit":      limit_val,
                "limit_unit": "%",
                "rrt":        float(rm.group(1)) if rm else None,
                "method":     _infer_method(block),
            })

    # ── Warnings ───────────────────────────────────────────────────────────────
    if not storage:
        warnings.append(
            "INFO: storage not found — expected for BP raw material monographs "
            "(storage conditions are in BP General Notices). Will use PubChem fallback."
        )
    if not assay["limits"]:
        warnings.append("MISSING: assay limits.")
    if not identification:
        warnings.append("MISSING: identification tests.")

    return {
        "drug_name":          drug_name,
        "source":             "BP",
        "edition":            edition,
        "molecular_formula":  molecular_formula,
        "description":        description,
        "identification":     identification,
        "assay":              assay,
        "related_substances": related_substances,
        "dissolution":        dissolution,
        "storage":            storage,
        "microbial_limits":   microbial_limits,
        "loss_on_drying":     loss_on_drying,
        "water_content":      water_content,
        "uniformity":         uniformity,
        "impurities":         impurities,
        "raw_sections":       raw_sections,
        "parse_warnings":     warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# USP  ──  PDF PARSER  (pdfplumber + regex)
# ═══════════════════════════════════════════════════════════════════════════════
#
# USP PDF structure (uspnf.com downloaded PDFs):
#   - Page 1  : image-rendered → DEFINITION, IDENTIFICATION, ASSAY unextractable
#   - Pages 2+: text-based with these patterns:
#       Main sections : ALL-CAPS standalone line  e.g. IMPURITIES, SPECIFIC TESTS
#       Sub-fields    : •FIELD NAME 〈ref〉:  e.g. •LOSS ON DRYING 〈731〉
#       Assay limits  : en-dash format  e.g. 98.0%–102.0%
#       Storage       : •PACKAGING AND STORAGE: inside ADDITIONAL REQUIREMENTS
#   - Missing fields from page 1 are filled by PubChem via spec_resolver (step 3.4)

_USP_MAIN_SECTIONS = re.compile(
    r"^(IMPURITIES|SPECIFIC\s+TESTS|ADDITIONAL\s+REQUIREMENTS|"
    r"PERFORMANCE\s+TESTS|MICROBIOLOGICAL\s+TESTS|"
    r"DEFINITION|IDENTIFICATION|ASSAY|DISSOLUTION|LABELING)$",
    re.MULTILINE | re.IGNORECASE,
)

# Bullet sub-field: •FIELD NAME 〈ref〉: or •FIELD NAME:
_USP_BULLET_RE = re.compile(
    r"^[•·]\s*([A-Z][A-Z\s/]+?)(?:\s*[〈<]\d+[〉>])?\s*:",
    re.MULTILINE,
)


def _extract_usp_text(pdf_path: str) -> tuple[str, list[str]]:
    import pdfplumber
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            pages.append(text)
    return "\f".join(pages), pages


def _split_usp_sections(full_text: str) -> dict[str, str]:
    """Split on ALL-CAPS standalone lines (real USP PDF heading format)."""
    matches = list(_USP_MAIN_SECTIONS.finditer(full_text))
    if not matches:
        return {"FULL_TEXT": full_text}

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip().upper()
        start   = m.end()
        end     = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body    = full_text[start:end].strip()
        sections[heading] = sections.get(heading, "") + ("\n" + body if heading in sections else body)
    return sections


def _extract_usp_bullet_field(text: str, field_name: str) -> Optional[str]:
    """
    Extract content of a bullet sub-field from USP section text.
    e.g. •LOSS ON DRYING 〈731〉: ... until next bullet or end
    """
    pattern = re.compile(
        r"[•·]\s*" + re.escape(field_name) + r"[^:]*:\s*(.*?)(?=[•·]|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(text)
    return _clean(m.group(1)) if m else None


def _parse_usp_pdf(pdf_path: str) -> dict:
    """
    Parse a USP PDF monograph.
    Note: Page 1 is typically image-rendered; fields from it will be None
    and should be filled by PubChem via spec_resolver (step 3.4).
    """
    warnings: list[str] = []

    try:
        full_text, pages = _extract_usp_text(pdf_path)
    except Exception as exc:
        return {"error": str(exc), "parse_warnings": [str(exc)]}

    if not full_text.strip():
        return {
            "error": "No extractable text.",
            "parse_warnings": ["pdfplumber returned empty text — fully scanned PDF."],
        }

    # Strip print header lines (added by uspnf.com when saving)
    # e.g. "11/3/2020 USP-NF Metformin Hydrochloride"
    full_text = re.sub(r"^\d+/\d+/\d+\s+USP-NF\s+.+$", "", full_text, flags=re.MULTILINE)
    full_text = re.sub(r"^Printed\s+(?:on|by):.+$", "", full_text, flags=re.MULTILINE)
    full_text = re.sub(r"^https?://\S+$", "", full_text, flags=re.MULTILINE)

    sections = _split_usp_sections(full_text)
    log.info("USP sections found: %s", list(sections.keys()))

    # ── Drug name ──────────────────────────────────────────────────────────────
    drug_name = Path(pdf_path).stem
    # Strip "USP-NF " prefix
    drug_name = re.sub(r"^USP-NF\s+", "", drug_name).strip()

    # ── Edition ────────────────────────────────────────────────────────────────
    edition = "USP 43-NF38"   # known from folder structure

    # ── Fields mostly on page 1 (image) — will be None, filled by PubChem ─────
    molecular_formula = None
    description       = None
    identification: list[dict] = []
    assay: dict[str, Any] = {"method": None, "limits": None, "units": "%w/w", "raw": None}

    # Try to get assay limits from page 1 text if partially extractable
    page1 = pages[0] if pages else ""
    if page1:
        lim = _extract_assay_limits(page1)
        if lim:
            assay["limits"] = lim
            assay["method"] = _infer_method(page1)
            assay["raw"]    = _clean(page1)[:400]
        # Also try to get assay from ASSAY section if detected
    raw_assay = sections.get("ASSAY", "")
    if raw_assay and not assay["limits"]:
        assay["limits"] = _extract_assay_limits(raw_assay)
        assay["method"] = _infer_method(raw_assay)
        assay["raw"]    = _clean(raw_assay)[:400]

    # ── SPECIFIC TESTS section — Loss on drying, water, etc. ──────────────────
    specific = sections.get("SPECIFIC TESTS", "")

    loss_on_drying = None
    lod_raw = _extract_usp_bullet_field(specific, "LOSS ON DRYING")
    if lod_raw:
        lm = re.search(r"NMT\s+(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%", lod_raw, re.IGNORECASE)
        tm = _LOD_TEMP_RE.search(lod_raw)
        limit_val = None
        if lm:
            limit_val = float(lm.group(1) or lm.group(2))
        loss_on_drying = {
            "limit_pct":     limit_val,
            "temperature_c": int(tm.group(1)) if tm else None,
            "method":        "Gravimetric (USP <731>)",
        }

    water_content = None
    water_raw = _extract_usp_bullet_field(specific, "WATER DETERMINATION") or \
                _extract_usp_bullet_field(specific, "WATER")
    if water_raw:
        lm = re.search(r"NMT\s+(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%", water_raw, re.IGNORECASE)
        limit_val = float(lm.group(1) or lm.group(2)) if lm else None
        water_content = {
            "limit_pct": limit_val,
            "method": "Karl Fischer titration" if re.search(r"karl|fischer", water_raw, re.I)
                      else "Gravimetric",
        }

    residue_on_ignition = None
    roi_raw = _extract_usp_bullet_field(specific, "RESIDUE ON IGNITION")
    if roi_raw:
        lm = re.search(r"NMT\s+(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%", roi_raw, re.IGNORECASE)
        limit_val = float(lm.group(1) or lm.group(2)) if lm else None
        residue_on_ignition = {"limit_pct": limit_val, "method": "USP <281>"}

    # ── ADDITIONAL REQUIREMENTS — Storage ─────────────────────────────────────
    additional = sections.get("ADDITIONAL REQUIREMENTS", "")
    storage = None
    stor_raw = _extract_usp_bullet_field(additional, "PACKAGING AND STORAGE")
    if stor_raw:
        storage = stor_raw[:300]

    # ── IMPURITIES section ─────────────────────────────────────────────────────
    imp_text = sections.get("IMPURITIES", "")
    related_substances: list[dict] = []
    impurities: list[dict] = []

    # Organic impurities bullet
    org_imp_raw = _extract_usp_bullet_field(imp_text, "ORGANIC IMPURITIES")
    if not org_imp_raw:
        org_imp_raw = imp_text  # use full impurities section

    if org_imp_raw:
        # Extract acceptance criteria lines
        crit_section = re.search(
            r"[Aa]cceptance\s+[Cc]riteria(.*?)(?=[•·]|\Z)", org_imp_raw, re.DOTALL)
        crit_text = _clean(crit_section.group(1)) if crit_section else _clean(org_imp_raw)

        # Split on semicolons or newlines for individual impurity limits
        entries = re.split(r";|\n", crit_text)
        for entry in entries:
            entry = _clean(entry)
            if len(entry) < 5:
                continue
            lm = re.search(r"NMT\s+(\d+(?:\.\d+)?)\s*%", entry, re.IGNORECASE)
            if lm or "%" in entry:
                limit_val = float(lm.group(1)) if lm else None
                related_substances.append({
                    "name":       entry[:120],
                    "limit":      limit_val,
                    "limit_unit": "%",
                    "rrt":        None,
                    "method":     "HPLC",
                })

    # Residue on ignition (store separately)
    roi_imp = _extract_usp_bullet_field(imp_text, "RESIDUE ON IGNITION")
    if roi_imp and not residue_on_ignition:
        lm = re.search(r"NMT\s+(\d+(?:\.\d+)?)\s*%", roi_imp, re.IGNORECASE)
        residue_on_ignition = {
            "limit_pct": float(lm.group(1)) if lm else None,
            "method": "USP <281>",
        }

    # ── Dissolution ────────────────────────────────────────────────────────────
    dissolution: dict = {"apparatus": None, "medium": None, "rpm": None,
                         "time_min": None, "limit_pct": None, "method": None, "raw": None}
    perf = sections.get("PERFORMANCE TESTS", "") or sections.get("DISSOLUTION", "")
    if perf:
        dissolution = _extract_dissolution_fields(perf)

    # ── Microbial ──────────────────────────────────────────────────────────────
    microbial_limits: dict = {"TAMC": None, "TYMC": None,
                               "pathogens": [], "method": None, "raw": None}
    micro_text = sections.get("MICROBIOLOGICAL TESTS", "")
    if micro_text:
        microbial_limits = _extract_microbial_fields(micro_text)

    # ── Uniformity ─────────────────────────────────────────────────────────────
    uniformity = None
    uni_raw = _extract_usp_bullet_field(perf or specific, "UNIFORMITY OF DOSAGE UNITS")
    if uni_raw:
        crit_m = re.search(r"AV\s*[≤<=]\s*(\d+(?:\.\d+)?)", uni_raw)
        uniformity = {
            "method": "USP <905>",
            "criterion": f"AV ≤ {crit_m.group(1)}" if crit_m else
                         "Meets requirements" if "meets" in uni_raw.lower() else uni_raw[:200],
        }

    # ── Warnings ───────────────────────────────────────────────────────────────
    warnings.append(
        "INFO: USP page 1 is image-rendered. DEFINITION/IDENTIFICATION/ASSAY "
        "limits will be filled by PubChem via spec_resolver (step 3.4)."
    )
    if not storage:
        warnings.append("MISSING: storage (•PACKAGING AND STORAGE not found).")
    if not loss_on_drying:
        warnings.append("MISSING: loss on drying.")

    return {
        "drug_name":           drug_name,
        "source":              "USP",
        "edition":             edition,
        "molecular_formula":   molecular_formula,
        "description":         description,
        "identification":      identification,
        "assay":               assay,
        "related_substances":  related_substances,
        "dissolution":         dissolution,
        "storage":             storage,
        "microbial_limits":    microbial_limits,
        "loss_on_drying":      loss_on_drying,
        "water_content":       water_content,
        "uniformity":          uniformity,
        "impurities":          impurities,
        "residue_on_ignition": residue_on_ignition,
        "raw_sections":        {k: v[:2000] for k, v in sections.items()},
        "parse_warnings":      warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def parse_monograph(file_path: str, source: str = "BP") -> dict:
    """
    Parse a BP HTML or USP PDF monograph.

    Parameters
    ----------
    file_path : str   Path to .html (BP) or .pdf (USP) file.
    source    : str   "BP" or "USP".

    Returns
    -------
    dict with all extracted fields + raw_sections + parse_warnings.
    """
    source = source.upper()
    if source not in ("BP", "USP"):
        raise ValueError(f"source must be 'BP' or 'USP', got '{source}'")
    if not Path(file_path).exists():
        return {"error": f"File not found: {file_path}", "parse_warnings": []}

    log.info("Parsing %s monograph: %s", source, file_path)
    return _parse_bp_html(file_path) if source == "BP" else _parse_usp_pdf(file_path)


def validate_result(result: dict) -> list[str]:
    """
    Return list of missing critical fields.
    Used by spec_resolver (step 3.4) to decide which fallback source to query.
    """
    issues: list[str] = []
    for field in ("description", "identification", "storage"):
        val = result.get(field)
        if val is None or val == [] or val == {}:
            issues.append(f"MISSING: {field}")
    assay = result.get("assay", {})
    if not (isinstance(assay, dict) and assay.get("limits")):
        issues.append("MISSING: assay limits (min/max %)")
    return issues


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Parse a BP HTML or USP PDF monograph → structured JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pharmacopoeia_parser.py metformin-hydrochloride.html --source BP --validate
  python pharmacopoeia_parser.py "USP-NF Metformin Hydrochloride.pdf" --source USP
  python pharmacopoeia_parser.py metformin-hydrochloride.html --source BP --sections-only
""",
    )
    parser.add_argument("file", help="Path to monograph file (.html for BP, .pdf for USP).")
    parser.add_argument("--source", choices=["BP", "USP"], required=True)
    parser.add_argument("--out", default=None, help="Output JSON path.")
    parser.add_argument("--validate", action="store_true", help="Print validation issues.")
    parser.add_argument("--sections-only", action="store_true",
                        help="Print section names and exit.")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"ERROR: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.sections_only:
        if args.source == "BP":
            from bs4 import BeautifulSoup
            with open(args.file, encoding="utf-8", errors="replace") as f:
                soup = BeautifulSoup(f.read(), "lxml")
            sections    = [_clean(h.get_text()) for h in soup.find_all("h2", class_="mainheading")]
            subsections = [_clean(h.get_text()) for h in soup.find_all("h3", class_="sub_general")]
            print(f"BP main sections ({len(sections)}):")
            for s in sections:
                print(f"  • {s}")
            print(f"\nBP sub-sections ({len(subsections)}):")
            for s in subsections:
                print(f"    – {s}")
        else:
            full_text, _ = _extract_usp_text(args.file)
            full_text = re.sub(r"^\d+/\d+/\d+\s+USP-NF\s+.+$", "", full_text, flags=re.MULTILINE)
            sections = _split_usp_sections(full_text)
            print(f"USP sections ({len(sections)}):")
            for name in sections:
                print(f"  • {name}")
            # Also show bullet sub-fields
            print("\nUSP bullet sub-fields:")
            all_text = " ".join(sections.values())
            for m in _USP_BULLET_RE.finditer(all_text):
                print(f"    – {m.group(1).strip()}")
        sys.exit(0)

    result = parse_monograph(args.file, source=args.source)

    if args.validate:
        issues = validate_result(result)
        print("\n=== VALIDATION ===")
        if issues:
            for issue in issues:
                print(f"  ⚠  {issue}")
        else:
            print("  ✓  All critical fields populated.")

    out_path = args.out or (Path(args.file).stem + f"_{args.source}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✓  Drug    : {result.get('drug_name', 'Unknown')}")
    print(f"   Source  : {result.get('source')}")
    print(f"   Edition : {result.get('edition')}")
    print(f"   Formula : {result.get('molecular_formula')}")
    print(f"   Sections: {len(result.get('raw_sections', {}))}")
    print(f"   Output  : {out_path}")
    if result.get("parse_warnings"):
        print(f"   Warnings ({len(result['parse_warnings'])}):")
        for w in result["parse_warnings"]:
            print(f"     • {w}")


if __name__ == "__main__":
    main()