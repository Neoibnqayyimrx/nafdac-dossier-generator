[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are building a NAFDAC Nigeria pharmaceutical dossier generator in Python.
We are on Phase 1.

Here is what Phase 1 covers:
1.1 — Set up project folder structure, virtual environment, and install all dependencies
1.2 — Build the CLI skeleton using typer with these commands as stubs:
       ingest, new-drug, generate, validate, export-pdf, diff
1.3 — Design the drug_profile.yaml schema covering:
       drug name, strength, dosage form, therapeutic class, ATC code,
       manufacturer details, registration type, shelf life, storage,
       and file paths to supporting study documents
1.4 — Build a pydantic model that validates the drug_profile.yaml on load
       and gives clear error messages for missing required fields

Start with step 1.1. Show me the full folder structure we are creating,
then write the setup commands and code file by file.
After each step confirm with me before moving to the next.
At the end of the session give me an updated PROJECT_STATE.md block to copy.



[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are on Phase 2 of the NAFDAC dossier generator.

Phase 2 covers ingestion of my existing manually-written dossiers:
2.1 — Build docx_parser.py to extract text, tables, headings, and
       section structure from Word dossier files using python-docx
2.2 — Build pdf_parser.py to extract the same using pdfplumber,
       handling multi-column layouts and tables
2.3 — Build template_extractor.py that uses spaCy NER + regex to detect
       variable fields: drug name, manufacturer, strength, dates, batch numbers,
       dosage forms, storage conditions, shelf life, test limits
2.4 — Replace detected variables with Jinja2 placeholder syntax and
       generate .jinja2 template files per dossier section
2.5 — Save extracted templates into the templates/ folder organized
       by module (module1_admin, module2_quality, etc.)

I will provide sample dossier files as we go.
Start with step 2.1. Write complete working code.
Confirm with me after each step before proceeding.
At the end give me an updated PROJECT_STATE.md block to copy.



[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are on Phase 3 of the NAFDAC dossier generator.

Phase 3 covers building the pharmacopoeia reference database:
3.1 — Build pharmacopoeia_parser.py to parse BP and USP monograph PDFs.
       Extract: description, identification tests, assay limits,
       related substances, dissolution specs, storage, microbial limits.
       Handle varied PDF layouts across editions.
3.2 — Build a local JSON database under pharmacopoeia_db/BP/ and
       pharmacopoeia_db/USP/ with one structured JSON file per drug monograph.
       Include a CLI command: nafdac add-pharmacopoeia --source FILE --type BP|USP
3.3 — Build pubchem_api.py to query the PubChem REST API for:
       molecular weight, molecular formula, IUPAC name, SMILES, logP,
       melting point, solubility. Map results to our dossier fields.
3.4 — Build spec_resolver.py that applies priority logic when populating
       Module 3 quality sections:
       1st: existing dossier data, 2nd: BP, 3rd: USP, 4th: COA file, 5th: AI

Start with step 3.1. I will provide sample BP/USP monograph PDFs.
Write complete working code for each step.
Confirm with me after each step before proceeding.
At the end give me an updated PROJECT_STATE.md block to copy.



[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are on Phase 4 of the NAFDAC dossier generator.

Phase 4 covers building the actual dossier output engine:
4.1 — Build folder_builder.py that creates the NAFDAC submission folder
       hierarchy on disk following NAFDAC/WHO CTD structure:
       Module 1 (Administrative), Module 2 (Quality Overall Summary),
       Module 3 (Quality), Module 4 (Safety/Nonclinical),
       Module 5 (Efficacy/Clinical), plus PIL and SmPC as separate docs.
4.2 — Build docx_generator.py that renders each Jinja2 template with
       drug_profile.yaml data + pharmacopoeia DB data into polished .docx files.
       Handle: headings hierarchy, tables, headers/footers, page numbers,
       NAFDAC cover page format.
4.3 — Build a dedicated smpc_pil_generator.py for the Summary of Product
       Characteristics and Patient Information Leaflet since these have
       strict NAFDAC-required section ordering.
4.4 — Build pdf_exporter.py that calls LibreOffice headless to batch-convert
       all generated .docx files to PDF when the user runs:
       nafdac export-pdf --path ./submissions/drugname/

Start with step 4.1.
Write complete working code for each step.
Confirm with me after each step before proceeding.
At the end give me an updated PROJECT_STATE.md block to copy.



[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are on Phase 5 of the NAFDAC dossier generator.

Phase 5 covers web scraping and external data sources:
5.1 — Build nafdac_portal.py using requests + BeautifulSoup to:
       - Check if a drug name/strength is already registered with NAFDAC
       - Pull the registered product list for a given manufacturer
       - Check if a NAFDAC registration number is still valid
       Target: https://www.nafdac.gov.ng (public pages only)
5.2 — Build who_pq.py to query the WHO prequalification medicines list at
       https://extranet.who.int/pqweb to check if a product has WHO PQ status.
       Return PQ number, manufacturer, and assessment report link if available.
5.3 — Build drugbank_scraper.py to pull public drug data from DrugBank:
       mechanism of action, pharmacodynamics, pharmacokinetics (half life,
       protein binding, metabolism, route of elimination).
       This populates Module 4 and SmPC pharmacology sections.

Handle rate limiting, connection errors, and site structure changes gracefully.
Log all scraped data with timestamp to scraped_data/ for audit trail.
Start with step 5.1.
Write complete working code.
Confirm with me after each step.
At the end give me an updated PROJECT_STATE.md block to copy.



[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are on Phase 6 of the NAFDAC dossier generator.

Phase 6 covers the AI-powered narrative generation and tweaking:
6.1 — Build narrative_tweaker.py using the Anthropic SDK (claude-sonnet-4-20250514).
       It should accept an original narrative section text + new drug profile
       and return a rewritten version that:
       - Keeps identical regulatory tone and NAFDAC formatting style
       - Only changes what is scientifically necessary for the new drug
       - Preserves section structure and paragraph flow
       - Flags with [AI-REVIEW] any sentence it was uncertain about
6.2 — Build diff_viewer.py that runs in terminal and shows a clean side-by-side
       or inline diff between the original template narrative and the AI output
       so you can review every change before it goes into the final dossier.
       CLI: nafdac diff --original ./templates/module2/qos.jinja2
                        --generated ./submissions/metformin/module2/qos.docx
6.3 — Build spec_gap_filler.py where if pharmacopoeia DB and PubChem both
       return nothing for a required spec field, the AI is prompted to suggest
       a scientifically reasonable placeholder clearly marked [REQUIRES VERIFICATION]

Start with step 6.1.
Write complete working code.
Confirm with me after each step.
At the end give me an updated PROJECT_STATE.md block to copy.



[PASTE PROJECT_STATE.md CONTENT HERE]

---

We are on Phase 7 of the NAFDAC dossier generator — the final phase.

Phase 7 covers validation and full end-to-end integration:
7.1 — Build nafdac_checklist.py that validates a generated submission folder against
       the NAFDAC Guidelines for Registration of Medicines checklist:
       - All required modules present
       - SmPC and PIL present and complete
       - Cover forms (Form A/B/C) included
       - No [AI-REVIEW] or [REQUIRES VERIFICATION] flags remaining unresolved
       - All tables populated (no empty spec cells)
       - Manufacturer details consistent across all modules
7.2 — Build report_generator.py that outputs a terminal validation report:
       PASS / WARN / FAIL per section with specific guidance on what to fix
7.3 — Final end-to-end integration test:
       Run the full pipeline from scratch using a test drug profile,
       a sample existing dossier for ingestion, and a sample BP monograph.
       Verify the complete output folder is generated correctly.
       Fix any integration bugs across all phases.

After 7.3 is complete, help me write a clean README.md covering:
installation, setup, ingestion workflow, generation workflow,
pharmacopoeia database management, and CLI command reference.

Start with step 7.1.
Write complete working code.
Confirm with me after each step.
At the end give me a FINAL PROJECT_STATE.md marked as COMPLETE.


I am continuing a project we started in a previous session.
Here is the current project state:

[PASTE FULL PROJECT_STATE.md CONTENT]

Please confirm you understand the current phase and step,
then continue from where we left off.