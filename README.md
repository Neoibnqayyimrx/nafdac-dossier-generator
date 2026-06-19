# NAFDAC Dossier Generator

A command-line tool for generating complete pharmaceutical dossiers compliant with the **NAFDAC Nigeria CTD (Common Technical Document)** submission format. Built for pharmacists and regulatory affairs professionals who need to produce Module 3–5 dossier documents quickly and accurately.

---

## Features

- **Drug profile management** — define a drug once in YAML, generate everything from it
- **Pharmacopoeia integration** — parse British Pharmacopoeia (BP) HTML files and USP PDF monographs to auto-populate quality specifications
- **PubChem enrichment** — fetch chemical properties, molecular weight, SMILES, and 2D structure images automatically
- **Full CTD module generation** — produce Module 3 (Quality), Module 4 (Safety), and Module 5 (Efficacy) DOCX documents from Jinja2 templates
- **SmPC & PIL generation** — auto-generate Summary of Product Characteristics and Patient Information Leaflets
- **PDF export** — batch convert all DOCX files in a submission to PDF via LibreOffice headless
- **NAFDAC validation** — validate a submission against the full NAFDAC CTD checklist
- **External data scrapers** — query NAFDAC Greenbook, WHO Prequalification, OpenFDA, and DrugBank
- **AI narrative rewriting** — use the Anthropic API to refine dossier sections with context-aware edits
- **Dossier ingestion** — parse existing DOCX/PDF dossiers and extract reusable Jinja2 templates

---

## Project Structure

```
nafdac-dossier-gen/
├── cli.py                  # Main entry point
├── requirements.txt
├── setup.py
├── README.md
├── .gitignore
│
├── core/                   # Dossier generation engine
│   ├── pharmacopoeia_parser.py       # Parse BP HTML & USP PDF monographs
│   ├── pharmacopoeia_db_builder.py   # Build & query local pharmacopoeia DB
│   ├── module_generators.py          # Generate Module 3/4/5 DOCX files
│   ├── nafdac_structure.py           # CTD folder structure & manifest
│   ├── spec_resolver.py              # Resolve quality specifications
│   └── placeholder_generator.py     # Fill template placeholders
│
├── config/                 # Drug profiles & app config
│   ├── config_manager.py
│   ├── drug_profile.yaml             # Template drug profile
│   └── metformin.yaml                # Example: Metformin HCl profile
│
├── scrapers/               # External data sources
│   ├── pubchem_api.py                # PubChem REST API client
│   ├── web_scrapers.py               # NAFDAC, WHO, OpenFDA scrapers
│   ├── structure_fetcher.py          # 2D chemical structure images
│   ├── drugbank_scraper.py
│   ├── nafdac_portal.py
│   └── who_pq.py
│
├── ingestion/              # Parse existing dossiers
│   ├── docx_parser.py
│   ├── pdf_parser.py
│   └── template_extractor.py
│
├── exporters/              # Output generation
│   ├── pdf_exporter.py               # LibreOffice headless PDF export
│   ├── smpc_pil_generator.py         # SmPC & PIL documents
│   ├── docx_generator.py
│   └── folder_builder.py
│
├── validators/             # NAFDAC compliance checking
│   ├── nafdac_validator.py
│   ├── nafdac_checklist.py
│   └── report_generator.py
│
├── ai/                     # AI-assisted narrative generation
│   └── ai_narrative.py               # Anthropic API integration
│
├── models/                 # Data models
│   └── drug_profile_model.py         # Pydantic drug profile schema
│
├── templates/              # Jinja2 document templates
│   ├── module3_quality/
│   ├── module4_safety/
│   ├── module5_efficacy/
│   ├── module5_pil_smpc/
│   └── unclassified/
│
├── tests/
│   ├── test_pharmacopoeia_parser.py
│   ├── test_integration.py
│   └── make_test_dossier.py
│
└── pharmacopoeia_db/       # Local pharmacopoeia files (not in Git — see Setup)
    ├── BP/                           # British Pharmacopoeia HTML files (~2GB)
    └── USP/                          # USP PDF monographs (~2GB)
```

---

## Requirements

- Python 3.10+
- LibreOffice (for PDF export) — install and ensure `soffice` is on your PATH
- spaCy English model: `python -m spacy download en_core_web_sm`

### Python dependencies

```bash
pip install -r requirements.txt
```

Key packages: `typer`, `rich`, `python-docx`, `pdfplumber`, `Jinja2`, `PyYAML`, `pydantic`, `spacy`, `requests`, `beautifulsoup4`, `pandas`, `anthropic`, `rdkit`, `diff-match-patch`

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Neoibnqayyimrx/nafdac-dossier-generator.git
cd nafdac-dossier-generator
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 4. Add pharmacopoeia databases

