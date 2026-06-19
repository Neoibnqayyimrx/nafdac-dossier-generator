"""
tests/test_pharmacopoeia_parser.py
===================================
Unit tests for the updated pharmacopoeia_parser.py.
  - BP  tests use synthetic HTML  (pharmacopoeia.com structure)
  - USP tests use synthetic text  (monkey-patched _extract_usp_text)

Run:
    python -m pytest tests/test_pharmacopoeia_parser.py -v
    # or directly:
    python tests/test_pharmacopoeia_parser.py
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import pharmacopoeia_parser as pp


# ═══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC CONTENT
# ═══════════════════════════════════════════════════════════════════════════════

# --- BP: minimal but realistic pharmacopoeia.com HTML for Aceclofenac ---------
BP_ACECLOFENAC_HTML = """<!DOCTYPE html>
<html>
<head><title>Aceclofenac - BP 2024</title></head>
<body>
<div class="version-title"><strong>Edition: BP 2024 (Ph. Eur. 11.3 update)</strong></div>
<article id="body">
<div id="publication-content">

<h1 class="euro">Aceclofenac</h1>

<div class="para_formula">C<sub>16</sub>H<sub>13</sub>Cl<sub>2</sub>NO<sub>4</sub>  354.2  89796-99-6</div>

<section class="section">
  <h2 class="mainheading">DEFINITION</h2>
  <p>[[[2-[(2,6-Dichlorophenyl)amino]phenyl]acetyl]oxy]acetic acid.</p>
  <div class="subsection">
    <h3 class="sub_general">Content</h3>
    <p>99.0 per cent to 101.0 per cent (dried substance).</p>
  </div>
</section>

<section class="section">
  <h2 class="mainheading">CHARACTERS</h2>
  <div class="subsection">
    <h3 class="sub_general">Appearance</h3>
    <p>White or almost white, crystalline powder.</p>
  </div>
  <div class="subsection">
    <h3 class="sub_general">Solubility</h3>
    <p>Practically insoluble in water, freely soluble in acetone.</p>
  </div>
</section>

<section class="section">
  <h2 class="mainheading">IDENTIFICATION</h2>
  <p><em>First identification: B</em>.</p>
  <div class="para_num1bottom">A. Ultraviolet and visible absorption spectrophotometry (2.2.25).
    Absorption maximum 275 nm.</div>
  <div class="para_num1">B. Infrared absorption spectrophotometry (2.2.24).
    Comparison: Ph. Eur. reference spectrum of aceclofenac.</div>
  <div class="para_num1">C. Chemical test. Dissolve in ethanol. A blue colour develops.</div>
</section>

<section class="section">
  <h2 class="mainheading">TESTS</h2>
  <div class="subsection">
    <h3 class="sub_general">Related substances</h3>
    <p>Liquid chromatography (2.2.29).</p>
    <p>Impurity A (diclofenac): not more than 0.3%.</p>
    <p>Any other impurity: not more than 0.1%.</p>
  </div>
  <div class="subsection">
    <h3 class="sub_general">Loss on drying</h3>
    <p>Not more than 0.5%, determined on 1.000 g by drying at 105 °C for 4 h.</p>
  </div>
</section>

<section class="section">
  <h2 class="mainheading">ASSAY</h2>
  <p>Liquid chromatography (2.2.29) as described in the test for related substances.</p>
  <p>Calculate the percentage content of C16H13Cl2NO4.</p>
  <p>Limits: 99.0 per cent to 101.0 per cent.</p>
</section>

<section class="section">
  <h2 class="mainheading">STORAGE</h2>
  <p>Protected from light, in an airtight container.</p>
</section>

<section class="section">
  <h2 class="mainheading">IMPURITIES</h2>
  <p>A. Diclofenac: limit 0.3%.</p>
  <p>B. Aceclofenac impurity B: limit 0.1%.</p>
</section>

</div>
</article>
</body>
</html>"""

# --- BP: with dissolution and microbial sections (for a tablet formulation) ---
BP_WITH_DISSOLUTION_HTML = """<!DOCTYPE html>
<html><body>
<div class="version-title"><strong>Edition: BP 2024</strong></div>
<article id="body"><div id="publication-content">
<h1 class="euro">Metformin Hydrochloride Tablets</h1>
<div class="para_formula">C<sub>4</sub>H<sub>11</sub>N<sub>5</sub>·HCl  165.6</div>

