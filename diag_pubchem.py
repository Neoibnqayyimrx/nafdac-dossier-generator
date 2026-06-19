import requests, json

cid = 14219

# Check XLogP
url1 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/XLogP,CanonicalSMILES,IsomericSMILES/JSON"
r1 = requests.get(url1)
print("=== PROPERTIES ===")
print(json.dumps(r1.json(), indent=2))

# Check PUG View headings available
url2 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Experimental+Properties"
r2 = requests.get(url2)
data = r2.json()
print("\n=== PUG VIEW TOP-LEVEL HEADINGS ===")
for section in data.get("Record", {}).get("Section", []):
    print(f"  • {section.get('TOCHeading')}")
    for sub in section.get("Section", []):
        print(f"      – {sub.get('TOCHeading')}")