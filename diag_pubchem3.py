import requests, json

cid = 14219
# Fetch the full compound view to find solubility heading
url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
r = requests.get(url)
data = r.json()

def walk(node, depth=0):
    if isinstance(node, dict):
        heading = node.get("TOCHeading")
        if heading:
            print("  " * depth + f"• {heading}")
            for info in node.get("Information", []):
                val = info.get("Value", {})
                swm = val.get("StringWithMarkup", [])
                if swm:
                    print("  " * (depth+1) + f'= {swm[0].get("String","")[:80]}')
                    break
        for v in node.values():
            walk(v, depth)
    elif isinstance(node, list):
        for item in node:
            walk(item, depth)

walk(data)