<section class="section">
  <h2 class="mainheading">DISSOLUTION</h2>
  <p>Apparatus 2, 50 rpm. Medium: 0.1 M hydrochloric acid; 900 mL.</p>
  <p>Time: 45 minutes. Limit: NLT 80% of the stated amount.</p>
</section>

<section class="section">
  <h2 class="mainheading">MICROBIAL CONTAMINATION</h2>
  <p>Total aerobic microbial count (TAMC): acceptance criterion 10^3 CFU/g (2.6.12).</p>
  <p>Total yeast/mould count (TYMC): acceptance criterion 10^2 CFU/g (2.6.12).</p>
  <p>Absence of Escherichia coli (2.6.13).</p>
  <p>Absence of Salmonella (2.6.13).</p>
</section>

<section class="section">
  <h2 class="mainheading">UNIFORMITY OF CONTENT</h2>
  <p>It complies with the test for uniformity of content (Ph. Eur. 2.9.6). Meets requirements.</p>
</section>

<section class="section">
  <h2 class="mainheading">WATER</h2>
  <p>Not more than 0.5%, determined by Karl Fischer titration.</p>
</section>

<section class="section">
  <h2 class="mainheading">STORAGE</h2>
  <p>Store below 30 °C, protected from moisture.</p>
</section>

<section class="section">
  <h2 class="mainheading">ASSAY</h2>
  <p>HPLC method. 98.5 per cent to 101.5 per cent.</p>
</section>

<section class="section">
  <h2 class="mainheading">DEFINITION</h2>
  <p>Contains not less than 98.5 per cent and not more than 101.5 per cent of
  metformin hydrochloride.</p>
</section>
</div></article></body></html>"""

# --- USP: synthetic plain text (returned by monkey-patched _extract_usp_text) -
USP_ACETAMINOPHEN_TEXT = """\
ACETAMINOPHEN
United States Pharmacopeia 2023

Definition. Acetaminophen contains NLT 98.0% and NMT 101.0% of C8H9NO2,
calculated on the dried basis.

Description. White or slightly pinkish crystalline powder.

Identification.
A. Infrared Absorption 197K.
B. Ultraviolet Absorption 197U, pH 6.0 phosphate buffer, maximum at 243 nm.

Assay. HPLC method. Mobile phase: acetonitrile and water. Limits: 98.0% to 101.0%.

Dissolution. Medium: water; 900 mL. Apparatus 2: 50 rpm. Time: 30 minutes.
Tolerances: NLT 80% (Q = 80%) of the labeled amount dissolved.

Uniformity of Dosage Units 905: meets requirements.

Water Determination. NMT 0.5%; Method: Karl Fischer titration.

Storage. Store at controlled room temperature.
"""

USP_METFORMIN_TEXT = """\
METFORMIN HYDROCHLORIDE
United States Pharmacopeia 2023

Definition. Metformin Hydrochloride contains NLT 98.5% and NMT 101.0%
of C4H11N5·HCl, calculated on the dried basis.

Identification.
A. Infrared Absorption 197K.
B. It meets the requirements of the test for Chloride.

Assay. Titration. 98.5% to 101.0%.

Loss on Drying. NMT 0.5%. Dry at 105 °C for 4 h.

Organic Impurities. HPLC.
Guanidine: NMT 0.02%.
Melamine: NMT 0.02%.
Any individual unspecified impurity: NMT 0.10%.

Storage. Store in tight containers.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

import tempfile, os

