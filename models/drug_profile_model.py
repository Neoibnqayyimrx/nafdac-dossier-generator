"""
models/drug_profile_model.py
============================
Pydantic v2 models that validate a drug_profile.yaml on load.
Any missing required field gives a clear, human-readable error
message pointing to exactly which field to fix.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Literal
from pydantic import BaseModel, field_validator, model_validator, Field
import yaml


# ── Sub-models ──────────────────────────────────────────────────────────────

class DrugInfo(BaseModel):
    name: str = Field(..., description="INN / generic drug name")
    brand_name: str = Field(..., description="Brand/proprietary name")
    strength: str = Field(..., description="Strength e.g. '850mg'")
    dosage_form: str = Field(..., description="e.g. 'Film-coated Tablets'")
    route_of_administration: str = Field(..., description="e.g. 'Oral'")
    therapeutic_class: str = Field(..., description="e.g. 'Antidiabetic – Biguanide'")
    atc_code: str = Field(..., description="WHO ATC code e.g. 'A10BA02'")
    pharmacopoeia_standard: Literal["BP", "USP", "BP/USP", "In-house"] = "BP"
    description: Optional[str] = None

    @field_validator("name", "brand_name", "strength", "dosage_form",
                     "route_of_administration", "therapeutic_class", "atc_code")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"drug.{info.field_name} is required and cannot be empty. "
                f"Please fill this in your drug_profile.yaml."
            )
        return v.strip()


class ManufacturerInfo(BaseModel):
    name: str = Field(..., description="Manufacturer legal name")
    address: str = Field(..., description="Full manufacturing site address")
    country: str = "Nigeria"
    nafdac_number: Optional[str] = None
    gmp_certificate: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("name", "address")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"manufacturer.{info.field_name} is required. "
                f"Please fill this in your drug_profile.yaml."
            )
        return v.strip()


class ApplicantInfo(BaseModel):
    name: str = Field(..., description="Applicant company name")
    address: str = Field(..., description="Applicant address")
    country: str = "Nigeria"
    contact_person: str = Field(..., description="Primary contact name")
    email: str = Field(..., description="Contact email address")
    phone: str = Field(..., description="Contact phone number")

    @field_validator("name", "address", "contact_person", "email", "phone")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"applicant.{info.field_name} is required. "
                f"Please fill this in your drug_profile.yaml."
            )
        return v.strip()


class RegistrationInfo(BaseModel):
    application_type: Literal["New Product", "Renewal", "Variation"] = "New Product"
    product_category: Literal["Finished Product", "API", "Medical Device"] = "Finished Product"
    target_market: str = "Nigeria"
    nafdac_registration_number: Optional[str] = None
    previous_submission_date: Optional[str] = None

    @model_validator(mode="after")
    def renewal_requires_reg_number(self) -> "RegistrationInfo":
        if self.application_type in ("Renewal", "Variation"):
            if not self.nafdac_registration_number:
                raise ValueError(
                    "registration.nafdac_registration_number is required "
                    "when application_type is 'Renewal' or 'Variation'."
                )
        return self


class StorageInfo(BaseModel):
    shelf_life: str = Field(..., description="e.g. '24 months'")
    storage_conditions: str = Field(..., description="e.g. 'Store below 30°C'")
    pack_size: str = Field(..., description="e.g. 'Blister pack of 10 x 10 strips'")
    container_type: str = Field(..., description="e.g. 'PVC/Aluminium blister'")

    @field_validator("shelf_life", "storage_conditions", "pack_size", "container_type")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"storage_and_stability.{info.field_name} is required. "
                f"Please fill this in your drug_profile.yaml."
            )
        return v.strip()


class Specifications(BaseModel):
    # All optional here — Phase 3 will auto-populate from BP/USP/PubChem.
    # User can pre-fill any field to override auto-population.
    description: Optional[str] = None
    identification: Optional[str] = None
    assay_limit: Optional[str] = None
    dissolution: Optional[str] = None
    related_substances: Optional[str] = None
    water_content: Optional[str] = None
    microbial_limit: Optional[str] = None
    particle_size: Optional[str] = None
    hardness: Optional[str] = None
    disintegration: Optional[str] = None


class SupportingDocuments(BaseModel):
    bioequivalence_study: Optional[str] = None
    stability_data: Optional[str] = None
    certificate_of_analysis: Optional[str] = None
    gmp_certificate: Optional[str] = None
    drug_master_file: Optional[str] = None
    site_master_file: Optional[str] = None

    @model_validator(mode="after")
    def validate_file_paths(self) -> "SupportingDocuments":
        """Warn if a provided file path doesn't exist on disk."""
        fields = {
            "bioequivalence_study": self.bioequivalence_study,
            "stability_data": self.stability_data,
            "certificate_of_analysis": self.certificate_of_analysis,
            "gmp_certificate": self.gmp_certificate,
            "drug_master_file": self.drug_master_file,
            "site_master_file": self.site_master_file,
        }
        missing = []
        for field_name, path_str in fields.items():
            if path_str and path_str.strip():
                p = Path(path_str.strip())
                if not p.exists():
                    missing.append(f"supporting_documents.{field_name}: '{path_str}' does not exist")
        if missing:
            # Warn but don't block — file may not be needed for all sections
            import warnings
            for m in missing:
                warnings.warn(f"[WARNING] {m}", UserWarning, stacklevel=2)
        return self


