"""
config_manager.py
=================
Handles creation of blank drug_profile.yaml files for new drugs.
Called by the CLI 'new-drug' command.
"""

from pathlib import Path
import yaml


BLANK_PROFILE_TEMPLATE = {
    "drug": {
        "name": "",
        "brand_name": "",
        "strength": "",
        "dosage_form": "",
        "route_of_administration": "",
        "therapeutic_class": "",
        "atc_code": "",
        "pharmacopoeia_standard": "BP",
        "description": "",
    },
    "manufacturer": {
        "name": "",
        "address": "",
        "country": "Nigeria",
        "nafdac_number": "",
        "gmp_certificate": "",
        "contact_person": "",
        "email": "",
        "phone": "",
    },
    "applicant": {
        "name": "",
        "address": "",
        "country": "Nigeria",
        "contact_person": "",
        "email": "",
        "phone": "",
    },
    "registration": {
        "application_type": "New Product",
        "product_category": "Finished Product",
        "target_market": "Nigeria",
        "nafdac_registration_number": "",
        "previous_submission_date": "",
    },
    "storage_and_stability": {
        "shelf_life": "",
        "storage_conditions": "",
        "pack_size": "",
        "container_type": "",
    },
    "specifications": {
        "description": "",
        "identification": "",
        "assay_limit": "",
        "dissolution": "",
        "related_substances": "",
        "water_content": "",
        "microbial_limit": "",
        "particle_size": "",
        "hardness": "",
        "disintegration": "",
    },
    "supporting_documents": {
        "bioequivalence_study": "",
        "stability_data": "",
        "certificate_of_analysis": "",
        "gmp_certificate": "",
        "drug_master_file": "",
        "site_master_file": "",
    },
    "references": {
        "who_prequalified": False,
        "who_pq_number": "",
        "pubchem_cid": "",
        "bp_monograph_ref": "",
        "usp_monograph_ref": "",
    },
}


def create_blank_drug_profile(name: str, output_path: Path) -> None:
    """
    Create a blank drug_profile.yaml pre-filled with the drug name.
    Writes to output_path, creating parent directories if needed.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profile = BLANK_PROFILE_TEMPLATE.copy()
    profile["drug"] = profile["drug"].copy()
    profile["drug"]["name"] = name

    # Add helpful header comment by writing raw then prepending
    yaml_content = yaml.dump(profile, default_flow_style=False, allow_unicode=True, sort_keys=False)

    header = (
        f"# NAFDAC Dossier Generator — Drug Profile\n"
        f"# Drug: {name}\n"
        f"# Fill in all required fields before running: nafdac generate\n"
        f"# Required fields: drug.name/brand_name/strength/dosage_form/route/class/atc_code,\n"
        f"#                   manufacturer.name/address, applicant.* (all), storage_and_stability.*\n"
        f"# ─────────────────────────────────────────────────────────────────────\n\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + yaml_content)
