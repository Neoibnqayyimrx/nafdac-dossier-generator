"""
cli_pharmacopoeia_additions.py
================================
Paste these 4 commands into your existing cli.py.

STEP 1 — Add this import near the top of cli.py (with other imports):
─────────────────────────────────────────────────────────────────────
from pharmacopoeia_db_builder import (
    build_db, add_single, lookup, db_stats, rebuild_index
)

STEP 2 — Paste the 4 commands below into cli.py (after existing commands).
"""

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from typing import Optional

# NOTE: 'app' already exists in your cli.py — do NOT redeclare it.
# These functions use the same 'app' object you already have.

console = Console()


# ── Command 1: build-pharmacopoeia-db ─────────────────────────────────────────

@app.command("build-pharmacopoeia-db")
def build_pharmacopoeia_db(
    type: str = typer.Option(
        "BP",
        "--type", "-t",
        help="Source to build: BP, USP, or ALL",
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Skip files already in the database (default: True)",
    ),
    max_files: Optional[int] = typer.Option(
        None,
        "--max-files",
        help="Limit number of files (useful for testing, e.g. --max-files 10)",
    ),
):
    """
    Parse all BP HTML or USP PDF monographs and build the local JSON database.

    Examples:
      python cli.py build-pharmacopoeia-db --type BP
      python cli.py build-pharmacopoeia-db --type USP
      python cli.py build-pharmacopoeia-db --type ALL
      python cli.py build-pharmacopoeia-db --type BP --max-files 10
      python cli.py build-pharmacopoeia-db --type BP --no-resume
    """
    valid = {"BP", "USP", "ALL"}
    if type.upper() not in valid:
        rprint(f"[red]ERROR: --type must be one of: {', '.join(valid)}[/red]")
        raise typer.Exit(1)

    rprint(f"[bold cyan]Building {type.upper()} pharmacopoeia database...[/bold cyan]")
    if max_files:
        rprint(f"[yellow]Test mode: limiting to {max_files} files[/yellow]")
    if not resume:
        rprint("[yellow]--no-resume: all files will be re-parsed[/yellow]")

    summary = build_db(
        source=type.upper(),
        resume=resume,
        max_files=max_files,
        show_progress=True,
    )

    rprint("\n[bold green]✓ Database build complete[/bold green]")
    rprint(f"  Processed : [green]{summary['processed']}[/green]")
    rprint(f"  Skipped   : [dim]{summary['skipped']}[/dim]  (already in DB)")
    rprint(f"  Errors    : [red]{summary['errors']}[/red]")
    rprint(f"  Warnings  : [yellow]{summary['warnings']}[/yellow]  (missing fields, filled by PubChem)")


# ── Command 2: add-pharmacopoeia ───────────────────────────────────────────────

@app.command("add-pharmacopoeia")
def add_pharmacopoeia(
    source: str = typer.Option(
        ...,
        "--source", "-s",
        help="Path to the BP HTML or USP PDF file to add.",
    ),
    type: str = typer.Option(
        ...,
        "--type", "-t",
        help="Pharmacopoeia type: BP or USP",
    ),
):
    """
    Parse a single BP HTML or USP PDF file and add it to the database.

    Examples:
      python cli.py add-pharmacopoeia --source pharmacopoeia_db/BP/.../monographs/paracetamol.html --type BP
      python cli.py add-pharmacopoeia --source "pharmacopoeia_db/USP/.../M/USP-NF Metformin Hydrochloride.pdf" --type USP
    """
    if type.upper() not in ("BP", "USP"):
        rprint("[red]ERROR: --type must be BP or USP[/red]")
        raise typer.Exit(1)

    rprint(f"[bold cyan]Adding {type.upper()} monograph: {source}[/bold cyan]")

    result = add_single(source, type.upper(), verbose=True)

    if "error" in result:
        rprint(f"[red]✗ Failed: {result['error']}[/red]")
        raise typer.Exit(1)

    warnings = [w for w in result.get("parse_warnings", []) if w.startswith("MISSING")]
    if warnings:
        rprint(f"\n[yellow]⚠ Missing fields (will be filled by PubChem):[/yellow]")
        for w in warnings:
            rprint(f"   [dim]{w}[/dim]")
    else:
        rprint(f"\n[green]✓ All fields populated[/green]")

    rprint(f"\n[bold]Drug   :[/bold] {result.get('drug_name')}")
    rprint(f"[bold]Source :[/bold] {result.get('source')}")
    rprint(f"[bold]Edition:[/bold] {result.get('edition')}")
    rprint(f"[bold]Formula:[/bold] {result.get('molecular_formula')}")