class References(BaseModel):
    who_prequalified: bool = False
    who_pq_number: Optional[str] = None
    pubchem_cid: Optional[str] = None
    bp_monograph_ref: Optional[str] = None
    usp_monograph_ref: Optional[str] = None

    @model_validator(mode="after")
    def pq_number_required_if_prequalified(self) -> "References":
        if self.who_prequalified and not self.who_pq_number:
            raise ValueError(
                "references.who_pq_number is required when who_prequalified is true."
            )
        return self


# ── Root model ───────────────────────────────────────────────────────────────

class DrugProfile(BaseModel):
    """
    Root model representing a complete drug_profile.yaml.
    Load with DrugProfile.from_yaml(path).
    """
    drug: DrugInfo
    manufacturer: ManufacturerInfo
    applicant: ApplicantInfo
    registration: RegistrationInfo
    storage_and_stability: StorageInfo
    specifications: Specifications = Field(default_factory=Specifications)
    supporting_documents: SupportingDocuments = Field(default_factory=SupportingDocuments)
    references: References = Field(default_factory=References)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DrugProfile":
        """
        Load and validate a drug_profile.yaml file.
        Raises ValueError with clear messages if validation fails.
        """
        yaml_path = Path(path)
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"Drug profile not found: {yaml_path}\n"
                f"Run: nafdac new-drug --name 'YourDrug' to create one."
            )
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            raise ValueError(f"Drug profile YAML is empty: {yaml_path}")

        return cls.model_validate(raw)

    def display_name(self) -> str:
        """Returns a clean human-readable identifier for this drug."""
        return f"{self.drug.brand_name} ({self.drug.name} {self.drug.strength} {self.drug.dosage_form})"

    def submission_folder_name(self) -> str:
        """Returns a filesystem-safe folder name for the submission."""
        safe = f"{self.drug.brand_name}_{self.drug.strength}".replace(" ", "_").replace("/", "-")
        return safe


# ── Standalone validation helper ─────────────────────────────────────────────

def validate_profile(path: str | Path) -> tuple[bool, Optional[DrugProfile], list[str]]:
    """
    Validate a drug_profile.yaml and return (is_valid, profile, error_messages).
    Use this in the CLI for clean error reporting.
    """
    errors = []
    try:
        profile = DrugProfile.from_yaml(path)
        return True, profile, []
    except FileNotFoundError as e:
        return False, None, [str(e)]
    except Exception as e:
        # Parse pydantic validation errors into human-readable messages
        raw = str(e)
        lines = raw.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("For further"):
                errors.append(line)
        return False, None, errors


if __name__ == "__main__":
    # Quick test: validate the template config
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "config/drug_profile.yaml"
    is_valid, profile, errors = validate_profile(path)
    if is_valid:
        print(f"✅ Profile valid: {profile.display_name()}")
    else:
        print("❌ Validation failed:")
        for e in errors:
            print(f"   → {e}")
