# NAFDAC Dossier Generator — Project State

## Last Updated: 2026-06-10
## Current Phase: 3
## Current Step: COMPLETE — PHASE 3 DONE
## Status: READY FOR PHASE 4

---

## Project Stack
- Language: Python 3.13 (Miniconda on Windows)
- CLI: typer
- Docx: python-docx
- PDF parsing: pdfplumber
- HTML parsing: beautifulsoup4 + lxml
- Templating: Jinja2
- NER: spaCy blank (regex-primary)
- Config: PyYAML + pydantic
- AI: anthropic SDK
- Pharmacopoeia DB: local JSON
- Web: requests + beautifulsoup4
- PDF export: LibreOffice headless
- Structure imaging: RDKit + PubChem PNG

## Project Folder
Path: C:\Users\DELL\Desktop\Neoibnqayyim\nafdac-dossier-gen

## Install Command (run from project folder)
python -m pip install python-docx pdfplumber jinja2 pyyaml pydantic spacy requests beautifulsoup4 lxml pandas openpyxl anthropic diff-match-patch typer rich
conda install -c conda-forge rdkit -y

## Environment Variables Required
ANTHROPIC_API_KEY=your-key  (set with: $env:ANTHROPIC_API_KEY = "sk-ant-...")

## Completed Steps
- [x] 1.1 Project scaffold and virtual environment
- [x] 1.2 CLI skeleton with typer (all commands working)
- [x] 1.3 Drug profile YAML schema
- [x] 1.4 Pydantic validation model
- [x] 2.1 DOCX dossier parser
- [x] 2.2 PDF dossier parser
- [x] 2.3 Placeholder/variable detector (20+ patterns)
- [x] 2.4 Jinja2 template extractor
- [x] 2.5 Template library saver + manifest.json
- [x] 3.1 BP/USP monograph parser — verified on real files
- [x] 3.2 Local pharmacopoeia JSON database builder
      BP: 1,825 monographs parsed, 0 errors, 313 warnings (excipients/herbals)
      CLI: build-pharmacopoeia-db, add-pharmacopoeia, lookup-pharmacopoeia,
           pharmacopoeia-stats
- [x] 3.3 PubChem API integration
      Fields: CID, formula, MW, IUPAC name, SMILES, InChIKey, logP, MP,
              solubility, pKa
      Cache: pharmacopoeia_db/pubchem_cache/
      CLI: pubchem-lookup, pubchem-enrich-db, pubchem-stats
- [x] 3.3b Structure image fetcher
      PubChem PNG (primary) → RDKit from SMILES (fallback)
      Output: pharmacopoeia_db/structures/<drug>.png (300×300 px)
- [x] 3.3c draw-structure CLI command
      CLI: draw-structure, fetch-all-structures
- [x] 3.4 Spec priority resolver
      Priority: 1st dossier, 2nd BP, 3rd USP, 4th COA, 5th AI
      Metformin: 15/21 fields from BP (correct for raw material)
      AI fallback ready — needs Anthropic billing credits
      CLI: resolve-spec
      Output: pharmacopoeia_db/resolved/<drug>.json
- [ ] 4.1 NAFDAC folder structure builder
- [ ] 4.2 Module DOCX generators (1-5)
- [ ] 4.3 SmPC and PIL generator
- [ ] 4.4 LibreOffice PDF exporter
- [ ] 5.1 NAFDAC portal scraper
- [ ] 5.2 WHO prequalification checker
- [ ] 5.3 DrugBank public data scraper
- [ ] 6.1 Anthropic SDK narrative tweaker
- [ ] 6.2 Narrative diff viewer
- [ ] 6.3 AI spec gap filler
- [ ] 7.1 NAFDAC checklist validator
- [ ] 7.2 Missing section reporter
- [ ] 7.3 End-to-end integration test

