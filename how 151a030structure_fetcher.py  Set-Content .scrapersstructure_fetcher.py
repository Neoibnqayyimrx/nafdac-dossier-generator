"""
structure_fetcher.py
====================
Fetches or generates 2D chemical structure images for the NAFDAC dossier.

Strategy (in priority order)
-----------------------------
1. PubChem PNG  — fetch pre-rendered 2D structure PNG using CID
2. RDKit        — generate 2D structure from SMILES string
3. None         — return None if both fail (dossier will note missing image)

Output
------
  pharmacopoeia_db/structures/<drug_stem>.png
  e.g. pharmacopoeia_db/structures/metformin-hydrochloride.png

Image spec
----------
  Format  : PNG, RGBA
  Size    : 300×300 px (PubChem default) or configurable for RDKit
  Use     : Embedded in Module 3 (Section 3.2.S.1.2 — Structure) DOCX

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

# ── Output directory ───────────────────────────────────────────────────────────
STRUCTURES_DIR = Path("pharmacopoeia_db") / "structures"

# ── PubChem image endpoint ─────────────────────────────────────────────────────
_PUBCHEM_IMG_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG"

# ── PubChem cache dir (to read CID/SMILES without re-querying) ────────────────
_PUBCHEM_CACHE_DIR = Path("pharmacopoeia_db") / "pubchem_cache"


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1: PUBCHEM PNG
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2: RDKIT FROM SMILES
# ═══════════════════════════════════════════════════════════════════════════════

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
        # Parse SMILES — handle salt forms (e.g. "CN(C)...N.Cl") by taking
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

        # Convert SVG → PNG using cairosvg if available, else use PIL+rdkit PNG
        png_bytes = _svg_to_png(svg_text, size)
        if png_bytes:
            log.info("RDKit SVG→PNG generated for '%s' (%d bytes)", drug_name, len(png_bytes))
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
    except Exceptio