def _make_bp_html_file(html_content: str) -> str:
    """Write synthetic HTML to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    )
    f.write(html_content)
    f.close()
    return f.name


def _run_usp_parse(text: str) -> dict:
    """
    Monkey-patch _extract_usp_text so we can test the USP pipeline
    without a real PDF on disk.
    """
    original = pp._extract_usp_text
    pp._extract_usp_text = lambda path: (text, text.split("\f"))
    try:
        # USP parser reads from a file path — pass any string, patched fn ignores it
        result = pp._parse_usp_pdf("dummy_usp.pdf")
    finally:
        pp._extract_usp_text = original
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class TestBPHtmlParser(unittest.TestCase):
    """Tests for _parse_bp_html() — pharmacopoeia.com HTML structure."""

    def setUp(self):
        self.html_path = _make_bp_html_file(BP_ACECLOFENAC_HTML)
        self.result = pp._parse_bp_html(self.html_path)

    def tearDown(self):
        os.unlink(self.html_path)

    # ── Meta fields ────────────────────────────────────────────────────────────
    def test_drug_name(self):
        self.assertIn("Aceclofenac", self.result["drug_name"])

    def test_source_tag(self):
        self.assertEqual(self.result["source"], "BP")

    def test_edition_extracted(self):
        self.assertIsNotNone(self.result["edition"])
        self.assertIn("2024", self.result["edition"])

    def test_molecular_formula(self):
        f = self.result["molecular_formula"]
        self.assertIsNotNone(f)
        self.assertIn("C16", f)
        self.assertIn("Cl2", f)

    # ── Description ────────────────────────────────────────────────────────────
    def test_description_extracted(self):
        desc = self.result["description"]
        self.assertIsNotNone(desc)
        self.assertIn("white", desc.lower())

    # ── Identification ─────────────────────────────────────────────────────────
    def test_identification_is_list(self):
        self.assertIsInstance(self.result["identification"], list)

    def test_identification_count(self):
        # A, B, C → 3 tests
        self.assertEqual(len(self.result["identification"]), 3)

    def test_identification_ir_detected(self):
        methods = [i["method"] for i in self.result["identification"]]
        self.assertTrue(any("IR" in m or "Infrared" in m for m in methods),
                        f"Expected IR method in {methods}")

    def test_identification_uv_detected(self):
        methods = [i["method"] for i in self.result["identification"]]
        self.assertTrue(any("UV" in m or "Ultraviolet" in m for m in methods),
                        f"Expected UV method in {methods}")

    def test_identification_chemical_detected(self):
        methods = [i["method"] for i in self.result["identification"]]
        self.assertTrue(any("Chemical" in m for m in methods),
                        f"Expected Chemical test in {methods}")

    # ── Assay ──────────────────────────────────────────────────────────────────
    def test_assay_limits_extracted(self):
        assay = self.result["assay"]
        self.assertIsNotNone(assay["limits"], "Expected assay limits")
        self.assertEqual(assay["limits"]["min"], 99.0)
        self.assertEqual(assay["limits"]["max"], 101.0)

    def test_assay_method_hplc(self):
        self.assertIn("HPLC", self.result["assay"]["method"])

    # ── Related substances ─────────────────────────────────────────────────────
    def test_related_substances_is_list(self):
        self.assertIsInstance(self.result["related_substances"], list)

    def test_related_substances_not_empty(self):
        self.assertGreater(len(self.result["related_substances"]), 0)

    def test_related_substances_has_limits(self):
        limits = [r["limit"] for r in self.result["related_substances"] if r["limit"] is not None]
        self.assertGreater(len(limits), 0, "Expected at least one numeric limit")

    # ── Loss on drying ─────────────────────────────────────────────────────────
    def test_loss_on_drying_extracted(self):
        lod = self.result["loss_on_drying"]
        self.assertIsNotNone(lod)
        self.assertEqual(lod["limit_pct"], 0.5)
        self.assertEqual(lod["temperature_c"], 105)

    # ── Storage ────────────────────────────────────────────────────────────────
    def test_storage_extracted(self):
        storage = self.result["storage"]
        self.assertIsNotNone(storage)
        self.assertIn("airtight", storage.lower())

    # ── Impurities section ─────────────────────────────────────────────────────
    def test_impurities_extracted(self):
        self.assertIsInstance(self.result["impurities"], list)
        self.assertGreater(len(self.result["impurities"]), 0)

    # ── Raw sections ───────────────────────────────────────────────────────────
    def test_raw_sections_contains_definition(self):
        self.assertIn("DEFINITION", self.result["raw_sections"])

    def test_raw_sections_contains_assay(self):
        self.assertIn("ASSAY", self.result["raw_sections"])

    # ── JSON serializable ──────────────────────────────────────────────────────
    def test_result_json_serializable(self):
        try:
            json.dumps(self.result)
        except TypeError as e:
            self.fail(f"Result not JSON-serializable: {e}")

    # ── parse_warnings ─────────────────────────────────────────────────────────
    def test_parse_warnings_is_list(self):
        self.assertIsInstance(self.result["parse_warnings"], list)


class TestBPHtmlParserDissolution(unittest.TestCase):
    """Tests dissolution, microbial, water, uniformity using second BP HTML."""

    def setUp(self):
        self.html_path = _make_bp_html_file(BP_WITH_DISSOLUTION_HTML)
        self.result = pp._parse_bp_html(self.html_path)

    def tearDown(self):
        os.unlink(self.html_path)

    def test_drug_name_tablets(self):
        self.assertIn("Metformin", self.result["drug_name"])

    def test_dissolution_apparatus(self):
        diss = self.result["dissolution"]
        self.assertIsNotNone(diss["apparatus"])
        self.assertIn("2", diss["apparatus"])

    def test_dissolution_rpm(self):
        self.assertEqual(self.result["dissolution"]["rpm"], 50)

    def test_dissolution_time(self):
        self.assertEqual(self.result["dissolution"]["time_min"], 45)

    def test_dissolution_limit(self):
        self.assertEqual(self.result["dissolution"]["limit_pct"], 80)

    def test_microbial_tamc(self):
        mic = self.result["microbial_limits"]
        self.assertIsNotNone(mic["TAMC"])
        self.assertIn("CFU", mic["TAMC"])

    def test_microbial_tymc(self):
        mic = self.result["microbial_limits"]
        self.assertIsNotNone(mic["TYMC"])

    def test_microbial_pathogens(self):
        pathogens = self.result["microbial_limits"]["pathogens"]
        self.assertIn("Escherichia coli", pathogens)
        self.assertIn("Salmonella", pathogens)

    def test_uniformity_extracted(self):
        uni = self.result["uniformity"]
        self.assertIsNotNone(uni)
        self.assertIn("Meets requirements", uni["criterion"])

    def test_water_content_extracted(self):
        water = self.result["water_content"]
        self.assertIsNotNone(water)
        self.assertEqual(water["limit_pct"], 0.5)
        self.assertEqual(water["method"], "Karl Fischer titration")

    def test_assay_limits_from_definition(self):
        # Assay limits should fall back to DEFINITION section
        assay = self.result["assay"]
        self.assertIsNotNone(assay["limits"])
        self.assertEqual(assay["limits"]["min"], 98.5)
        self.assertEqual(assay["limits"]["max"], 101.5)

    def test_storage_extracted(self):
        self.assertIsNotNone(self.result["storage"])
        self.assertIn("30", self.result["storage"])


class TestUSPPdfParser(unittest.TestCase):
    """Tests for _parse_usp_pdf() using monkey-patched text extraction."""

    def setUp(self):
        self.acetaminophen = _run_usp_parse(USP_ACETAMINOPHEN_TEXT)
        self.metformin     = _run_usp_parse(USP_METFORMIN_TEXT)

    # ── Meta ───────────────────────────────────────────────────────────────────
    def test_source_tag(self):
        self.assertEqual(self.acetaminophen["source"], "USP")
        self.assertEqual(self.metformin["source"], "USP")

    def test_drug_name_acetaminophen(self):
        self.assertIn("Acetaminophen", self.acetaminophen["drug_name"])

    def test_drug_name_metformin(self):
        self.assertIn("Metformin", self.metformin["drug_name"])

    # ── Assay ──────────────────────────────────────────────────────────────────
    def test_acetaminophen_assay_limits(self):
        assay = self.acetaminophen["assay"]
        self.assertIsNotNone(assay["limits"])
        self.assertEqual(assay["limits"]["min"], 98.0)
        self.assertEqual(assay["limits"]["max"], 101.0)

    def test_acetaminophen_assay_method_hplc(self):
        self.assertIn("HPLC", self.acetaminophen["assay"]["method"])

    def test_metformin_assay_limits(self):
        assay = self.metformin["assay"]
        self.assertIsNotNone(assay["limits"])
        self.assertEqual(assay["limits"]["min"], 98.5)
        self.assertEqual(assay["limits"]["max"], 101.0)

    # ── Identification ─────────────────────────────────────────────────────────
    def test_identification_list(self):
        self.assertIsInstance(self.acetaminophen["identification"], list)
        self.assertGreater(len(self.acetaminophen["identification"]), 0)

    def test_identification_ir(self):
        methods = [i["method"] for i in self.acetaminophen["identification"]]
        self.assertTrue(any("IR" in m or "Infrared" in m for m in methods))

    # ── Dissolution ────────────────────────────────────────────────────────────
    def test_dissolution_apparatus(self):
        diss = self.acetaminophen["dissolution"]
        self.assertIsNotNone(diss["apparatus"])
        self.assertIn("2", diss["apparatus"])

    def test_dissolution_rpm(self):
        self.assertEqual(self.acetaminophen["dissolution"]["rpm"], 50)

    def test_dissolution_time(self):
        self.assertEqual(self.acetaminophen["dissolution"]["time_min"], 30)

    def test_dissolution_limit(self):
        self.assertEqual(self.acetaminophen["dissolution"]["limit_pct"], 80)

    # ── Storage ────────────────────────────────────────────────────────────────
    def test_acetaminophen_storage(self):
        self.assertIsNotNone(self.acetaminophen["storage"])

    def test_metformin_storage(self):
        self.assertIsNotNone(self.metformin["storage"])
        self.assertIn("tight", self.metformin["storage"].lower())

    # ── Water content ──────────────────────────────────────────────────────────
    def test_water_content(self):
        water = self.acetaminophen["water_content"]
        self.assertIsNotNone(water)
        self.assertEqual(water["limit_pct"], 0.5)
        self.assertEqual(water["method"], "Karl Fischer titration")

    # ── Loss on drying ─────────────────────────────────────────────────────────
    def test_loss_on_drying_metformin(self):
        lod = self.metformin["loss_on_drying"]
        self.assertIsNotNone(lod)
        self.assertEqual(lod["limit_pct"], 0.5)
        self.assertEqual(lod["temperature_c"], 105)

    # ── Uniformity ─────────────────────────────────────────────────────────────
    def test_uniformity(self):
        uni = self.acetaminophen["uniformity"]
        self.assertIsNotNone(uni)
        self.assertIn("Meets requirements", uni["criterion"])

    # ── Related substances ─────────────────────────────────────────────────────
    def test_related_substances_metformin(self):
        rs = self.metformin["related_substances"]
        self.assertIsInstance(rs, list)
        self.assertGreater(len(rs), 0)

    # ── JSON serializable ──────────────────────────────────────────────────────
    def test_acetaminophen_json_serializable(self):
        try:
            json.dumps(self.acetaminophen)
        except TypeError as e:
            self.fail(f"Result not JSON-serializable: {e}")

    def test_metformin_json_serializable(self):
        try:
            json.dumps(self.metformin)
        except TypeError as e:
            self.fail(f"Result not JSON-serializable: {e}")


class TestPublicAPI(unittest.TestCase):
    """Tests for the public parse_monograph() router."""

    def test_invalid_source_raises(self):
        with self.assertRaises(ValueError):
            pp.parse_monograph("any.html", source="EP")

    def test_missing_file_returns_error(self):
        result = pp.parse_monograph("nonexistent.html", source="BP")
        self.assertIn("error", result)

    def test_bp_routes_to_html_parser(self):
        html_path = _make_bp_html_file(BP_ACECLOFENAC_HTML)
        try:
            result = pp.parse_monograph(html_path, source="BP")
            self.assertEqual(result["source"], "BP")
            self.assertNotIn("error", result)
        finally:
            os.unlink(html_path)

    def test_usp_routes_to_pdf_parser(self):
        # Patch _extract_usp_text so no real PDF is needed
        original = pp._extract_usp_text
        pp._extract_usp_text = lambda path: (USP_ACETAMINOPHEN_TEXT, [USP_ACETAMINOPHEN_TEXT])
        try:
            result = pp.parse_monograph("dummy.pdf", source="USP")
            self.assertEqual(result["source"], "USP")
        finally:
            pp._extract_usp_text = original


class TestValidateResult(unittest.TestCase):
    """Tests for validate_result() — used by spec_resolver in step 3.4."""

    def _make_complete(self):
        html_path = _make_bp_html_file(BP_ACECLOFENAC_HTML)
        result = pp._parse_bp_html(html_path)
        os.unlink(html_path)
        return result

    def test_complete_result_has_no_issues(self):
        result = self._make_complete()
        issues = pp.validate_result(result)
        # Description, identification, storage all present; assay limits present
        storage_issues = [i for i in issues if "storage" in i.lower()]
        assay_issues   = [i for i in issues if "assay" in i.lower()]
        self.assertEqual(len(storage_issues), 0)
        self.assertEqual(len(assay_issues), 0)

    def test_empty_result_has_issues(self):
        issues = pp.validate_result({})
        self.assertGreater(len(issues), 0)

    def test_missing_assay_limits_flagged(self):
        result = {"description": "White powder", "identification": [{"test": "A"}],
                  "storage": "Cool place", "assay": {"limits": None, "method": None}}
        issues = pp.validate_result(result)
        self.assertTrue(any("assay" in i.lower() for i in issues))


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
 
