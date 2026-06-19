"""
pharmacopoeia_db_builder.py
============================
Builds and manages the local JSON pharmacopoeia database for the
NAFDAC dossier generator.

Database layout
---------------
pharmacopoeia_db/
├── index.json                        ← master index of all parsed monographs
├── BP/
│   └── json/
│       ├── metformin-hydrochloride.json
│       ├── paracetamol.json
│       └── ...  (one per BP HTML file)
└── USP/
    └── json/
        ├── Metformin Hydrochloride.json
        ├── Acetaminophen.json
        └── ...  (one per USP PDF file)

index.json structure
--------------------
{
  "generated": "2026-05-24T10:00:00",
  "bp_count": 1825,
  "usp_count": 304,
  "entries": {
    "metformin hydrochloride": {
      "bp":  "pharmacopoeia_db/BP/json/metformin-hydrochloride.json",
      "usp": "pharmacopoeia_db/USP/json/Metformin Hydrochloride.json"
    },
    ...
  }
}

Usage (module)
--------------
  from pharmacopoeia_db_builder import build_db, add_single, lookup

  build_db(source="BP")          # parse all BP HTML files → JSON
  build_db(source="USP")         # parse all USP PDFs → JSON
  add_single("path/to/file.html", source="BP")   # add one file
  result = lookup("metformin hydrochloride")      # get paths from index

CLI (via cli.py)
----------------
  python cli.py build-pharmacopoeia-db --type BP
  python cli.py build-pharmacopoeia-db --type USP
  python cli.py build-pharmacopoeia-db --type ALL
  python cli.py add-pharmacopoeia --source FILE --type BP
  python cli.py add-pharmacopoeia --source FILE --type USP
  python cli.py lookup-pharmacopoeia metformin
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
DB_ROOT     = Path("pharmacopoeia_db")
BP_ROOT     = DB_ROOT / "BP"
USP_ROOT    = DB_ROOT / "USP"
BP_JSON_DIR = BP_ROOT / "json"
USP_JSON_DIR= USP_ROOT / "json"
INDEX_FILE  = DB_ROOT / "index.json"

# ── BP source location ────────────────────────────────────────────────────────
BP_MONOGRAPHS_DIR = BP_ROOT / "BP 2024" / "BP 2024 (EP 11.3)" / "monographs"

# ── USP source location (all A-Z letter folders) ──────────────────────────────
USP_SOURCE_ROOT = USP_ROOT / "USP 43-NF38" / "USP 43 A to Z"


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "bp_count":  0,
        "usp_count": 0,
        "entries":   {},
    }


def _save_index(index: dict) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    index["generated"] = datetime.now().isoformat(timespec="seconds")
    INDEX_FILE.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalise_name(name: str) -> str:
    """Lowercase + strip for consistent index keys."""
    return name.strip().lower()


def _update_index(index: dict, drug_name: str, source: str, json_path: Path) -> None:
    key = _normalise_name(drug_name)
    if key not in index["entries"]:
        index["entries"][key] = {}
    index["entries"][key][source.lower()] = str(json_path)


# ═══════════════════════════════════════════════════════════════════════════════
# JSON SAVE
# ═══════════════════════════════════════════════════════════════════════════════

def _save_monograph_json(result: dict, json_dir: Path, stem: str) -> Path:
    """Save a parsed monograph dict to <json_dir>/<stem>.json."""
    json_dir.mkdir(parents=True, exist_ok=True)
    out_path = json_dir / f"{stem}.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE FILE ADD
# ═══════════════════════════════════════════════════════════════════════════════

def add_single(
    file_path: str,
    source: str,
    verbose: bool = True,
) -> dict:
    """
    Parse one BP HTML or USP PDF file and add it to the JSON database.

    Parameters
    ----------
    file_path : str   Path to the .html (BP) or .pdf (USP) file.
    source    : str   "BP" or "USP".
    verbose   : bool  Print progress to stdout.

    Returns
    -------
    dict  The parsed monograph result.
    """
    from pharmacopoeia_parser import parse_monograph

    source = source.upper()
    path   = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if verbose:
        print(f"  Parsing {source}: {path.name}")

    result = parse_monograph(str(path), source=source)

    if "error" in result:
        if verbose:
            print(f"  ✗ Error: {result['error']}")
        return result

    drug_name = result.get("drug_name", path.stem)
    stem      = path.stem  # preserve original filename as JSON key

    json_dir  = BP_JSON_DIR if source == "BP" else USP_JSON_DIR
    json_path = _save_monograph_json(result, json_dir, stem)

    # Update index
    index = _load_index()
    _update_index(index, drug_name, source, json_path)
    count_key = "bp_count" if source == "BP" else "usp_count"
    index[count_key] = len([
        v for v in index["entries"].values()
        if source.lower() in v
    ])
    _save_index(index)

    if verbose:
        warnings = [w for w in result.get("parse_warnings", [])
                    if w.startswith("MISSING")]
        status = "⚠" if warnings else "✓"
        print(f"  {status} {drug_name} → {json_path.name}")
        for w in warnings:
            print(f"      {w}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# BULK BUILD
# ═══════════════════════════════════════════════════════════════════════════════

def _collect_bp_files() -> list[Path]:
    """Return all .html files from the BP monographs directory."""
    if not BP_MONOGRAPHS_DIR.exists():
        raise FileNotFoundError(
            f"BP monographs directory not found: {BP_MONOGRAPHS_DIR}\n"
            f"Expected: pharmacopoeia_db/BP/BP 2024/BP 2024 (EP 11.3)/monographs/"
        )
    files = sorted(BP_MONOGRAPHS_DIR.glob("*.html"))
    log.info("Found %d BP HTML files", len(files))
    return files


def _collect_usp_files() -> list[Path]:
    """Return all .pdf files from all USP A-Z letter folders."""
    if not USP_SOURCE_ROOT.exists():
        raise FileNotFoundError(
            f"USP source directory not found: {USP_SOURCE_ROOT}\n"
            f"Expected: pharmacopoeia_db/USP/USP 43-NF38/USP 43 A to Z/"
        )
    files = sorted(USP_SOURCE_ROOT.rglob("*.pdf"))
    log.info("Found %d USP PDF files", len(files))
    return files


def build_db(
    source: str = "BP",
    resume: bool = True,
    max_files: Optional[int] = None,
    show_progress: bool = True,
) -> dict:
    """
    Parse all BP or USP monograph files and build the JSON database.

    Parameters
    ----------
    source       : str   "BP", "USP", or "ALL".
    resume       : bool  Skip files whose JSON already exists (default True).
    max_files    : int   Limit number of files (useful for testing).
    show_progress: bool  Print a progress line per file.

    Returns
    -------
    dict  Summary statistics.
    """
    from pharmacopoeia_parser import parse_monograph

    sources = ["BP", "USP"] if source.upper() == "ALL" else [source.upper()]
    summary = {"processed": 0, "skipped": 0, "errors": 0, "warnings": 0}

    for src in sources:
        print(f"\n{'='*60}")
        print(f"  Building {src} pharmacopoeia database")
        print(f"{'='*60}")

        files    = _collect_bp_files() if src == "BP" else _collect_usp_files()
        json_dir = BP_JSON_DIR if src == "BP" else USP_JSON_DIR
        json_dir.mkdir(parents=True, exist_ok=True)

        if max_files:
            files = files[:max_files]

        total   = len(files)
        index   = _load_index()
        t_start = time.time()

        for i, fpath in enumerate(files, 1):
            stem      = fpath.stem
            json_path = json_dir / f"{stem}.json"

            # Resume: skip already-parsed files
            if resume and json_path.exists():
                summary["skipped"] += 1
                if show_progress:
                    print(f"  [{i:4d}/{total}] SKIP  {stem[:60]}")
                continue

            try:
                result = parse_monograph(str(fpath), source=src)
            except Exception as exc:
                summary["errors"] += 1
                print(f"  [{i:4d}/{total}] ERROR {stem[:55]} — {exc}")
                continue

            if "error" in result:
                summary["errors"] += 1
                print(f"  [{i:4d}/{total}] ERROR {stem[:50]} — {result['error'][:40]}")
                continue

            # Save JSON
            _save_monograph_json(result, json_dir, stem)

            # Update index
            drug_name = result.get("drug_name", stem)
            _update_index(index, drug_name, src, json_path)
            summary["processed"] += 1

            # Count MISSING warnings
            missing = [w for w in result.get("parse_warnings", [])
                       if w.startswith("MISSING")]
            if missing:
                summary["warnings"] += 1

            if show_progress:
                status = "⚠" if missing else "✓"
                elapsed = time.time() - t_start
                rate    = i / elapsed if elapsed > 0 else 0
                eta_s   = (total - i) / rate if rate > 0 else 0
                eta_str = _fmt_time(eta_s)
                print(
                    f"  [{i:4d}/{total}] {status} "
                    f"{drug_name[:45]:45s} "
                    f"[{rate:.1f}/s  ETA {eta_str}]"
                )

        # Save index after each source
        count_key = "bp_count" if src == "BP" else "usp_count"
        index[count_key] = len([v for v in index["entries"].values()
                                  if src.lower() in v])
        _save_index(index)

        elapsed_total = time.time() - t_start
        print(f"\n  ── {src} complete in {_fmt_time(elapsed_total)} ──")
        print(f"     Processed : {summary['processed']}")
        print(f"     Skipped   : {summary['skipped']}  (already in DB)")
        print(f"     Errors    : {summary['errors']}")
        print(f"     Warnings  : {summary['warnings']}  (MISSING fields)")
        print(f"     Index     : {INDEX_FILE}")

    return summary


def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


# ═══════════════════════════════════════════════════════════════════════════════
# LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════

def lookup(drug_name: str) -> dict:
    """
    Look up a drug in the index and return its JSON data.

    Parameters
    ----------
    drug_name : str   Drug name (case-insensitive, partial match supported).

    Returns
    -------
    dict with keys:
      "matches"  : list of matching index entries
      "bp_data"  : parsed BP JSON (or None)
      "usp_data" : parsed USP JSON (or None)
    """
    index   = _load_index()
    entries = index.get("entries", {})
    key     = _normalise_name(drug_name)

    # Exact match first
    matches = {}
    if key in entries:
        matches[key] = entries[key]
    else:
        # Partial match
        for k, v in entries.items():
            if key in k:
                matches[k] = v

    if not matches:
        return {"matches": [], "bp_data": None, "usp_data": None}

    # Load JSON data for the first (best) match
    best_key   = next(iter(matches))
    best_entry = matches[best_key]

    bp_data  = _load_json(best_entry.get("bp"))
    usp_data = _load_json(best_entry.get("usp"))

    return {
        "matches":  list(matches.keys()),
        "bp_data":  bp_data,
        "usp_data": usp_data,
    }


def _load_json(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        log.warning("JSON file not found: %s", path)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load %s: %s", path, exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# DB STATS
# ═══════════════════════════════════════════════════════════════════════════════

def db_stats() -> dict:
    """Return statistics about the current database."""
    index = _load_index()
    entries = index.get("entries", {})

    bp_only  = sum(1 for v in entries.values() if "bp" in v and "usp" not in v)
    usp_only = sum(1 for v in entries.values() if "usp" in v and "bp" not in v)
    both     = sum(1 for v in entries.values() if "bp" in v and "usp" in v)

    return {
        "total_drugs":  len(entries),
        "bp_count":     index.get("bp_count", 0),
        "usp_count":    index.get("usp_count", 0),
        "bp_only":      bp_only,
        "usp_only":     usp_only,
        "both_sources": both,
        "last_updated": index.get("generated"),
        "index_path":   str(INDEX_FILE),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REBUILD INDEX (repair tool)
# ═══════════════════════════════════════════════════════════════════════════════

def rebuild_index() -> None:
    """
    Rebuild index.json by scanning all existing JSON files.
    Use this if the index gets out of sync.
    """
    print("Rebuilding index from existing JSON files...")
    index = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "bp_count":  0,
        "usp_count": 0,
        "entries":   {},
    }

    for src, json_dir in [("bp", BP_JSON_DIR), ("usp", USP_JSON_DIR)]:
        if not json_dir.exists():
            continue
        files = list(json_dir.glob("*.json"))
        print(f"  Found {len(files)} {src.upper()} JSON files")
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                drug_name = data.get("drug_name", f.stem)
                _update_index(index, drug_name, src.upper(), f)
            except Exception as exc:
                print(f"  ✗ Skip {f.name}: {exc}")

    index["bp_count"]  = len([v for v in index["entries"].values() if "bp"  in v])
    index["usp_count"] = len([v for v in index["entries"].values() if "usp" in v])
    _save_index(index)
    print(f"  Index rebuilt: {len(index['entries'])} entries → {INDEX_FILE}")