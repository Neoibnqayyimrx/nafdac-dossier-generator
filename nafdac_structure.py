"""
nafdac_structure.py
===================
Builds the NAFDAC CTD (Common Technical Document) folder structure for a
finished product registration submission.

NAFDAC follows the ICH CTD format with five modules:
  Module 1  Administrative Information (NAFDAC-specific)
  Module 2  CTD Summaries
  Module 3  Quality
  Module 4  Nonclinical Study Reports
  Module 5  Clinical Study Reports

Folder structure created
------------------------
submissions/
└── {drug_slug}/
    ├── submission_manifest.json   ← index of all generated files
    ├── Module1/
    │   ├── 1.1_Cover_Letter/
    │   ├── 1.2_Application_Form/
    │   ├── 1.3_Product_Information/
    │   │   ├── 1.3.1_SmPC/
    │   │   ├── 1.3.2_PIL/
    │   │   └── 1.3.3_Labelling/
    │   ├── 1.4_Expert_Information/
    │   └── 1.5_Administrative/
    ├── Module2/
    │   ├── 2.1_TOC/
    │   ├── 2.2_Introduction/
    │   ├── 2.3_QOS/               ← Quality Overall Summary
    │   ├── 2.4_Nonclinical_Overview/
    │   ├── 2.5_Clinical_Overview/
    │   ├── 2.6_Nonclinical_Summary/
    │   └── 2.7_Clinical_Summary/
    ├── Module3/
    │   ├── 3.1_TOC/
    │   └── 3.2_Body_of_Data/
    │       ├── 3.2.S_Drug_Substance/
    │       │   ├── 3.2.S.1_General_Information/
    │       │   ├── 3.2.S.2_Manufacture/
    │       │   ├── 3.2.S.3_Characterisation/
    │       │   ├── 3.2.S.4_Control/
    │       │   ├── 3.2.S.5_Reference_Standards/
    │       │   ├── 3.2.S.6_Container_Closure/
    │       │   └── 3.2.S.7_Stability/
    │       └── 3.2.P_Drug_Product/
    │           ├── 3.2.P.1_Description/
    │           ├── 3.2.P.2_Pharmaceutical_Development/
    │           ├── 3.2.P.3_Manufacture/
    │           ├── 3.2.P.4_Control_of_Excipients/
    │           ├── 3.2.P.5_Control_of_Drug_Product/
    │           ├── 3.2.P.6_Reference_Standards/
    │           ├── 3.2.P.7_Container_Closure/
    │           └── 3.2.P.8_Stability/
    ├── Module4/
    │   ├── 4.2_Study_Reports/
    │   └── 4.3_Literature_References/
    └── Module5/
        ├── 5.2_Tabular_Listing/
        ├── 5.3_Clinical_Study_Reports/
        └── 5.4_Literature_References/

Usage
-----
  from nafdac_structure import build_submission_folder, SubmissionConfig

  config = SubmissionConfig(
      drug_name        = "Amlodipine Besylate",
      strength         = "10mg",
      dosage_form      = "Tablets",
      applicant        = "ABC Pharmaceuticals Ltd",
      manufacturer     = "XYZ Manufacturing Ltd",
      country_of_mfr   = "Nigeria",
      submission_type  = "new_product",
  )
  paths = build_submission_folder(config)

CLI (via cli.py)
----------------
  python cli.py new-submission --drug "Amlodipine Besylate" --strength 10mg --form Tablets
  python cli.py new-submission --drug "Metformin Hydrochloride" --strength 500mg --form Tablets --applicant "ABC Pharma"
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Root submissions directory ─────────────────────────────────────────────────
SUBMISSIONS_ROOT = Path("submissions")


# ═══════════════════════════════════════════════════════════════════════════════
# SUBMISSION CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SubmissionConfig:
    """
    All metadata needed to build a NAFDAC CTD submission folder.
    """
    # Required
    drug_name:        str
    strength:         str          # e.g. "10mg", "500mg"
    dosage_form:      str          # e.g. "Tablets", "Capsules", "Oral Suspension"

    # Company information
    applicant:        str  = "APPLICANT NAME"
    manufacturer:     str  = "MANUFACTURER NAME"
    country_of_mfr:   str  = "Nigeria"
    address_applicant: str = ""
    address_mfr:       str = ""

    # Regulatory
    submission_type:  str  = "new_product"   # new_product | variation | renewal
    nafdac_number:    str  = ""              # filled if renewal/variation
    inn:              str  = ""              # International Non-proprietary Name
    brand_name:       str  = ""

    # Dates
    submission_date:  str  = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    # Drug substance details (populated from spec_resolver)
    drug_substance:   str  = ""   # INN of active substance
    molecular_formula: str = ""
    molecular_weight:  str = ""

    # Output location
    output_root:      str  = ""   # defaults to submissions/<drug_slug>/

    def __post_init__(self):
        if not self.drug_substance:
            self.drug_substance = self.drug_name
        if not self.inn:
            self.inn = self.drug_name

    @property
    def slug(self) -> str:
        """URL-safe folder name for the submission."""
        name = f"{self.drug_name}_{self.strength}_{self.dosage_form}"
        return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")

    @property
    def full_product_name(self) -> str:
        brand = f" ({self.brand_name})" if self.brand_name else ""
        return f"{self.drug_name} {self.strength} {self.dosage_form}{brand}"

    @property
    def submission_root(self) -> Path:
        if self.output_root:
            return Path(self.output_root)
        return SUBMISSIONS_ROOT / self.slug


# ═══════════════════════════════════════════════════════════════════════════════
# CTD FOLDER TREE DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════

# Each entry: (path_relative_to_submission_root, description, docx_to_generate)
_CTD_FOLDERS = [
    # Module 1 — Administrative
    ("Module1/1.1_Cover_Letter",                   "Cover letter to NAFDAC",                      "1.1_cover_letter.docx"),
    ("Module1/1.2_Application_Form",               "NAFDAC application form",                     "1.2_application_form.docx"),
    ("Module1/1.3_Product_Information/1.3.1_SmPC", "Summary of Product Characteristics",          "smpc.docx"),
    ("Module1/1.3_Product_Information/1.3.2_PIL",  "Patient Information Leaflet",                 "pil.docx"),
    ("Module1/1.3_Product_Information/1.3.3_Labelling", "Labelling mock-ups",                     None),
    ("Module1/1.4_Expert_Information",             "Expert reports (QP declaration etc.)",        None),
    ("Module1/1.5_Administrative",                 "Administrative documents",                    None),
 
    # Module 2 — CTD Summaries
    ("Module2/2.1_TOC",                            "CTD Table of Contents",                       "2.1_ctd_toc.docx"),
    ("Module2/2.2_Introduction",                   "Introduction to the dossier",                 "2.2_introduction.docx"),
    ("Module2/2.3_QOS",                            "Quality Overall Summary",                     "2.3_quality_overall_summary.docx"),
    ("Module2/2.4_Nonclinical_Overview",           "Nonclinical overview",                        None),
    ("Module2/2.5_Clinical_Overview",              "Clinical overview",                           None),
    ("Module2/2.6_Nonclinical_Summary",            "Nonclinical written and tabulated summary",   None),
    ("Module2/2.7_Clinical_Summary",               "Clinical summary",                            None),
 
    # Module 3 — Quality
    ("Module3/3.1_TOC",                            "Module 3 Table of Contents",                  "3.1_module3_toc.docx"),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.1_General_Information",
                                                   "Drug substance: name, structure, properties", "3.2.S.1_general_information.docx"),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.2_Manufacture",
                                                   "Drug substance manufacture",                  "3.2.S.2_manufacture.docx"),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.3_Characterisation",
                                                   "Elucidation of structure and other characteristics", "3.2.S.3_characterisation.docx"),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.4_Control",
                                                   "Control of drug substance (specifications)",  "3.2.S.4.1_specifications.docx"),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.5_Reference_Standards",
                                                   "Reference standards and materials",           None),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.6_Container_Closure",
                                                   "Container closure system",                    None),
    ("Module3/3.2_Body_of_Data/3.2.S_Drug_Substance/3.2.S.7_Stability",
                                                   "Stability data for drug substance",           None),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.1_Description",
                                                   "Description and composition of the drug product", "3.2.P.1_description_composition.docx"),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.2_Pharmaceutical_Development",
                                                   "Pharmaceutical development",                  None),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.3_Manufacture",
                                                   "Manufacture of the drug product",             None),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.4_Control_of_Excipients",
                                                   "Control of excipients",                       None),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.5_Control_of_Drug_Product",
                                                   "Control of drug product (specifications)",    "3.2.P.5.1_specifications.docx"),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.6_Reference_Standards",
                                                   "Reference standards",                         None),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.7_Container_Closure",
                                                   "Container closure system",                    None),
    ("Module3/3.2_Body_of_Data/3.2.P_Drug_Product/3.2.P.8_Stability",
                                                   "Stability data for drug product",             None),
    ("Module3/3.3_Literature_References",          "Literature references",                       None),
 
    # Module 4 — Nonclinical
    ("Module4/4.2_Study_Reports",                  "Nonclinical study reports",                   None),
    ("Module4/4.3_Literature_References",          "Nonclinical literature references",           None),
 
    # Module 5 — Clinical
    ("Module5/5.2_Tabular_Listing",                "Tabular listing of all clinical studies",     None),
    ("Module5/5.3_Clinical_Study_Reports",         "Clinical study reports",                      None),
    ("Module5/5.4_Literature_References",          "Clinical literature references",              None),
]

# ═══════════════════════════════════════════════════════════════════════════════
# FOLDER BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_submission_folder(
    config: SubmissionConfig,
    overwrite: bool = False,
) -> dict:
    """
    Create the full NAFDAC CTD folder structure for a submission.

    Parameters
    ----------
    config    : SubmissionConfig   All submission metadata.
    overwrite : bool               If True, recreate even if folder exists.

    Returns
    -------
    dict with:
      "root"     : str  Path to the submission root folder
      "folders"  : list[str]  All created folder paths
      "manifest" : dict  Written to submission_manifest.json
    """
    root = config.submission_root
    if root.exists() and not overwrite:
        log.info("Submission folder already exists: %s", root)
    root.mkdir(parents=True, exist_ok=True)

    created_folders: list[str] = []
    docx_needed: list[dict]    = []

    for rel_path, description, docx_filename in _CTD_FOLDERS:
        folder = root / rel_path
        folder.mkdir(parents=True, exist_ok=True)
        created_folders.append(str(folder))
        log.debug("Created: %s", folder)

        if docx_filename:
            docx_needed.append({
                "folder":      str(folder),
                "filename":    docx_filename,
                "description": description,
                "path":        str(folder / docx_filename),
                "status":      "pending",
            })

    # ── Write submission manifest ──────────────────────────────────────────────
    manifest = {
        "submission_date":   config.submission_date,
        "drug_name":         config.drug_name,
        "strength":          config.strength,
        "dosage_form":       config.dosage_form,
        "full_product_name": config.full_product_name,
        "applicant":         config.applicant,
        "manufacturer":      config.manufacturer,
        "country_of_mfr":    config.country_of_mfr,
        "submission_type":   config.submission_type,
        "nafdac_number":     config.nafdac_number,
        "inn":               config.inn,
        "brand_name":        config.brand_name,
        "slug":              config.slug,
        "root":              str(root),
        "folders_created":   len(created_folders),
        "docx_pending":      len(docx_needed),
        "documents":         docx_needed,
        "config":            asdict(config),
    }

    manifest_path = root / "submission_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log.info(
        "Submission folder built: %s (%d folders, %d DOCX pending)",
        root, len(created_folders), len(docx_needed),
    )
    return {
        "root":     str(root),
        "folders":  created_folders,
        "manifest": manifest,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def load_manifest(submission_root: str) -> dict:
    """Load the submission manifest from an existing submission folder."""
    path = Path(submission_root) / "submission_manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"No manifest found in {submission_root}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_submissions() -> list[dict]:
    """List all submissions in the submissions root directory."""
    if not SUBMISSIONS_ROOT.exists():
        return []
    results = []
    for folder in sorted(SUBMISSIONS_ROOT.iterdir()):
        manifest_path = folder / "submission_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                results.append({
                    "slug":             manifest.get("slug", folder.name),
                    "full_product_name": manifest.get("full_product_name", ""),
                    "applicant":        manifest.get("applicant", ""),
                    "submission_date":  manifest.get("submission_date", ""),
                    "docx_pending":     manifest.get("docx_pending", 0),
                    "root":             str(folder),
                })
            except (json.JSONDecodeError, OSError):
                pass
    return results


def get_docx_path(submission_root: str, docx_filename: str) -> Optional[Path]:
    """Find the path where a specific DOCX file should be placed."""
    manifest = load_manifest(submission_root)
    for doc in manifest.get("documents", []):
        if doc["filename"] == docx_filename:
            return Path(doc["path"])
    return None


def update_document_status(
    submission_root: str,
    docx_filename: str,
    status: str,
) -> None:
    """Update the status of a document in the manifest (pending/generated/reviewed)."""
    manifest_path = Path(submission_root) / "submission_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for doc in manifest.get("documents", []):
        if doc["filename"] == docx_filename:
            doc["status"] = status
            break
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def config_from_manifest(submission_root: str) -> SubmissionConfig:
    """Reconstruct a SubmissionConfig from an existing manifest."""
    manifest = load_manifest(submission_root)
    cfg_data  = manifest.get("config", {})
    return SubmissionConfig(**{
        k: v for k, v in cfg_data.items()
        if k in SubmissionConfig.__dataclass_fields__
    })