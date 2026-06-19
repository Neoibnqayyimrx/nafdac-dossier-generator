"""
debug_scrapers2.py — Run this to find the real NAFDAC API route.

Strategy:
  1. Fetch the Greenbook homepage and extract all JS/XHR references
  2. Load the main JS bundle and grep for route strings
  3. Try DataTables-style AJAX endpoints common in Laravel
  4. Also re-test DrugBank and WHO with better headers

Run with:  python debug_scrapers2.py
"""

import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE = "https://greenbook.nafdac.gov.ng"

# ── Step 1: Fetch homepage, find all script tags ───────────────────────────
print("=" * 60)
print("STEP 1: Greenbook homepage — extracting JS bundle URLs")
print("=" * 60)

r = requests.get(BASE, headers=HEADERS, timeout=20)
print(f"  Homepage status: {r.status_code}")
soup = BeautifulSoup(r.text, "lxml")

# Find all <script src="..."> tags
script_urls = []
for tag in soup.find_all("script", src=True):
    src = tag["src"]
    if not src.startswith("http"):
        src = BASE + "/" + src.lstrip("/")
    script_urls.append(src)
    print(f"  Script: {src}")

# Also find any inline fetch/axios/ajax calls
inline_scripts = [s.string for s in soup.find_all("script") if s.string]
print(f"\n  Inline script blocks: {len(inline_scripts)}")
for i, s in enumerate(inline_scripts):
    if any(kw in s for kw in ["fetch(", "axios", "ajax", "url:", "route(", "/api/", "DataTable"]):
        print(f"\n  [Inline {i}] (relevant portion):")
        # Print lines containing URL-like content
        for line in s.split("\n"):
            if any(kw in line for kw in ["url", "route", "fetch", "ajax", "ajax", "api", "product", "search"]):
                print(f"    {line.strip()[:120]}")

print()

# ── Step 2: Grep JS bundles for route strings ─────────────────────────────
print("=" * 60)
print("STEP 2: Scanning JS bundles for API routes")
print("=" * 60)

for js_url in script_urls[:8]:  # limit to first 8 scripts
    try:
        jr = requests.get(js_url, headers=HEADERS, timeout=15)
        if jr.status_code != 200:
            continue
        js = jr.text
        # Find strings that look like API routes
        found = re.findall(r'["\']([/][a-zA-Z0-9/_\-]{3,50})["\']', js)
        unique = sorted(set(found))
        api_like = [f for f in unique if any(kw in f for kw in
                    ["product", "search", "drug", "api", "query", "filter", "list", "data"])]
        if api_like:
            print(f"\n  {js_url.split('/')[-1]} — API-like routes found:")
            for f in api_like[:20]:
                print(f"    {f}")
    except Exception as e:
        print(f"  {js_url} → {e}")

print()

# ── Step 3: Try common Laravel DataTables patterns ────────────────────────
print("=" * 60)
print("STEP 3: Trying Laravel DataTables patterns")
print("=" * 60)

ajax_headers = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE + "/",
}

# Common Laravel patterns for DataTables server-side
candidates = [
    f"{BASE}/product-list",
    f"{BASE}/product/list",
    f"{BASE}/product/search",
    f"{BASE}/products/search",
    f"{BASE}/products/list",
    f"{BASE}/medicines",
    f"{BASE}/medicines/search",
    f"{BASE}/drug/search",
    f"{BASE}/datatable/products",
    f"{BASE}/api/datatable",
    f"{BASE}/product-categories/drugs",
    f"{BASE}/products-table",
    f"{BASE}/productsTable",
    f"{BASE}/getProducts",
    f"{BASE}/get-products",
    f"{BASE}/filterProducts",
    f"{BASE}/filter-products",
    f"{BASE}/nafdac/products",
]

for url in candidates:
    try:
        r = requests.get(
            url,
            params={"name": "amlodipine", "draw": 1, "start": 0, "length": 5},
            headers=ajax_headers,
            timeout=10,
        )
        print(f"  {url.replace(BASE,'')} → {r.status_code}  ({r.headers.get('content-type','')[:40]})")
        if r.status_code == 200:
            print(f"  *** HIT! Body: {r.text[:400]}")
    except Exception as e:
        print(f"  {url.replace(BASE,'')} → ERROR: {e}")

print()

# ── Step 4: DrugBank with session cookie approach ─────────────────────────
print("=" * 60)
print("STEP 4: DrugBank — session + search")
print("=" * 60)

session = requests.Session()
session.headers.update(HEADERS)

# First get the homepage to pick up cookies
try:
    home = session.get("https://go.drugbank.com", timeout=15)
    print(f"  Homepage: {home.status_code}  cookies: {list(session.cookies.keys())}")

    # Now try the search
    search = session.get(
        "https://go.drugbank.com/unearth/q",
        params={"query": "amlodipine", "searcher": "drugs"},
        headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,*/*",
                 "Referer": "https://go.drugbank.com/"},
        timeout=15,
    )
    print(f"  Search: {search.status_code}  final_url: {search.url}")
    print(f"  Body (first 600): {search.text[:600]}")

    # Try direct drug page (amlodipine is DB00381)
    drug_page = session.get(
        "https://go.drugbank.com/drugs/DB00381",
        headers={**HEADERS, "Referer": "https://go.drugbank.com/"},
        timeout=15,
    )
    print(f"\n  Direct DB00381: {drug_page.status_code}")
    print(f"  Body (first 600): {drug_page.text[:600]}")

except Exception as e:
    print(f"  DrugBank ERROR: {e}")

print()

# ── Step 5: WHO with session ───────────────────────────────────────────────
print("=" * 60)
print("STEP 5: WHO Prequalification")
print("=" * 60)

try:
    who_r = requests.get(
        "https://extranet.who.int/prequal/medicines/prequalified-lists-medicines",
        headers=HEADERS,
        timeout=20,
    )
    print(f"  Status: {who_r.status_code}")
    print(f"  Content-Type: {who_r.headers.get('content-type','')}")
    print(f"  Body (first 800): {who_r.text[:800]}")

    # Also try the new WHO PQ search API
    who_api = requests.get(
        "https://extranet.who.int/prequal/api/products",
        params={"search": "amlodipine"},
        headers={**HEADERS, "Accept": "application/json"},
        timeout=15,
    )
    print(f"\n  WHO API: {who_api.status_code}")
    print(f"  Body: {who_api.text[:400]}")
except Exception as e:
    print(f"  WHO ERROR: {e}")

print("\n" + "=" * 60)
print("Done. Paste ALL of this output back.")
print("=" * 60)