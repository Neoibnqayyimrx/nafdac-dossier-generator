from bs4 import BeautifulSoup
import re

with open(
    'pharmacopoeia_db/BP/BP 2024/BP 2024 (EP 11.3)/monographs/metformin-hydrochloride.html',
    encoding='utf-8', errors='replace'
) as f:
    soup = BeautifulSoup(f.read(), 'lxml')

for sec in soup.find_all('section', class_='section'):
    h2 = sec.find('h2', class_='mainheading')
    if not h2 or 'DEFINITION' not in h2.get_text().upper():
        continue

    print("=== DEFINITION section raw text ===")
    print(repr(sec.get_text()[:300]))
    print()

    print("=== subsection divs inside DEFINITION ===")
    for div in sec.find_all('div', class_='subsection'):
        h3 = div.find('h3')
        print(f"  h3 text: {repr(h3.get_text()) if h3 else 'NO H3'}")
        print(f"  div text: {repr(div.get_text()[:150])}")
        print()

    print("=== After space-insertion fix ===")
    raw = sec.get_text()
    fixed = re.sub(r'([A-Za-z])(\d)', r'\1 \2', raw)
    print(repr(fixed[:300]))