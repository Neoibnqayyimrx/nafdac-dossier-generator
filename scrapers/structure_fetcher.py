"""
structure_fetcher.py
====================
Fetches or generates 2D chemical structure images for the NAFDAC dossier.

Strategy (in priority order)
-----------------------------
1. PubChem PNG  ΓÇö fetch pre-rendered 2D structure PNG using CID
2. RDKit        ΓÇö generate 2D structure from SMILES string
3. None         ΓÇö return None if both fail (dossier will note missing image)

Output
------
  pharmacopoeia_db/structures/<drug_stem>.png
  e.g. pharmacopoeia_db/structures/metformin-hydrochloride.png

Image spec
----------
  Format  : PNG, RGBA
  Size    : 300├ù300 px (PubChem default) or configurable for RDKit
  Use     : Embedded in Module 3 (Section 3.2.S.1.2 ΓÇö Structure) DOCX

Usage
-----
  from structure_fetcher import fetch_structure, get_structure_path

  # Fetch by drug name (uses pubchem_cache to get CID and SMILES)
  path = fetch_structure("metformin hydrochloride")

  # Fetch with explicit CID and SMILES
  path = fetch_structure(
      drug_name="metformin hydrochloride",
      cid=14219,
      smiles="CN(C)C(=N)N=C(N)N.Cl",
  )

CLI (via cli.py)
----------------
  python cli.py draw-structure metformin
  python cli.py draw-structure paracetamol --size 400
  python cli.py draw-structure "metformin hydrochloride" --show
"""

from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ΓöÇΓöÇ Output directory ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
STRUCTURES_DIR = Path("pharmacopoeia_db") / "structures"

# ΓöÇΓöÇ PubChem image endpoint ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
_PUBCHEM_IMG_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG"

# ΓöÇΓöÇ PubChem cache dir (to read CID/SMILES without re-querying) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
_PUBCHEM_CACHE_DIR = Path("pharmacopoeia_db") / "pubchem_cache"


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# HELPERS
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def _normalise_stem(drug_name: str) -> str:
    """Convert drug name to a safe filename stem."""
    stem = drug_name.lower().strip()
    stem = re.sub(r"[^a-z0-9]+", "-", stem)
    return stem.strip("-")


def _load_pubchem_cache(drug_name: str) -> Optional[dict]:
    """Load cached PubChem data for a drug."""
    key  = re.sub(r"[^a-z0-9]+", "_", drug_name.lower().strip()).strip("_")
    path = _PUBCHEM_CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def get_structure_path(drug_name: str) -> Path:
    """Return the expected output path for a drug's structure image."""
    return STRUCTURES_DIR / f"{_normalise_stem(drug_name)}.png"


