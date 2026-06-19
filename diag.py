from bs4 import BeautifulSoup
import re

with open(
    'pharmacopoeia_db/BP/BP 2024/BP 2024 (EP 11.3)/monographs/metformin-hydrochloride.html',
    encoding='utf-8', errors='replace'
) as f:
    soup = BeautifulSoup(f.read(), 'lxml')

print("=== STORAGE SEARCH ===")
for tag in soup.find_all(string=re.compile('torage', re.IGNORECASE)):
    parent = tag.parent
    print(f"Tag: {parent.name}, class: {parent.get('class')}")
    print(f"Text: {tag[:100]}")
    print()

print("=== ALL H3 SUB-SECTIONS ===")
for h3 in soup.find_all('h3'):
    print(f"class={h3.get('class')}, text={h3.get_text()[:60]}")