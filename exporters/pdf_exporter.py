"""
pdf_exporter.py — Step 4.4
Converts DOCX files to PDF using LibreOffice headless.

Modes:
  - Single:  convert one .docx file → .pdf in the same folder (or a custom output dir)
  - Batch:   walk an entire submission folder, convert every .docx found

Windows notes:
  - Tries the standard LibreOffice install paths automatically.
  - Set LIBREOFFICE_PATH env var to override if your install is non-standard.
  - Temp profile dirs are used so parallel conversions don't collide.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# ── LibreOffice discovery ─────────────────────────────────────────────────────

_DEFAULT_WINDOWS_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]

_DEFAULT_UNIX_PATHS = [
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def find_soffice() -> Optional[Path]:
    """Return path to soffice executable, or None if not found."""
    # 1. Explicit env override
    env_path = os.environ.get("LIBREOFFICE_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    # 2. Standard install locations
    candidates = _DEFAULT_WINDOWS_PATHS + _DEFAULT_UNIX_PATHS
    for p in candidates:
        if Path(p).is_file():
            return Path(p)

    # 3. On PATH
    found = shutil.which("soffice") or shutil.which("libreoffice")
    return Path(found) if found else None


# ── Core conversion ───────────────────────────────────────────────────────────

class PDFExportError(RuntimeError):
    pass


def convert_docx_to_pdf(
    docx_path: Path | str,
    output_dir: Optional[Path | str] = None,
    soffice: Optional[Path | str] = None,
    timeout: int = 120,
) -> Path:
    """
    Convert a single DOCX file to PDF.

    Args:
        docx_path:  Path to the .docx source file.
        output_dir: Directory for the resulting .pdf.
                    Defaults to the same directory as the .docx.
        soffice:    Explicit path to soffice/libreoffice executable.
                    Auto-detected if omitted.
        timeout:    Seconds to wait for LibreOffice before giving up.

    Returns:
        Path to the generated .pdf file.

    Raises:
        FileNotFoundError: If the .docx file doesn't exist.
        PDFExportError:    If LibreOffice is not found or conversion fails.
    """
    docx_path = Path(docx_path).resolve()
    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    # Resolve soffice
    exe = Path(soffice) if soffice else find_soffice()
    if exe is None:
        raise PDFExportError(
            "LibreOffice not found. Install it or set the LIBREOFFICE_PATH "
            "environment variable to the full path of soffice.exe."
        )

    # Output directory
    if output_dir is None:
        out_dir = docx_path.parent
    else:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Use a temp profile dir so multiple conversions can run simultaneously
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        cmd = [
            str(exe),
            "--headless",
            "--norestore",
            "--nofirststartwizard",
            f"-env:UserInstallation=file:///{Path(profile_dir).as_posix()}",
            "--convert-to", "pdf",
            "--outdir", str(out_dir),
            str(docx_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise PDFExportError(
                f"LibreOffice timed out after {timeout}s converting {docx_path.name}"
            )
        except FileNotFoundError:
            raise PDFExportError(
                f"Could not launch LibreOffice at: {exe}\n"
                "Check that it's installed and the path is correct."
            )

        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise PDFExportError(
                f"LibreOffice returned error {result.returncode} "
                f"for {docx_path.name}:\n{stderr}"
            )

    # Locate the output file (LibreOffice names it after the source)
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise PDFExportError(
            f"Conversion appeared to succeed but output not found: {pdf_path}"
        )

    return pdf_path


# ── Batch conversion ──────────────────────────────────────────────────────────

class BatchResult:
    """Summary of a batch PDF export run."""

    def __init__(self):
        self.converted: list[Path] = []
        self.failed: list[tuple[Path, str]] = []  # (docx_path, error_message)

    @property
    def total(self) -> int:
        return len(self.converted) + len(self.failed)

    @property
    def success_count(self) -> int:
        return len(self.converted)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    def __repr__(self) -> str:
        return (
            f"<BatchResult: {self.success_count}/{self.total} converted, "
            f"{self.failure_count} failed>"
        )


def convert_submission_to_pdf(
    submission_dir: Path | str,
    mirror_structure: bool = True,
    pdf_subdir: Optional[str] = "PDF",
    soffice: Optional[Path | str] = None,
    timeout: int = 120,
    skip_existing: bool = True,
) -> BatchResult:
    """
    Walk an entire submission folder and convert every .docx to .pdf.

    Args:
        submission_dir:   Root of the NAFDAC submission tree.
        mirror_structure: If True, PDFs go into <pdf_subdir>/<same relative path>.
                          If False, each PDF is placed next to its source .docx.
        pdf_subdir:       Name of the PDF mirror folder (only used when
                          mirror_structure=True). Set to None to place PDFs in
                          the submission root.
        soffice:          Path to soffice/libreoffice (auto-detected if omitted).
        timeout:          Per-file timeout in seconds.
        skip_existing:    Skip conversion if the target .pdf already exists.

    Returns:
        BatchResult with lists of converted paths and failures.
    """
    submission_dir = Path(submission_dir).resolve()
    if not submission_dir.is_dir():
        raise FileNotFoundError(f"Submission directory not found: {submission_dir}")

    # Resolve soffice once — fail fast if not available
    exe = Path(soffice) if soffice else find_soffice()
    if exe is None:
        raise PDFExportError(
            "LibreOffice not found. Install it or set LIBREOFFICE_PATH."
        )

    # Collect all .docx files (skip temp files Word leaves behind)
    docx_files = [
        p for p in submission_dir.rglob("*.docx")
        if not p.name.startswith("~$")
    ]

    result = BatchResult()

    for docx_path in sorted(docx_files):
        # Determine output directory
        if mirror_structure:
            rel = docx_path.parent.relative_to(submission_dir)
            if pdf_subdir:
                out_dir = submission_dir / pdf_subdir / rel
            else:
                out_dir = submission_dir / rel
        else:
            out_dir = docx_path.parent

        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / (docx_path.stem + ".pdf")

        if skip_existing and pdf_path.exists():
            result.converted.append(pdf_path)
            continue

        try:
            converted = convert_docx_to_pdf(
                docx_path, output_dir=out_dir, soffice=exe, timeout=timeout
            )
            result.converted.append(converted)
        except (PDFExportError, FileNotFoundError) as exc:
            result.failed.append((docx_path, str(exc)))

    return result


# ── Convenience helpers ───────────────────────────────────────────────────────

def libreoffice_version(soffice: Optional[Path | str] = None) -> Optional[str]:
    """Return LibreOffice version string, or None if not installed."""
    exe = Path(soffice) if soffice else find_soffice()
    if exe is None:
        return None
    try:
        r = subprocess.run(
            [str(exe), "--version"],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip() or r.stderr.strip()
    except Exception:
        return None