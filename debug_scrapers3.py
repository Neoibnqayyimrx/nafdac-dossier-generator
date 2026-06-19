"""
debug_scrapers3.py — Final targeted debug.

From Step 1 we know:
  - DataTables AJAX url is the ROOT: https://greenbook.nafdac.gov.ng
  - Extra params: search_ingredient, product_category filter
  - Fields: product_name, product_category.name, nrn, route.name, applicant.id
  - Detail URL: /products/details/<product_id>

Strategy:
  - POST to root with DataTables params
  - Try root with different DataTables draw/columns params
  - Use OpenFDA instead of DrugBank (free, no auth, great PK data)
  - Use WHO Essential Medicines PDF/list as fallback

Run with: python debug_scrapers3.py
"""

import requests
from bs4 import BeautifulSoup
import json

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

BASE = "https://greenbook.nafdac.gov.ng"

# ── NAFDAC: DataTables sends POST to root with these params ───────────────
print("=" * 60)
print("NAFDAC: POST to root with DataTables params")
print("=" * 60)

dt_headers = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": BASE + "/",
    "Origin": BASE,
}

# Standard DataTables server-side POST body
dt_params = {
    "draw": "1",
    "start": "0",
    "length": "10",
    "search[value]": "amlodipine",
    "search[regex]": "false",
    "search_ingredient": "amlodipine",
    "columns[0][data]": "product_name",
    "columns[0][name]": "product_name",
    "columns[0][searchable]": "true",
    "columns[0][orderable]": "true",
    "columns[0][search][value]": "",
    "order[0][column]": "0",
    "order[0][dir]": "asc",
}

# Try POST to root and several variations
for url in [
    BASE,
    BASE + "/",
    BASE + "/?draw=1",
]:
    try:
        r = requests.post(url, data=dt_params, headers=dt_headers, timeout=15)
        print(f"\nPOST {url}")
        print(f"  Status: {r.status_code}  CT: {r.headers.get('content-type','')[:50]}")
        print(f"  Body (500): {r.text[:500]}")
    except Exception as e:
        print(f"\nPOST {url} → ERROR: {e}")

# Try GET to root with search param
print("\n--- GET root with search params ---")
for params in [
    {"search[value]": "amlodipine", "draw": 1},
    {"search_product": "amlodipine", "draw": 1},
    {"q": "amlodipine"},
    {"name": "amlodipine"},
]:
    try:
        r = requests.get(BASE, params=params, headers=dt_headers, timeout=10)
        print(f"\nGET /?{list(params.keys())[0]}=...")
        print(f"  Status: {r.status_code}  CT: {r.headers.get('content-type','')[:50]}")
        if r.status_code == 200 and "product" in r.text.lower():
            print(f"  ** CONTAINS 'product' — Body: {r.text[:400]}")
        else:
            print(f"  Body (200): {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Check the homepage HTML for the full inline script
print("\n--- Full inline script from homepage ---")
r = requests.get(BASE, headers=HEADERS, timeout=15)
soup = BeautifulSoup(r.text, "lxml")
for s in soup.find_all("script"):
    if s.string and "ajax" in s.string.lower():
        print(s.string[:2000])
        break

print()

# ── OpenFDA — free API, no key needed, has drug label data ───────────────
print("=" * 60)
print("OpenFDA — drug labels (replaces DrugBank for PK/interactions)")
print("=" * 60)

openfda_url = "https://api.fda.gov/drug/label.json"
try:
    r = requests.get(
        openfda_url,
        params={"search": 'openfda.generic_name:"amlodipine"', "limit": 1},
        headers=HEADERS,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    data = r.json()
    result = data.get("results", [{}])[0]
    # Show available fields
    print(f"Available fields: {list(result.keys())[:20]}")
    # Show PK-relevant fields
    for field in ["clinical_pharmacology", "pharmacokinetics", "drug_interactions",
                  "warnings", "indications_and_usage", "dosage_and_administration",
                  "mechanism_of_action", "clinical_pharmacology_table"]:
        val = result.get(field)
        if val:
            text = val[0] if isinstance(val, list) else val
            print(f"\n  [{field}] (first 300):\n  {str(text)[:300]}")
except Exception as e:
    print(f"OpenFDA ERROR: {e}")

print()

# ── WHO Essential Medicines / PQ list ─────────────────────────────────────
print("=" * 60)
print("WHO Prequalification — testing correct URL")
print("=" * 60)

who_urls = [
    "https://extranet.who.int/prequal/medicines/prequalified-lists-medicines",
    "https://www.who.int/medicines/prequal/",
    # WHO has a public data API for essential medicines
    "https://list.essentialmedicines.org/api/products?search=amlodipine",
]
for url in who_urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"\n{url}")
        print(f"  Status: {r.status_code}  CT: {r.headers.get('content-type','')[:50]}")
        print(f"  Body (400): {r.text[:400]}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("Done — paste all output back.")
print("=" * 60)