The BP and USP source files are not included in this repository (too large). Place them as follows:

```
pharmacopoeia_db/
├── BP/      ← British Pharmacopoeia HTML files (from BP subscription)
└── USP/     ← USP-NF PDF monographs (from USP subscription)
```

Then build the local database:

```bash
python cli.py build-pharmacopoeia-db
```

---

## Usage

### Create a new drug profile

```bash
python cli.py new-drug
```

This walks you through an interactive prompt and saves a YAML profile to `config/`.

### Generate a complete dossier

```bash
python cli.py generate --drug metformin --profile config/metformin.yaml
```

### Look up a drug in the pharmacopoeia database

```bash
python cli.py lookup-pharmacopoeia --drug "Metformin Hydrochloride"
```

### Resolve Module 3 quality specifications

```bash
python cli.py resolve-spec --drug "Metformin Hydrochloride"
```

### Generate SmPC and PIL

```bash
python cli.py generate-smpc --submission submissions/metformin_hcl
python cli.py generate-pil  --submission submissions/metformin_hcl
```

### Export all DOCX files to PDF

```bash
python cli.py export-pdf-batch --submission submissions/metformin_hcl
```

### Validate a submission

```bash
python cli.py validate --submission submissions/metformin_hcl
```

### AI narrative rewrite

```bash
python cli.py tweak-narrative --file path/to/section.docx --mode improve
```

### Search NAFDAC Greenbook

```bash
python cli.py nafdac-search --drug "Metformin"
python cli.py nafdac-verify --nrn A4-0001
```

### PubChem enrichment

```bash
python cli.py pubchem-lookup --drug "Metformin Hydrochloride"
python cli.py pubchem-enrich-db
```

---

## CLI Commands Reference

| Phase | Command | Description |
|-------|---------|-------------|
| 1 | `new-drug` | Create a new drug profile YAML |
| 2 | `ingest` | Parse an existing dossier and extract templates |
| 3 | `add-pharmacopoeia` | Parse a single BP/USP file into the database |
| 3 | `build-pharmacopoeia-db` | Build the full local pharmacopoeia database |
| 3 | `lookup-pharmacopoeia` | Look up a drug monograph |
| 3 | `pharmacopoeia-stats` | Show database statistics |
| 3 | `pubchem-lookup` | Query PubChem for drug properties |
| 3 | `pubchem-enrich-db` | Enrich all BP monographs with PubChem data |
| 3 | `draw-structure` | Fetch a 2D chemical structure image |
| 3 | `resolve-spec` | Resolve all Module 3 quality fields |
| 4 | `new-submission` | Create the CTD folder structure |
| 4 | `generate` | Generate the complete dossier |
| 4 | `generate-modules` | Generate all Module DOCX files |
| 4 | `generate-smpc` | Generate the SmPC document |
| 4 | `generate-pil` | Generate the PIL document |
| 4 | `export-pdf` | Convert a single DOCX to PDF |
| 4 | `export-pdf-batch` | Convert all DOCX files in a submission to PDF |
| 5 | `nafdac-search` | Search the NAFDAC Greenbook |
| 5 | `nafdac-verify` | Verify a NAFDAC Registration Number |
| 5 | `who-prequal` | Check WHO Prequalification status |
| 5 | `drugbank-lookup` | Fetch drug data from OpenFDA |
| 5 | `fetch-external` | Run all external scrapers at once |
| 5 | `scraper-stats` | Show or clear scraper cache |
| 6 | `tweak-narrative` | AI-rewrite a dossier section |
| 6 | `narrative-diff` | Diff two dossier versions |
| 6 | `fill-spec-gaps` | AI-fill empty specification fields |
| 7 | `validate` | Validate against NAFDAC CTD checklist |
| 7 | `integration-test` | Run full end-to-end pipeline test |

---

## Supported Drugs (Current Templates)

- Amlodipine Besylate (BP & USP)
- Metformin Hydrochloride (BP)
- Glibenclamide (BP)
- Losartan Potassium
- Telmisartan

---

## Notes

- PDF export requires LibreOffice to be installed. On Windows, ensure `soffice.exe` is accessible on your system PATH.
- The AI narrative features require a valid `ANTHROPIC_API_KEY` in your `.env` file.
- The pharmacopoeia database files are large (~4GB total) and must be obtained separately through a BP or USP subscription.

---

## License

Private — internal use only. Not for public distribution.