def structure_exists(drug_name: str) -> bool:
    """Check if a structure image already exists on disk."""
    return get_structure_path(drug_name).exists()


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# SOURCE 1: PUBCHEM PNG
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def _fetch_pubchem_png(cid: int, size: int = 300) -> Optional[bytes]:
    """
    Download a 2D structure PNG from PubChem for a given CID.
    Returns raw PNG bytes or None on failure.
    """
    url = _PUBCHEM_IMG_URL.format(cid=cid)
    params = {"image_size": f"{size}x{size}"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200 and resp.content:
            # Verify it's actually a PNG (magic bytes: \x89PNG)
            if resp.content[:4] == b'\x89PNG':
                log.info("PubChem PNG fetched for CID %d (%d bytes)", cid, len(resp.content))
                return resp.content
    except requests.exceptions.RequestException as exc:
        log.warning("PubChem PNG fetch failed for CID %d: %s", cid, exc)
    return None


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# SOURCE 2: RDKIT FROM SMILES
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def _generate_rdkit_png(smiles: str, size: int = 300, drug_name: str = "") -> Optional[bytes]:
    """
    Generate a 2D structure PNG from a SMILES string using RDKit.
    Returns raw PNG bytes or None on failure.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw, AllChem
        from rdkit.Chem.Draw import rdMolDraw2D
    except ImportError:
        log.warning("RDKit not available. Install with: conda install -c conda-forge rdkit")
        return None

    try:
        # Parse SMILES ΓÇö handle salt forms (e.g. "CN(C)...N.Cl") by taking
        # the largest fragment
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            # Try sanitizing more aggressively
            mol = Chem.MolFromSmiles(smiles, sanitize=False)
            if mol:
                Chem.SanitizeMol(mol, catchErrors=True)

        if mol is None:
            log.warning("RDKit: could not parse SMILES: %s", smiles[:60])
            return None

        # For salt forms, take the largest fragment
        frags = Chem.GetMolFrags(mol, asMols=True)
        if len(frags) > 1:
            mol = max(frags, key=lambda m: m.GetNumAtoms())

        # Generate 2D coordinates
        AllChem.Compute2DCoords(mol)

        # Render to PNG using the high-quality drawer
        drawer = rdMolDraw2D.MolDraw2DSVG(size, size)
        drawer.drawOptions().addAtomIndices = False
        drawer.drawOptions().addStereoAnnotation = True
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        svg_text = drawer.GetDrawingText()

        # Convert SVG ΓåÆ PNG using cairosvg if available, else use PIL+rdkit PNG
        png_bytes = _svg_to_png(svg_text, size)
        if png_bytes:
            log.info("RDKit SVGΓåÆPNG generated for '%s' (%d bytes)", drug_name, len(png_bytes))
            return png_bytes

        # Fallback: direct PNG drawer
        png_drawer = rdMolDraw2D.MolDraw2DCairo(size, size)
        png_drawer.DrawMolecule(mol)
        png_drawer.FinishDrawing()
        png_bytes = png_drawer.GetDrawingText()
        if png_bytes:
            log.info("RDKit Cairo PNG generated for '%s' (%d bytes)", drug_name, len(png_bytes))
            return png_bytes

    except Exception as exc:
        log.warning("RDKit generation failed for '%s': %s", drug_name, exc)

    return None


def _svg_to_png(svg_text: str, size: int) -> Optional[bytes]:
    """Convert SVG string to PNG bytes. Tries cairosvg first, then svglib."""
    # Method 1: cairosvg
    try:
        import cairosvg
        png = cairosvg.svg2png(
            bytestring=svg_text.encode("utf-8"),
            output_width=size, output_height=size,
        )
        return png
    except ImportError:
        pass
    except Exception as exc:
        log.debug("cairosvg failed: %s", exc)

    # Method 2: svglib + reportlab
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="w") as f:
            f.write(svg_text)
            svg_path = f.name
        try:
            drawing = svg2rlg(svg_path)
            if drawing:
                buf = io.BytesIO()
                renderPM.drawToFile(drawing, buf, fmt="PNG")
                return buf.getvalue()
        finally:
            os.unlink(svg_path)
    except ImportError:
        pass
    except Exception as exc:
        log.debug("svglib failed: %s", exc)

    return None


def _generate_rdkit_png_direct(smiles: str, size: int = 300, drug_name: str = "") -> Optional[bytes]:
    """
    Direct RDKit PNG generation without SVG intermediate.
    Uses MolDraw2DCairo for highest quality output.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        # Take largest fragment for salts
        frags = Chem.GetMolFrags(mol, asMols=True)
        if len(frags) > 1:
            mol = max(frags, key=lambda m: m.GetNumAtoms())

        AllChem.Compute2DCoords(mol)

        # Try Cairo renderer (highest quality)
        try:
            drawer = rdMolDraw2D.MolDraw2DCairo(size, size)
            drawer.drawOptions().addStereoAnnotation = True
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()
            png_bytes = drawer.GetDrawingText()
            if png_bytes and len(png_bytes) > 100:
                return png_bytes
        except Exception:
            pass

        # Fallback: use Draw.MolToImage (PIL-based)
        from rdkit.Chem import Draw
        img = Draw.MolToImage(mol, size=(size, size))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as exc:
        log.warning("RDKit direct PNG failed for '%s': %s", drug_name, exc)
        return None


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# MASTER FETCH FUNCTION
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def fetch_structure(
    drug_name: str,
    cid: Optional[int] = None,
    smiles: Optional[str] = None,
    size: int = 300,
    overwrite: bool = False,
    source_preference: str = "pubchem",
) -> Optional[Path]:
    """
    Fetch or generate a 2D structure image for a drug.

    Priority:
      1. PubChem PNG (using CID)
      2. RDKit from SMILES
      3. None

    Parameters
    ----------
    drug_name         : str   Drug name (used for filename and cache lookup).
    cid               : int   PubChem CID (auto-loaded from cache if None).
    smiles            : str   SMILES string (auto-loaded from cache if None).
    size              : int   Image size in pixels (default 300).
    overwrite         : bool  Re-fetch even if image already exists.
    source_preference : str   "pubchem" (default) or "rdkit".

    Returns
    -------
    Path to the saved PNG file, or None if both sources failed.
    """
    out_path = get_structure_path(drug_name)

    # Return existing image unless overwrite requested
    if not overwrite and out_path.exists():
        log.info("Structure image already exists: %s", out_path)
        return out_path

    # Auto-load CID and SMILES from PubChem cache if not provided
    if cid is None or smiles is None:
        cached = _load_pubchem_cache(drug_name)
        if cached:
            cid    = cid    or cached.get("cid")
            smiles = smiles or cached.get("smiles")

    STRUCTURES_DIR.mkdir(parents=True, exist_ok=True)
    png_bytes: Optional[bytes] = None
    source_used = None

    if source_preference == "pubchem" and cid:
        # Try PubChem first
        png_bytes = _fetch_pubchem_png(cid, size=size)
        if png_bytes:
            source_used = "PubChem PNG"

    if not png_bytes and smiles:
        # Try RDKit
        png_bytes = _generate_rdkit_png_direct(smiles, size=size, drug_name=drug_name)
        if not png_bytes:
            png_bytes = _generate_rdkit_png(smiles, size=size, drug_name=drug_name)
        if png_bytes:
            source_used = "RDKit"

    if source_preference == "rdkit" and not png_bytes and cid:
        # rdkit preference but failed ΓÇö try PubChem as fallback
        png_bytes = _fetch_pubchem_png(cid, size=size)
        if png_bytes:
            source_used = "PubChem PNG (fallback)"

    if not png_bytes:
        log.warning("No structure image available for '%s'", drug_name)
        return None

    # Save PNG
    out_path.write_bytes(png_bytes)
    log.info("Structure saved: %s (source: %s)", out_path, source_used)
    return out_path


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# BATCH FETCH
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def fetch_all_structures(
    max_drugs: Optional[int] = None,
    overwrite: bool = False,
    size: int = 300,
) -> dict:
    """
    Fetch structure images for all drugs that have PubChem data cached.

    Returns
    -------
    dict  Summary: {fetched, skipped, failed}
    """
    if not _PUBCHEM_CACHE_DIR.exists():
        raise FileNotFoundError(
            "PubChem cache not found. Run: python cli.py pubchem-enrich-db"
        )

    cache_files = sorted(_PUBCHEM_CACHE_DIR.glob("*.json"))
    if max_drugs:
        cache_files = cache_files[:max_drugs]

    summary = {"fetched": 0, "skipped": 0, "failed": 0}
    total   = len(cache_files)

    print(f"\n{'='*60}")
    print(f"  Fetching structure images for {total} drugs")
    print(f"{'='*60}")

    for i, cache_file in enumerate(cache_files, 1):
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            summary["failed"] += 1
            continue

        if data.get("query_status") != "found":
            summary["skipped"] += 1
            continue

        drug_name = data.get("drug_name", cache_file.stem)
        cid       = data.get("cid")
        smiles    = data.get("smiles")

        if not overwrite and structure_exists(drug_name):
            summary["skipped"] += 1
            print(f"  [{i:4d}/{total}] SKIP  {drug_name[:50]}")
            continue

        path = fetch_structure(
            drug_name, cid=cid, smiles=smiles,
            size=size, overwrite=overwrite,
        )
        if path:
            summary["fetched"] += 1
            src = "PubChem" if cid else "RDKit"
            print(f"  [{i:4d}/{total}] Γ£ô  {drug_name[:45]:45s} [{src}]")
        else:
            summary["failed"] += 1
            print(f"  [{i:4d}/{total}] Γ£ù  {drug_name[:50]}")

    print(f"\n  ΓöÇΓöÇ Complete ΓöÇΓöÇ")
    print(f"     Fetched : {summary['fetched']}")
    print(f"     Skipped : {summary['skipped']}")
    print(f"     Failed  : {summary['failed']}")
    return summary


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# STANDALONE TEST
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    drug   = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "metformin hydrochloride"
    print(f"\nFetching structure for: {drug}")

    path = fetch_structure(drug, overwrite=True)
    if path:
        print(f"Γ£ô Saved: {path}")
        print(f"  Size : {path.stat().st_size:,} bytes")
    else:
        print("Γ£ù Failed to fetch structure image")
