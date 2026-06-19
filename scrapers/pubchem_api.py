"""
pubchem_api.py
==============
Queries the PubChem REST API for chemical property data and maps the results
to NAFDAC dossier fields. Results are cached locally so each drug is only
queried once.

Fields fetched
--------------
  cid               : int        PubChem Compound ID
  molecular_formula : str        e.g. "C4H12ClN5"
  molecular_weight  : float      g/mol
  iupac_name        : str        IUPAC systematic name
  smiles            : str        SMILES string
  inchikey          : str        standard InChIKey
  logp              : float      XLogP3 (None if not available)
  melting_point     : str | None extracted from experimental text
  solubility        : str | None from experimental data
  pka               : str | None dissociation constant
  synonyms          : list[str]  first 10 synonyms

Cache layout
------------
  pharmacopoeia_db/pubchem_cache/
    metformin_hydrochloride.json
    paracetamol.json
    ...

API endpoints used
------------------
  PUG REST:
    /compound/name/{name}/cids/JSON
    /compound/cid/{cid}/property/{props}/JSON
    /compound/cid/{cid}/synonyms/JSON

  PUG View (experimental data):
    /pug_view/data/compound/{cid}/JSON?heading=Experimental+Properties

Usage
-----
  from pubchem_api import query_pubchem, map_to_dossier_fields

  data   = query_pubchem("metformin hydrochloride")
  fields = map_to_dossier_fields(data)

CLI
---
  python cli.py pubchem-lookup metformin
  python cli.py pubchem-enrich-db --max-drugs 10
  python cli.py pubchem-stats
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

log = logging.getLogger(__name__)

# ── Cache location ─────────────────────────────────────────────────────────────
CACHE_DIR = Path("pharmacopoeia_db") / "pubchem_cache"

# ── PubChem API base URLs ──────────────────────────────────────────────────────
_PUG_BASE  = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_VIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"

# ── Rate limiting: PubChem allows ~5 requests/sec for anonymous users ──────────
_REQUEST_INTERVAL = 0.22
_last_request_time: float = 0.0

# ── HTTP session ───────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": "nafdac-dossier-gen/1.0 (research tool)"
})


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _get(url: str, params: Optional[dict] = None, timeout: int = 15) -> Optional[dict]:
    _rate_limit()
    for attempt in range(2):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            if attempt == 0:
                log.warning("Connection error, retrying in 2s...")
                time.sleep(2)
            else:
                log.error("Connection failed for %s", url)
                return None
        except requests.exceptions.Timeout:
            log.warning("Timeout for %s", url)
            return None
        except requests.exceptions.RequestException as exc:
            log.warning("Request error for %s: %s", url, exc)
            return None
        except json.JSONDecodeError:
            log.warning("Invalid JSON from %s", url)
            return None
    return None


def _normalise_cache_key(drug_name: str) -> str:
    key = drug_name.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    return key.strip("_")


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _cache_path(drug_name: str) -> Path:
    return CACHE_DIR / f"{_normalise_cache_key(drug_name)}.json"


def _load_cache(drug_name: str) -> Optional[dict]:
    path = _cache_path(drug_name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _save_cache(drug_name: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(drug_name).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def clear_cache(drug_name: Optional[str] = None) -> int:
    if drug_name:
        path = _cache_path(drug_name)
        if path.exists():
            path.unlink()
            return 1
        return 0
    if not CACHE_DIR.exists():
        return 0
    files = list(CACHE_DIR.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBCHEM QUERY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Salt suffixes to strip when full-name lookup fails
_SALT_PATTERNS = [
    r"\s+hydrochloride$", r"\s+hcl$", r"\s+sodium$", r"\s+potassium$",
    r"\s+sulfate$", r"\s+sulphate$", r"\s+phosphate$", r"\s+citrate$",
    r"\s+tartrate$", r"\s+maleate$", r"\s+fumarate$", r"\s+acetate$",
    r"\s+mesylate$", r"\s+mesilate$", r"\s+besylate$", r"\s+tosylate$",
    r"\s+monohydrate$", r"\s+dihydrate$", r"\s+trihydrate$",
    r"\s+hemihydrate$", r"\s+anhydrous$", r"\s+hydrate$",
]


def get_cid(drug_name: str) -> Optional[int]:
    """Resolve drug name → PubChem CID. Falls back to stripped salt name."""
    url  = f"{_PUG_BASE}/compound/name/{requests.utils.quote(drug_name)}/cids/JSON"
    data = _get(url)
    if data:
        cids = data.get("IdentifierList", {}).get("CID", [])
        if cids:
            return int(cids[0])

    # Fallback: strip salt suffix
    base = drug_name.lower()
    for pattern in _SALT_PATTERNS:
        shortened = re.sub(pattern, "", base, flags=re.IGNORECASE).strip()
        if shortened != base:
            url2  = f"{_PUG_BASE}/compound/name/{requests.utils.quote(shortened)}/cids/JSON"
            data2 = _get(url2)
            if data2:
                cids2 = data2.get("IdentifierList", {}).get("CID", [])
                if cids2:
                    log.info("CID found via fallback '%s': %d", shortened, cids2[0])
                    return int(cids2[0])
    log.warning("No CID found for '%s'", drug_name)
    return None


def get_properties(cid: int) -> dict:
    """
    Fetch core physicochemical properties from PUG REST.

    PubChem returns different SMILES property names depending on the compound:
      - Most compounds: CanonicalSMILES, IsomericSMILES
      - Some salts/mixtures: SMILES, ConnectivitySMILES
    We request all variants and take the best available.
    """
    # Request all possible SMILES variants + other properties
    props = [
        "MolecularFormula", "MolecularWeight", "IUPACName",
        "CanonicalSMILES", "IsomericSMILES", "SMILES",
        "InChIKey", "XLogP",
    ]
    url  = f"{_PUG_BASE}/compound/cid/{cid}/property/{','.join(props)}/JSON"
    data = _get(url)

    result: dict[str, Any] = {
        "molecular_formula": None,
        "molecular_weight":  None,
        "iupac_name":        None,
        "smiles":            None,
        "inchikey":          None,
        "logp":              None,
    }

    if not data:
        return result

    p_list = data.get("PropertyTable", {}).get("Properties", [])
    if not p_list:
        return result

    p = p_list[0]
    result["molecular_formula"] = p.get("MolecularFormula")
    result["molecular_weight"]  = p.get("MolecularWeight")
    result["iupac_name"]        = p.get("IUPACName")
    result["inchikey"]          = p.get("InChIKey")
    result["logp"]              = p.get("XLogP")

    # SMILES: prefer IsomericSMILES > CanonicalSMILES > SMILES
    result["smiles"] = (
        p.get("IsomericSMILES") or
        p.get("CanonicalSMILES") or
        p.get("SMILES")
    )

    return result


def get_synonyms(cid: int, max_synonyms: int = 10) -> list[str]:
    url  = f"{_PUG_BASE}/compound/cid/{cid}/synonyms/JSON"
    data = _get(url)
    if not data:
        return []
    info_list = data.get("InformationList", {}).get("Information", [])
    if not info_list:
        return []
    return info_list[0].get("Synonym", [])[:max_synonyms]


def _walk_pug_view(node: Any, target_heading: str, results: list) -> None:
    """
    Recursively walk PUG View JSON tree, collecting string values
    under any node whose TOCHeading matches target_heading.
    """
    if isinstance(node, dict):
        if node.get("TOCHeading") == target_heading:
            for info in node.get("Information", []):
                val = info.get("Value", {})
                for swm in val.get("StringWithMarkup", []):
                    s = swm.get("String", "").strip()
                    if s:
                        results.append(s)
                # Number + Unit fields
                nums = val.get("Number", [])
                unit = val.get("Unit", "")
                for n in nums:
                    results.append(f"{n} {unit}".strip())
            return  # don't descend further once found
        for v in node.values():
            _walk_pug_view(v, target_heading, results)
    elif isinstance(node, list):
        for item in node:
            _walk_pug_view(item, target_heading, results)


def _extract_mp_from_text(text: str) -> Optional[str]:
    """
    Extract melting point from free text like:
    "Prisms from water, MP 232 °C; crystals from propanol, MP 218-220 °C."
    "MW: 165.63. MP: 228-232°C."
    "Melting point: 225 °C"
    """
    patterns = [
        r"[Mm][Pp]\.?\s*[=:]?\s*(\d{2,3}(?:[–\-]\d{2,3})?)\s*°?\s*C",
        r"[Mm]elting\s+[Pp]oint\s*[=:]?\s*(\d{2,3}(?:[–\-]\d{2,3})?)\s*°?\s*C",
        r"(\d{2,3}(?:[–\-]\d{2,3})?)\s*°C",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1) + " °C"
    return None


def get_experimental_data(cid: int) -> dict:
    """
    Fetch experimental property data from PUG View.

    PubChem structure for metformin HCl and similar drugs:
      Chemical and Physical Properties
        Experimental Properties
          Stability/Shelf Life
          Decomposition
          Dissociation Constants   ← pKa here
          Other Experimental Properties  ← MP buried here as free text
          Solubility               ← may or may not exist

    Strategy:
      - Walk all headings collecting Solubility, Melting Point strings
      - Also parse MP from "Other Experimental Properties" free text
      - Parse pKa from "Dissociation Constants"
    """
    result: dict[str, Any] = {
        "melting_point": None,
        "solubility":    None,
        "pka":           None,
    }

    url    = f"{_VIEW_BASE}/data/compound/{cid}/JSON"
    params = {"heading": "Experimental Properties"}
    data   = _get(url, params=params)
    if not data:
        return result

    # ── Solubility ─────────────────────────────────────────────────────────────
    sol_vals: list[str] = []
    _walk_pug_view(data, "Solubility", sol_vals)
    if sol_vals:
        result["solubility"] = _clean_exp(sol_vals[0])

    # ── Melting point (dedicated heading) ─────────────────────────────────────
    mp_vals: list[str] = []
    _walk_pug_view(data, "Melting Point", mp_vals)
    if mp_vals:
        result["melting_point"] = _clean_exp(mp_vals[0])

    # ── Melting point fallback: parse from "Other Experimental Properties" ─────
    if not result["melting_point"]:
        other_vals: list[str] = []
        _walk_pug_view(data, "Other Experimental Properties", other_vals)
        for text in other_vals:
            mp = _extract_mp_from_text(text)
            if mp:
                result["melting_point"] = mp
                break

    # ── pKa ───────────────────────────────────────────────────────────────────
    pka_vals: list[str] = []
    _walk_pug_view(data, "Dissociation Constants", pka_vals)
    if pka_vals:
        result["pka"] = _clean_exp(pka_vals[0])

    return result


def _clean_exp(text: str) -> str:
    """Clean experimental property string."""
    text = re.sub(r"<[^>]+>", "", text)       # strip HTML
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER QUERY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def query_pubchem(
    drug_name: str,
    use_cache: bool = True,
    fetch_experimental: bool = True,
) -> dict:
    """
    Query PubChem for all available data on a drug.

    Parameters
    ----------
    drug_name          : str   Drug name (INN, salt form, or common name).
    use_cache          : bool  Return cached result if available (default True).
    fetch_experimental : bool  Also fetch melting point/solubility (default True).

    Returns
    -------
    dict with all extracted fields + query_status + cached flag.
    """
    if use_cache:
        cached = _load_cache(drug_name)
        if cached:
            cached["cached"] = True
            return cached

    log.info("Querying PubChem for: %s", drug_name)

    result: dict[str, Any] = {
        "drug_name":         drug_name,
        "cid":               None,
        "molecular_formula": None,
        "molecular_weight":  None,
        "iupac_name":        None,
        "smiles":            None,
        "inchikey":          None,
        "logp":              None,
        "melting_point":     None,
        "solubility":        None,
        "pka":               None,
        "synonyms":          [],
        "pubchem_url":       None,
        "query_status":      "not_found",
        "cached":            False,
    }

    # Step 1: CID
    cid = get_cid(drug_name)
    if not cid:
        _save_cache(drug_name, result)
        return result

    result["cid"]          = cid
    result["pubchem_url"]  = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
    result["query_status"] = "found"

    # Step 2: Core properties
    result.update(get_properties(cid))

    # Step 3: Synonyms
    result["synonyms"] = get_synonyms(cid)

    # Step 4: Experimental data
    if fetch_experimental:
        exp = get_experimental_data(cid)
        result["melting_point"] = exp["melting_point"]
        result["solubility"]    = exp["solubility"]
        result["pka"]           = exp["pka"]

    _save_cache(drug_name, result)
    log.info(
        "PubChem OK: %s → CID %d | MW %s | MP %s",
        drug_name, cid,
        result["molecular_weight"],
        result["melting_point"] or "—",
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# DOSSIER FIELD MAPPING
# ═══════════════════════════════════════════════════════════════════════════════

def map_to_dossier_fields(pubchem_data: dict) -> dict:
    """
    Map PubChem data to NAFDAC CTD dossier field names.

    CTD Module 3 mapping:
      3.2.S.1.1  Name        → drug_name, iupac_name, synonyms
      3.2.S.1.2  Structure   → smiles, inchikey
      3.2.S.1.3  Properties  → molecular_formula, molecular_weight, logp
      3.2.S.3.1  Characterisation → melting_point, pka
      SmPC 6.1   Excipients  → solubility
    """
    mw = pubchem_data.get("molecular_weight")
    return {
        "pubchem_cid":          pubchem_data.get("cid"),
        "pubchem_url":          pubchem_data.get("pubchem_url"),
        "iupac_name":           pubchem_data.get("iupac_name"),
        "synonyms":             pubchem_data.get("synonyms", []),
        "inchikey":             pubchem_data.get("inchikey"),
        "smiles":               pubchem_data.get("smiles"),
        "molecular_formula":    pubchem_data.get("molecular_formula"),
        "molecular_weight":     round(float(mw), 2) if mw else None,
        "logp":                 pubchem_data.get("logp"),
        "melting_point":        pubchem_data.get("melting_point"),
        "solubility":           pubchem_data.get("solubility"),
        "pka":                  pubchem_data.get("pka"),
        "pubchem_query_status": pubchem_data.get("query_status"),
        "pubchem_cached":       pubchem_data.get("cached", False),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_bp_database(
    max_drugs: Optional[int] = None,
    skip_cached: bool = True,
    delay_between: float = 0.25,
) -> dict:
    """
    Enrich all BP JSON monographs with PubChem data.
    Queries PubChem for each drug and merges fields into the JSON file.
    """
    bp_json_dir = Path("pharmacopoeia_db") / "BP" / "json"
    if not bp_json_dir.exists():
        raise FileNotFoundError(
            f"BP JSON directory not found: {bp_json_dir}\n"
            "Run: python cli.py build-pharmacopoeia-db --type BP"
        )

    files = sorted(bp_json_dir.glob("*.json"))
    if max_drugs:
        files = files[:max_drugs]

    summary = {"enriched": 0, "skipped": 0, "not_found": 0, "errors": 0}
    total   = len(files)

    print(f"\n{'='*60}")
    print(f"  Enriching {total} BP monographs with PubChem data")
    print(f"{'='*60}")

    for i, fpath in enumerate(files, 1):
        try:
            mono = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  [{i:4d}/{total}] ERROR reading {fpath.name}: {exc}")
            summary["errors"] += 1
            continue

        if skip_cached and mono.get("pubchem_cid"):
            summary["skipped"] += 1
            continue

        drug_name = mono.get("drug_name", fpath.stem)

        # Strip UI artefacts before querying PubChem
        # e.g. "Abacavir Sulfate Maximise" -> "Abacavir Sulfate"
        # e.g. "Povidone1" -> "Povidone"
        drug_name_clean = re.sub(
            r"\s*(Maximise|Maximize)\s*$", "", drug_name, flags=re.IGNORECASE
        ).strip()
        drug_name_clean = re.sub(r"\d+$", "", drug_name_clean).strip()

        try:
            pubchem = query_pubchem(drug_name_clean, use_cache=True)
            fields  = map_to_dossier_fields(pubchem)
            mono.update(fields)

            fpath.write_text(
                json.dumps(mono, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            status = "✓" if pubchem["query_status"] == "found" else "✗"
            mp     = pubchem.get("melting_point") or "—"
            print(
                f"  [{i:4d}/{total}] {status} {drug_name_clean[:40]:40s} "
                f"CID={str(pubchem.get('cid') or '—'):8}  MP={mp}"
            )

            if pubchem["query_status"] == "found":
                summary["enriched"] += 1
            else:
                summary["not_found"] += 1

            if delay_between > 0:
                time.sleep(delay_between)

        except Exception as exc:
            print(f"  [{i:4d}/{total}] ERROR {drug_name_clean if 'drug_name_clean' in dir() else drug_name[:40]}: {exc}")
            summary["errors"] += 1

    print(f"\n  ── Enrichment complete ──")
    print(f"     Enriched  : {summary['enriched']}")
    print(f"     Skipped   : {summary['skipped']}")
    print(f"     Not found : {summary['not_found']}")
    print(f"     Errors    : {summary['errors']}")
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE STATS
# ═══════════════════════════════════════════════════════════════════════════════

def cache_stats() -> dict:
    if not CACHE_DIR.exists():
        return {"total": 0, "found": 0, "not_found": 0, "cache_dir": str(CACHE_DIR)}
    files     = list(CACHE_DIR.glob("*.json"))
    found     = sum(1 for f in files
                    if json.loads(f.read_text(encoding="utf-8")).get("query_status") == "found")
    return {
        "total":     len(files),
        "found":     found,
        "not_found": len(files) - found,
        "cache_dir": str(CACHE_DIR),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    drug = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "metformin hydrochloride"
    print(f"\nQuerying PubChem for: {drug}\n")
    result = query_pubchem(drug, use_cache=False)
    fields = map_to_dossier_fields(result)
    for k, v in fields.items():
        print(f"  {k:25s}: {v}")