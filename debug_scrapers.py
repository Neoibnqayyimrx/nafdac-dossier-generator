"""
debug_scrapers.py — run this on your Windows machine to:
  1. Clear bad cache entries from the failed first run
  2. Discover the actual NAFDAC Greenbook API endpoint from network traffic
  3. Test DrugBank and WHO directly
  4. Print exactly what each scraper receives

Run with:  python debug_scrapers.py
"""

import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Step 1: Clear bad cache ────────────────────────────────────────────────
print("=" * 60)
print("STEP 1: Clearing bad cache entries")
print("=" * 60)

cache_dir = Path("scrapers_cache")
cleared = 0
for f in cache_dir.rglob("*.json"):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        # Delete if it recorded a miss (cached empty result)
        if (data.get("query_status") in ("not_found", "error")
                or data.get("registration_status") == "not_registered"
                or (data.get("fpp_prequalified") is False and data.get("api_prequalified") is False)):
            f.unlink()
            print(f"  Deleted: {f}")
            cleared += 1
    except Exception:
        pass
print(f"  Cleared {cleared} bad cache entries\n")


# ── Step 2: NAFDAC Greenbook — find the real API endpoint ─────────────────
print("=" * 60)
print("STEP 2: NAFDAC Greenbook endpoint discovery")
print("=" * 60)

nafdac_candidates = [
    # JSON API candidates (DataTables backend)
    ("GET",  "https://greenbook.nafdac.gov.ng/products",
     {"name": "amlodipine", "draw": 1, "start": 0, "length": 10}),
    ("GET",  "https://greenbook.nafdac.gov.ng/api/products",
     {"name": "amlodipine", "draw": 1, "start": 0, "length": 10}),
    ("GET",  "https://greenbook.nafdac.gov.ng/drugs",
     {"name": "amlodipine", "draw": 1, "start": 0, "length": 10}),
    ("GET",  "https://greenbook.nafdac.gov.ng/search",
     {"q": "amlodipine", "category": "Drugs"}),
    # DataTables AJAX endpoint (common pattern)
    ("POST", "https://greenbook.nafdac.gov.ng/products",
     {"name": "amlodipine", "draw": "1", "start": "0", "length": "10",
      "search[value]": "amlodipine", "search[regex]": "false"}),
    # Main page (HTML fallback)
    ("GET",  "https://greenbook.nafdac.gov.ng/",
     {"name": "amlodipine"}),
]

nafdac_headers = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://greenbook.nafdac.gov.ng/",
}

for method, url, params in nafdac_candidates:
    try:
        if method == "POST":
            r = requests.post(url, data=params, headers=nafdac_headers, timeout=15)
        else:
            r = requests.get(url, params=params, headers=nafdac_headers, timeout=15)
        ct = r.headers.get("content-type", "")
        print(f"\n  {method} {url}")
        print(f"  Status: {r.status_code}  |  Content-Type: {ct[:50]}")
        print(f"  Body (first 400): {r.text[:400]}")
    except Exception as e:
        print(f"\n  {method} {url} → ERROR: {e}")

print()


# ── Step 3: DrugBank ───────────────────────────────────────────────────────
print("=" * 60)
print("STEP 3: DrugBank")
print("=" * 60)

db_candidates = [
    "https://go.drugbank.com/unearth/q?query=amlodipine&searcher=drugs",
    "https://go.drugbank.com/drugs?q=amlodipine",
    "https://www.drugbank.com/drugs/DB00381",  # known amlodipine ID
]

for url in db_candidates:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        print(f"\n  GET {url}")
        print(f"  Status: {r.status_code}  |  Final URL: {r.url}")
        print(f"  Content-Type: {ct[:50]}")
        print(f"  Body (first 500): {r.text[:500]}")
    except Exception as e:
        print(f"\n  GET {url} → ERROR: {e}")

print()


# ── Step 4: WHO Prequalification ───────────────────────────────────────────
print("=" * 60)
print("STEP 4: WHO Prequalification")
print("=" * 60)

who_candidates = [
    "https://extranet.who.int/prequal/medicines/prequalified-lists-medicines",
    "https://extranet.who.int/prequal/medicines/active-pharmaceutical-ingredients",
    # WHO also has a public search API sometimes
    "https://extranet.who.int/prequal/sites/default/files/xmls/lists/pq-list-medicines.xml",
]

for url in who_candidates:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        ct = r.headers.get("content-type", "")
        print(f"\n  GET {url}")
        print(f"  Status: {r.status_code}  |  Content-Type: {ct[:50]}")
        print(f"  Body (first 400): {r.text[:400]}")
    except Exception as e:
        print(f"\n  GET {url} → ERROR: {e}")

print("\n" + "=" * 60)
print("Done. Paste this output back and I'll fix the scrapers.")
print("=" * 60)