## Decisions Made
- Output format: DOCX primary, PDF optional via LibreOffice headless
- Pharmacopoeia priority: BP > USP > COA > AI-generated
- NAFDAC target: Finished Product registration (New Product type default)
- CLI entry point: cli.py (run as: python cli.py <command>)
- Pydantic v2 used for validation
- Chemical structures: PubChem PNG primary, RDKit fallback
- SMILES field: stored as "smiles" in pubchem_api.py
- spaCy blank model (no download needed)
- Windows: use python -m pip (not pip directly — launcher broken)
- BP source: HTML files from pharmacopoeia.com
- USP source: PDF files, page 1 image-rendered, gaps filled by PubChem
- Assay limits: handles "per cent to", "% to", "%–%", en-dash variants
- Melting point: normalised °F → °C in spec_resolver
- AI fallback: only for fields unresolved by all other sources
- AI fields flagged low confidence, warned for manual verification

## Pharmacopoeia DB Structure
pharmacopoeia_db/
├── index.json
├── pubchem_cache/      ← one JSON per drug queried
├── structures/         ← one PNG per drug (300×300)
├── resolved/           ← one JSON per resolved spec
├── BP/
│   ├── json/           ← 1,825 .json files
│   └── BP 2024/BP 2024 (EP 11.3)/monographs/
└── USP/
    └── USP 43-NF38/USP 43 A to Z/{A-Z}/

## Files Created So Far
- cli.py
- pharmacopoeia_parser.py
- pharmacopoeia_db_builder.py
- pubchem_api.py
- structure_fetcher.py
- spec_resolver.py
- setup.py, requirements.txt, config_manager.py
- config/drug_profile.yaml, config/metformin.yaml
- models/__init__.py, models/drug_profile_model.py
- ingestion/__init__.py, docx_parser.py, pdf_parser.py, template_extractor.py
- tests/ (test files + CLI addition reference files)
- templates/manifest.json + all .jinja2 files
- pharmacopoeia_db/index.json
- pharmacopoeia_db/BP/json/*.json (1,825 files)
- pharmacopoeia_db/pubchem_cache/*.json
- pharmacopoeia_db/structures/*.png
- pharmacopoeia_db/resolved/*.json

## Known Issues / Notes
- molecular_formula includes MW and CAS from BP HTML — fix in Phase 4
- 313 BP warnings: excipients/herbals — expected, not bugs
- Full pubchem-enrich-db (all 1,825 drugs) not yet run
- ANTHROPIC_API_KEY must be set + account funded for AI fallback
- Rotate exposed API key immediately at console.anthropic.com

## Current Phase: COMPLETE — ALL 7 PHASES DONE
## Status: PRODUCTION READY

## Completed Steps
...
- [x] 7.1 NAFDAC checklist validator (Modules 1-5, 46 items)
- [x] 7.2 Missing section reporter (terminal + DOCX report)
- [x] 7.3 End-to-end integration test

## CLI Commands Available (full list)
python cli.py new-submission          # create submission folder
python cli.py generate-modules        # generate all module DOCX
python cli.py generate-smpc           # generate SmPC
python cli.py generate-pil            # generate PIL
python cli.py export-pdf              # single DOCX → PDF
python cli.py export-pdf-batch        # whole submission → PDF
python cli.py nafdac-search           # NAFDAC Greenbook lookup
python cli.py nafdac-verify           # verify NRN
python cli.py who-prequal             # WHO prequalification check
python cli.py drugbank-lookup         # OpenFDA drug data
python cli.py fetch-external          # all 3 scrapers at once
python cli.py tweak-narrative         # AI rewrite dossier section
python cli.py narrative-diff          # diff two text versions
python cli.py fill-spec-gaps          # AI fill empty spec fields
python cli.py validate                # NAFDAC checklist validation
python cli.py integration-test        # full pipeline check
python cli.py resolve-spec            # resolve drug spec
python cli.py pubchem-lookup          # PubChem data
python cli.py draw-structure          # 2D structure image