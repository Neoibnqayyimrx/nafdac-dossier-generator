import json
from pathlib import Path

cache_dir = Path('pharmacopoeia_db/pubchem_cache')

# Check what amlodipine files exist
files = list(cache_dir.glob('amlod*.json'))
print("Found:", [f.name for f in files])

src = cache_dir / 'amlodipine_besylate.json'
dst = cache_dir / 'amlodipine_besilate.json'

if src.exists():
    data = json.loads(src.read_text(encoding='utf-8'))
    data['drug_name'] = 'amlodipine besilate'
    dst.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('Cache copied OK')
    print('CID:', data.get('cid'))
    print('MW:', data.get('molecular_weight'))
    print('SMILES:', (data.get('smiles') or '')[:60])
elif dst.exists():
    print('Besilate cache already exists')
    data = json.loads(dst.read_text(encoding='utf-8'))
    print('CID:', data.get('cid'))
else:
    print('Neither cache file found')
    print('All cache files:', [f.name for f in cache_dir.glob('*.json')][:10])