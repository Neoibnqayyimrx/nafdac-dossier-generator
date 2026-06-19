"""
web_scrapers.py — Phase 5 (v2, corrected)

5.1  NAFDAC Greenbook  — registration status + product listings
     Source: greenbook.nafdac.gov.ng (DataTables POST to root)
     Fallback: nafdac.gov.ng/productstable/ static page

5.2  WHO Prequalification — FPP and API prequalification check
     Source: extranet.who.int/prequal (HTML scrape)
     Fallback: OpenFDA WHO cross-reference fields

5.3  OpenFDA (replaces DrugBank — DrugBank blocks all scrapers)
     Source: api.fda.gov/drug/label.json  (free, no key needed)
     Fields: mechanism of action, pharmacokinetics, interactions,
             clinical pharmacology, warnings, indications

All results cached in scrapers_cache/ for 24 h.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import requests
from bs4 import BeautifulSoup

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DIR = Path("scrapers_cache")
for sub in ("nafdac", "who", "openfda"):
    (CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)

CACHE_TTL_HOURS = 24

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name.lower().strip())


def _cache_path(subdir: str, key: str) -> Path:
    return CACHE_DIR / subdir / f"{_slug(key)}.json"


def _load_cache(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(data.get("_cached_at", "2000-01-01"))
        if datetime.utcnow() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
            return data
    except Exception:
        pass
    return None


def _save_cache(path: Path, data: dict) -> None:
    data["_cached_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ═════════════════════════════════════════════════════════════════════════════
# 5.1  NAFDAC GREENBOOK
# ═════════════════════════════════════════════════════════════════════════════

NAFDAC_ROOT     = "https://greenbook.nafdac.gov.ng"
NAFDAC_FALLBACK = "https://nafdac.gov.ng/productstable/"

_DT_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": NAFDAC_ROOT + "/",
    "Origin": NAFDAC_ROOT,
}


def _nafdac_datatable(drug_name: str) -> list[dict]:
    """
    POST to the Greenbook root — the JS sends DataTables AJAX here.
    The inline script shows these extra params: search_ingredient, search_nrn, etc.
    """
    payload = {
        "draw": "1",
        "start": "0",
        "length": "50",
        "search[value]": drug_name,
        "search[regex]": "false",
        "search_product": drug_name,
        "search_ingredient": drug_name,
        "search_nrn": "",
        "search_applicant": "",
        "search_aproval_date": "",
        "columns[0][data]": "product_name",
        "columns[0][name]": "product_name",
        "columns[0][searchable]": "true",
        "columns[0][orderable]": "true",
        "columns[0][search][value]": "",
        "columns[0][search][regex]": "false",
        "order[0][column]": "0",
        "order[0][dir]": "asc",
    }
    try:
        r = requests.post(
            NAFDAC_ROOT,
            data=payload,
            headers=_DT_HEADERS,
            timeout=25,
        )
        r.raise_for_status()
        body = r.json()
        # DataTables wraps rows in "data" key
        if isinstance(body, dict):
            return body.get("data", body.get("products", body.get("results", [])))
        if isinstance(body, list):
            return body
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        pass  # server is flaky — fall through to fallback
    except Exception:
        pass
    return []


def _nafdac_fallback_html(drug_name: str) -> list[dict]:
    """
    Scrape the static nafdac.gov.ng/productstable/ page.
    This is a simpler HTML table that doesn't require JS.
    """
    try:
        r = requests.get(
            NAFDAC_FALLBACK,
            params={"s": drug_name},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        drug_lower = drug_name.lower()
        rows = []

        for table in soup.find_all("table"):
            thead = table.find("thead")
            col_names = []
            if thead:
                col_names = [
                    th.get_text(strip=True).lower().replace(" ", "_")
                    for th in thead.find_all(["th", "td"])
                ]
            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if not cells:
                    continue
                row_text = " ".join(cells).lower()
                if drug_lower[:5] in row_text:
                    if col_names:
                        row = dict(zip(col_names, cells))
                    else:
                        row = {f"col_{i}": v for i, v in enumerate(cells)}
                    rows.append(row)
        return rows
    except Exception:
        return []


def _normalise_nafdac_row(row: dict) -> dict:
    """Map various field name formats to a standard schema."""
    def g(*keys):
        for k in keys:
            v = row.get(k, "")
            if v:
                return str(v).strip()
        return ""

    return {
        "product_name":       g("product_name", "name", "ProductName", "col_0"),
        "nrn":                g("nrn", "NRN", "nafdac_reg_no", "reg_no", "col_2"),
        "form":               g("form", "dosage_form", "Form", "col_3"),
        "strength":           g("strengths", "strength", "Strength", "col_4"),
        "applicant":          g("applicant_name", "applicant", "Applicant", "col_5"),
        "approval_date":      g("approval_date", "ApprovalDate", "date", "col_6"),
        "status":             g("status", "Status", "col_7") or "Active",
        "active_ingredients": g("active_ingredients", "ActiveIngredients", "ingredients", "col_1"),
        "route":              g("route", "route.name", "roa", "col_8"),
    }


def nafdac_search(
    drug_name: str,
    category: str = "Drugs",
    use_cache: bool = True,
) -> dict:
    """
    Search NAFDAC Greenbook for a drug.

    Returns registration status + list of matching products.
    """
    cpath = _cache_path("nafdac", f"{drug_name}_{category}")
    if use_cache:
        cached = _load_cache(cpath)
        if cached:
            cached["cached"] = True
            return cached

    result: dict = {
        "drug_name": drug_name,
        "query_status": "error",
        "registration_status": "unknown",
        "listings": [],
        "total": 0,
        "source": "live",
        "cached": False,
        "note": "",
    }

    # Primary: DataTables POST to Greenbook root
    rows = _nafdac_datatable(drug_name)

    # Fallback: static HTML table
    if not rows:
        rows = _nafdac_fallback_html(drug_name)
        if rows:
            result["note"] = "Results from nafdac.gov.ng/productstable (Greenbook was unreachable)"

    listings = [_normalise_nafdac_row(r) for r in rows]

    # Filter to rows that actually mention our drug
    drug_stem = drug_name.lower().replace(" ", "")[:6]
    filtered = [
        l for l in listings
        if drug_stem in (l["product_name"] + l["active_ingredients"]).lower().replace(" ", "")
    ] or listings  # if filter removes everything, keep all (better than nothing)

    result["listings"] = filtered
    result["total"] = len(filtered)
    result["query_status"] = "found" if filtered else "not_found"
    result["registration_status"] = "registered" if filtered else "not_registered"

    if not filtered:
        result["note"] = (
            "No listings found. The Greenbook server may be temporarily unreachable — "
            "verify manually at greenbook.nafdac.gov.ng"
        )

    _save_cache(cpath, result)
    return result


def nafdac_verify_registration_number(nrn: str) -> dict:
    """Verify a specific NAFDAC Registration Number."""
    cpath = _cache_path("nafdac", f"nrn_{nrn}")
    cached = _load_cache(cpath)
    if cached:
        cached["cached"] = True
        return cached

    result = {"nrn": nrn, "valid": False, "product": None, "cached": False}

    # Try DataTables with NRN in search_nrn field
    payload_nrn = {
        "draw": "1", "start": "0", "length": "5",
        "search[value]": nrn, "search[regex]": "false",
        "search_nrn": nrn,
    }
    try:
        r = requests.post(NAFDAC_ROOT, data=payload_nrn, headers=_DT_HEADERS, timeout=20)
        rows = r.json().get("data", []) if r.status_code == 200 else []
        if rows:
            result["valid"] = True
            result["product"] = _normalise_nafdac_row(rows[0])
    except Exception:
        pass

    if not result["valid"]:
        # Fallback: search HTML table
        rows = _nafdac_fallback_html(nrn)
        if rows:
            result["valid"] = True
            result["product"] = _normalise_nafdac_row(rows[0])

    _save_cache(cpath, result)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 5.2  WHO PREQUALIFICATION
# ═════════════════════════════════════════════════════════════════════════════

WHO_FPP_URL = "https://extranet.who.int/prequal/medicines/prequalified-lists-medicines"
WHO_API_URL = "https://extranet.who.int/prequal/medicines/active-pharmaceutical-ingredients"
# OpenFDA cross-reference — contains "is_original_packager" + country/WHO fields
OPENFDA_LABEL = "https://api.fda.gov/drug/label.json"


def _who_scrape(url: str, drug_name: str) -> list[dict]:
    """Scrape a WHO prequalification page for matching rows."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        drug_lower = drug_name.lower()
        results = []

        for table in soup.find_all("table"):
            headers_row = table.find("tr")
            col_names = []
            if headers_row:
                col_names = [
                    th.get_text(strip=True).lower().replace(" ", "_")
                    for th in headers_row.find_all(["th", "td"])
                ]
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if not cells:
                    continue
                if drug_lower[:5] in " ".join(cells).lower():
                    row = dict(zip(col_names, cells)) if col_names else {"raw": cells}
                    results.append(row)

        # Some WHO pages use divs/cards
        if not results:
            for el in soup.find_all(["p", "li", "div"]):
                text = el.get_text(strip=True)
                if drug_lower[:5] in text.lower() and 20 < len(text) < 500:
                    results.append({"text": text})
        return results
    except requests.exceptions.Timeout:
        return []
    except Exception:
        return []