# ── Command 3: lookup-pharmacopoeia ───────────────────────────────────────────

@app.command("lookup-pharmacopoeia")
def lookup_pharmacopoeia(
    drug: str = typer.Argument(..., help="Drug name to look up (partial match ok)"),
    show_fields: bool = typer.Option(
        False,
        "--fields", "-f",
        help="Show all extracted fields, not just summary",
    ),
):
    """
    Look up a drug in the pharmacopoeia database.

    Examples:
      python cli.py lookup-pharmacopoeia metformin
      python cli.py lookup-pharmacopoeia paracetamol --fields
      python cli.py lookup-pharmacopoeia "metformin hydrochloride"
    """
    import json

    rprint(f"[bold cyan]Looking up: {drug}[/bold cyan]")
    result = lookup(drug)

    if not result["matches"]:
        rprint(f"[red]✗ No match found for '{drug}' in the database.[/red]")
        rprint("[dim]Run 'python cli.py build-pharmacopoeia-db --type BP' to populate.[/dim]")
        raise typer.Exit(1)

    rprint(f"\n[green]Matches ({len(result['matches'])}):[/green]")
    for m in result["matches"][:10]:
        rprint(f"  • {m}")

    for src, data in [("BP", result["bp_data"]), ("USP", result["usp_data"])]:
        if not data:
            rprint(f"\n[dim]{src}: not in database[/dim]")
            continue

        rprint(f"\n[bold underline]{src} Data[/bold underline]")

        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("Field", style="cyan", width=22)
        table.add_column("Value", style="white")

        def _fmt(val):
            if val is None:
                return "[dim]—[/dim]"
            if isinstance(val, dict):
                return ", ".join(f"{k}={v}" for k, v in val.items() if v is not None)
            if isinstance(val, list):
                return f"[{len(val)} items]"
            return str(val)[:80]

        fields_to_show = [
            "drug_name", "edition", "molecular_formula",
            "description", "storage",
        ]
        if show_fields:
            fields_to_show = [
                "drug_name", "edition", "molecular_formula", "description",
                "identification", "assay", "related_substances",
                "dissolution", "storage", "microbial_limits",
                "loss_on_drying", "water_content", "uniformity",
            ]

        for field in fields_to_show:
            table.add_row(field, _fmt(data.get(field)))

        console.print(table)

        warnings = [w for w in data.get("parse_warnings", []) if "MISSING" in w]
        if warnings:
            rprint(f"  [yellow]⚠ Missing fields: {len(warnings)}[/yellow]")
            for w in warnings:
                rprint(f"    [dim]{w}[/dim]")


# ── Command 4: pharmacopoeia-stats ────────────────────────────────────────────

@app.command("pharmacopoeia-stats")
def pharmacopoeia_stats():
    """
    Show statistics about the local pharmacopoeia database.

    Example:
      python cli.py pharmacopoeia-stats
    """
    stats = db_stats()

    rprint("\n[bold cyan]Pharmacopoeia Database Statistics[/bold cyan]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total drugs indexed", str(stats["total_drugs"]))
    table.add_row("BP monographs",       str(stats["bp_count"]))
    table.add_row("USP monographs",      str(stats["usp_count"]))
    table.add_row("BP only",             str(stats["bp_only"]))
    table.add_row("USP only",            str(stats["usp_only"]))
    table.add_row("Both BP + USP",       str(stats["both_sources"]))
    table.add_row("Last updated",        str(stats["last_updated"]))
    table.add_row("Index file",          str(stats["index_path"]))

    console.print(table)

    if stats["total_drugs"] == 0:
        rprint("\n[yellow]Database is empty. Run:[/yellow]")
        rprint("  python cli.py build-pharmacopoeia-db --type BP")
        rprint("  python cli.py build-pharmacopoeia-db --type USP")