def _openfda_who_check(drug_name: str) -> bool:
    """
    Cross-check: OpenFDA drug labels sourced from WHO PQ manufacturers
    will have openfda.manufacturer_name entries — we use this as a
    secondary signal when WHO extranet is unreachable.
    """
    try:
        r = requests.get(
            OPENFDA_LABEL,
            params={
                "search": f'openfda.generic_name:"{drug_name}"',
                "limit": 1,
            },
            headers=HEADERS,
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results:
                mfr = results[0].get("openfda", {}).get("manufacturer_name", [])
                # WHO-prequalified products often appear in FDA labels
                return len(mfr) > 0
    except Exception:
        pass
    return False


def who_prequal_check(drug_name: str, use_cache: bool = True) -> dict:
    """
    Check WHO Prequalification for a drug (FPP + API lists).
    """
    cpath = _cache_path("who", drug_name)
    if use_cache:
        cached = _load_cache(cpath)
        if cached:
            cached["cached"] = True
            return cached

    result = {
        "drug_name": drug_name,
        "fpp_prequalified": False,
        "api_prequalified": False,
        "fpp_listings": [],
        "api_listings": [],
        "who_prequal_url": WHO_FPP_URL,
        "note": "",
        "cached": False,
    }

    fpp_rows = _who_scrape(WHO_FPP_URL, drug_name)
    result["fpp_listings"] = fpp_rows
    result["fpp_prequalified"] = len(fpp_rows) > 0

    time.sleep(1)

    api_rows = _who_scrape(WHO_API_URL, drug_name)
    result["api_listings"] = api_rows
    result["api_prequalified"] = len(api_rows) > 0

    # If WHO extranet timed out, note it clearly
    if not fpp_rows and not api_rows:
        result["note"] = (
            "WHO extranet may require a session/login, or returned no results. "
            "Verify manually at extranet.who.int/prequal — "
            "note: most cardiovascular drugs (e.g. amlodipine) are NOT WHO-prequalified "
            "as WHO PQ focuses on HIV/TB/malaria/NTD medicines."
        )

    _save_cache(cpath, result)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 5.3  OpenFDA  (replaces DrugBank — DrugBank blocks all non-browser clients)
# ═════════════════════════════════════════════════════════════════════════════

OPENFDA_BASE = "https://api.fda.gov"


def _openfda_label_query(drug_name: str) -> Optional[dict]:
    """Fetch the first matching drug label from OpenFDA."""
    # Try generic name first, then brand name
    for field in ("openfda.generic_name", "openfda.brand_name", "openfda.substance_name"):
        try:
            r = requests.get(
                f"{OPENFDA_BASE}/drug/label.json",
                params={
                    "search": f'{field}:"{drug_name}"',
                    "limit": 1,
                },
                headers=HEADERS,
                timeout=20,
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    return results[0]
        except Exception:
            continue
    return None


def _openfda_drugsfda_query(drug_name: str) -> list[dict]:
    """Query OpenFDA drug approvals database for application records."""
    try:
        r = requests.get(
            f"{OPENFDA_BASE}/drug/drugsfda.json",
            params={
                "search": f'openfda.generic_name:"{drug_name}"',
                "limit": 5,
            },
            headers=HEADERS,
            timeout=20,
        )
        if r.status_code == 200:
            return r.json().get("results", [])
    except Exception:
        pass
    return []


def _extract_text(val) -> str:
    """OpenFDA fields are lists of strings."""
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val).strip()
    return str(val).strip()


def _parse_pk_from_clinical(clinical_text: str) -> dict:
    """
    Extract pharmacokinetic values from clinical_pharmacology free text.
    OpenFDA stores the full SPL section as a string.
    """
    pk = {
        "half_life": "",
        "protein_binding": "",
        "volume_of_distribution": "",
        "clearance": "",
        "bioavailability": "",
        "tmax": "",
        "absorption": "",
    }
    text = clinical_text.lower()

    patterns = {
        "half_life": r"(?:terminal\s+)?(?:elimination\s+)?half.?life[^\.\n]{0,60}?(\d[\d\.\s\-–]+\s*(?:hours?|hrs?|h\b))",
        "protein_binding": r"protein\s*binding[^\.\n]{0,40}?(\d[\d\.\s\-–%]+%)",
        "volume_of_distribution": r"volume\s+of\s+distribution[^\.\n]{0,60}?(\d[\d\.\s\-/±]+\s*(?:l/kg|l\b))",
        "bioavailability": r"(?:oral\s+)?bioavailability[^\.\n]{0,40}?(\d[\d\.\s\-–%]+%)",
        "tmax": r"t\s*max[^\.\n]{0,40}?(\d[\d\.\s\-–]+\s*(?:hours?|hrs?|h\b))",
        "clearance": r"clearance[^\.\n]{0,60}?(\d[\d\.\s\-/±]+\s*(?:ml/min|l/h))",
    }

    for field, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            pk[field] = m.group(1).strip()

    # Also try "absorption" as a free sentence
    abs_match = re.search(r"absorption[^\.]{0,200}\.", text, re.IGNORECASE)
    if abs_match:
        pk["absorption"] = abs_match.group(0).strip()[:200]

    return pk


def openfda_lookup(drug_name: str, use_cache: bool = True) -> dict:
    """
    Fetch drug data from OpenFDA:
      - Mechanism of action
      - Pharmacokinetics (parsed from clinical_pharmacology)
      - Drug interactions
      - Indications
      - Warnings
      - FDA approval info

    Free API, no key required. Replaces DrugBank.
    """
    cpath = _cache_path("openfda", drug_name)
    if use_cache:
        cached = _load_cache(cpath)
        if cached:
            cached["cached"] = True
            return cached

    result: dict = {
        "drug_name": drug_name,
        "query_status": "error",
        "source": "OpenFDA (api.fda.gov)",
        "openfda_url": f"{OPENFDA_BASE}/drug/label.json",
        "brand_names": [],
        "generic_name": "",
        "manufacturer": "",
        "mechanism_of_action": "",
        "indications_and_usage": "",
        "clinical_pharmacology": "",
        "pharmacokinetics": {},
        "drug_interactions": "",
        "warnings": "",
        "contraindications": "",
        "dosage_forms_strengths": "",
        "fda_application_number": "",
        "cached": False,
    }

    label = _openfda_label_query(drug_name)
    if not label:
        result["query_status"] = "not_found"
        _save_cache(cpath, result)
        return result

    openfda = label.get("openfda", {})

    result["brand_names"]   = openfda.get("brand_name", [])[:5]
    result["generic_name"]  = _extract_text(openfda.get("generic_name", []))
    result["manufacturer"]  = _extract_text(openfda.get("manufacturer_name", []))

    result["mechanism_of_action"]    = _extract_text(label.get("mechanism_of_action", ""))[:600]
    result["indications_and_usage"]  = _extract_text(label.get("indications_and_usage", ""))[:400]
    result["drug_interactions"]      = _extract_text(label.get("drug_interactions", ""))[:600]
    result["warnings"]               = _extract_text(label.get("warnings", label.get("warnings_and_cautions", "")))[:400]
    result["contraindications"]      = _extract_text(label.get("contraindications", ""))[:300]

    # Clinical pharmacology — full text + PK extraction
    cp_text = _extract_text(label.get("clinical_pharmacology", ""))
    result["clinical_pharmacology"]  = cp_text[:800]
    result["pharmacokinetics"]       = _parse_pk_from_clinical(cp_text)

    # Also try dedicated pharmacokinetics section if present
    pk_section = _extract_text(label.get("pharmacokinetics", ""))
    if pk_section:
        result["clinical_pharmacology"] += "\n\n" + pk_section[:400]
        extra_pk = _parse_pk_from_clinical(pk_section)
        for k, v in extra_pk.items():
            if v and not result["pharmacokinetics"].get(k):
                result["pharmacokinetics"][k] = v

    # Dosage forms
    result["dosage_forms_strengths"] = _extract_text(
        label.get("dosage_forms_and_strengths",
        label.get("how_supplied", ""))
    )[:300]

    # FDA application number from drugsfda
    apps = _openfda_drugsfda_query(drug_name)
    if apps:
        appl = apps[0].get("application_number", "")
        result["fda_application_number"] = appl

    result["query_status"] = "found"
    _save_cache(cpath, result)
    return result


# Keep "drugbank_lookup" as an alias so existing CLI code doesn't break
def drugbank_lookup(drug_name: str, use_cache: bool = True) -> dict:
    """Alias → now calls openfda_lookup (DrugBank blocks scrapers)."""
    r = openfda_lookup(drug_name, use_cache=use_cache)
    # Add drugbank-compatible keys so CLI display still works
    r.setdefault("drugbank_id", "")
    r.setdefault("drugbank_url", "")
    r.setdefault("targets", [])
    r.setdefault("pharmacokinetics", {})
    return r


# ═════════════════════════════════════════════════════════════════════════════
# Unified fetch
# ═════════════════════════════════════════════════════════════════════════════

def fetch_all_external(drug_name: str, use_cache: bool = True) -> dict:
    results = {"drug_name": drug_name, "nafdac": None, "who": None, "drugbank": None}
    for key, fn in [
        ("nafdac",   lambda: nafdac_search(drug_name, use_cache=use_cache)),
        ("who",      lambda: who_prequal_check(drug_name, use_cache=use_cache)),
        ("drugbank", lambda: openfda_lookup(drug_name, use_cache=use_cache)),
    ]:
        try:
            results[key] = fn()
        except Exception as e:
            results[key] = {"error": str(e)}
    return results


# ═════════════════════════════════════════════════════════════════════════════
# Cache utilities
# ═════════════════════════════════════════════════════════════════════════════

def scraper_cache_stats() -> dict:
    stats = {}
    for sub in ("nafdac", "who", "openfda"):
        stats[sub] = len(list((CACHE_DIR / sub).glob("*.json")))
    # also count old "drugbank" folder if it exists
    db_dir = CACHE_DIR / "drugbank"
    stats["drugbank_legacy"] = len(list(db_dir.glob("*.json"))) if db_dir.exists() else 0
    stats["total"] = sum(v for k, v in stats.items() if k != "cache_dir")
    stats["cache_dir"] = str(CACHE_DIR)
    return stats


def clear_scraper_cache(source: Optional[str] = None) -> int:
    count = 0
    dirs = [source] if source else ["nafdac", "who", "openfda", "drugbank"]
    for d in dirs:
        p = CACHE_DIR / d
        if p.exists():
            for f in p.glob("*.json"):
                f.unlink()
                count += 1
    return count