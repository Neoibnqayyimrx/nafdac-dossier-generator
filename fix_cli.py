import shutil
from pathlib import Path

cli = Path("cli.py")
shutil.copy(cli, "cli_backup.py")
print("Backup saved to cli_backup.py")

new_content = '''"""
NAFDAC Dossier Generator — CLI Entry Point
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import print as rprint
from pathlib import Path
from typing import Optional
from pharmacopoeia_db_builder import build_db, add_single, lookup, db_stats, rebuild_index

app = typer.Typer(
    name="nafdac",
    help="NAFDAC Nigeria Pharmaceutical Dossier Generator",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

def _banner():
    text = Text()
    text.append("NAFDAC", style="bold green")
    text.append(" Dossier Generator", style="bold white")
    text.append(" v0.1.0", style="dim")
    console.print(Panel(text, expand=False))

@app.command()
def ingest(
    input: Path = typer.Option(..., "--input", "-i"),
    drug: str = typer.Option(..., "--drug", "-d"),
    output: Path = typer.Option(Path("templates/"), "--output", "-o"),
):
    """[Phase 2] Ingest an existing dossier and extract reusable templates."""
    _banner()
    suffix = input.suffix.lower() if input.is_file() else ""
    try:
        if input.is_dir() or suffix == ".docx":
            from ingestion.docx_parser import parse_dossier_docx
            parsed = parse_dossier_docx(input, drug_name_hint=drug)
        elif suffix == ".pdf":
            from ingestion.pdf_parser import parse_dossier_pdf
            parsed = parse_dossier_pdf(input, drug_name_hint=drug)
        else:
            console.print("[red]Unsupported file type.[/red]")
            raise typer.Exit(code=1)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    parsed.print_summary()
    from ingestion.template_extractor import extract_templates
    library = extract_templates(parsed, drug_name_hint=drug, templates_root=output)
    library.print_summary()

@app.command(name="new-drug")
def new_drug(
    name: str = typer.Option(..., "--name", "-n"),
    output: Path = typer.Option(Path("config/drug_profile.yaml"), "--output", "-o"),
):
    """[Phase 1] Create a new drug profile YAML."""
    _banner()
    from config_manager import create_blank_drug_profile
    create_blank_drug_profile(name=name, output_path=output)
    console.print(f"[green]Drug profile created at:[/green] {output}")

@app.command()
def generate(
    drug_profile: Path = typer.Option(..., "--drug-profile", "-p"),
    output: Path = typer.Option(Path("output/"), "--output", "-o"),
    skip_ai: bool = typer.Option(False, "--skip-ai"),
):
    """[Phase 4] Generate a complete NAFDAC dossier from a drug profile."""
    _banner()
    console.print("[dim]Phase 4 not yet implemented.[/dim]")

@app.command()
def validate(
    path: Path = typer.Option(..., "--path", "-p"),
    strict: bool = typer.Option(False, "--strict"),
):
    """[Phase 7] Validate a generated submission against NAFDAC requirements."""
    _banner()
    console.print("[dim]Phase 7 not yet implemented.[/dim]")

@app.command(name="export-pdf")
def export_pdf(
    path: Path = typer.Option(..., "--path", "-p"),
    keep_docx: bool = typer.Option(True, "--keep-docx/--no-keep-docx"),
):
    """[Phase 4] Convert .docx files to PDF via LibreOffice."""
    _banner()
    console.print("[dim]Phase 4.4 not yet implemented.[/dim]")

@app.command()
def diff(
    original: Path = typer.Option(..., "--original"),
    generated: Path = typer.Option(..., "--generated"),
    export: Optional[Path] = typer.Option(None, "--export"),
):
    """[Phase 6] Show diff between original template and AI-generated output."""
    _banner()
    console.print("[dim]Phase 6.2 not yet implemented.[/dim]")

@app.command(name="add-pharmacopoeia")
def add_pharmacopoeia(
    source: str = typer.Option(..., "--source", "-s"),
    type: str = typer.Option(..., "--type", "-t"),
):
    """[Phase 3] Parse a single BP HTML or USP PDF and add it to the database."""
    _banner()
    if type.upper() not in ("BP", "USP"):
        rprint("[red]ERROR: --type must be BP or USP[/red]")
        raise typer.Exit(1)
    result = add_single(source, type.upper(), verbose=True)
    if "error" in result:
        rprint(f"[red]Failed: {result[\'error\']}[/red]")
        raise typer.Exit(1)
    missing = [w for w in result.get("parse_warnings", []) if w.startswith("MISSING")]
    if missing:
        rprint("[yellow]Missing fields (PubChem will fill):[/yellow]")
        for w in missing:
            rprint(f"  [dim]{w}[/dim]")
    else:
        rprint("[green]All fields populated[/green]")
    rprint(f"Drug: {result.get(\'drug_name\')}  |  Formula: {result.get(\'molecular_formula\')}")

@app.command(name="build-pharmacopoeia-db")
def build_pharmacopoeia_db(
    type: str = typer.Option("BP", "--type", "-t"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    max_files: Optional[int] = typer.Option(None, "--max-files"),
):
    """[Phase 3] Parse all BP/USP monographs and build the local JSON database."""
    _banner()
    if type.upper() not in {"BP", "USP", "ALL"}:
        rprint("[red]ERROR: --type must be BP, USP, or ALL[/red]")
        raise typer.Exit(1)
    rprint(f"[bold cyan]Building {type.upper()} database...[/bold cyan]")
    summary = build_db(source=type.upper(), resume=resume, max_files=max_files, show_progress=True)
    rprint(f"[green]Done[/green] — Processed: {summary[\'processed\']}  Skipped: {summary[\'skipped\']}  Errors: {summary[\'errors\']}")

@app.command(name="lookup-pharmacopoeia")
def lookup_pharmacopoeia(
    drug: str = typer.Argument(...),
    show_fields: bool = typer.Option(False, "--fields", "-f"),
):
    """[Phase 3] Look up a drug in the local pharmacopoeia database."""
    _banner()
    result = lookup(drug)
    if not result["matches"]:
        rprint(f"[red]No match for \'{drug}\'. Run build-pharmacopoeia-db first.[/red]")
        raise typer.Exit(1)
    rprint(f"[green]Matches:[/green] {result[\'matches\'][:5]}")
    for src, data in [("BP", result["bp_data"]), ("USP", result["usp_data"])]:
        if not data:
            continue
        rprint(f"\\n[bold]{src}[/bold]")
        table = Table(show_header=False, box=None)
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        fields = ["drug_name","edition","molecular_formula","description","storage"]
        if show_fields:
            fields += ["assay","related_substances","dissolution","loss_on_drying","uniformity"]
        for f in fields:
            v = data.get(f)
            table.add_row(f, str(v)[:80] if v else "[dim]—[/dim]")
        console.print(table)

@app.command(name="pharmacopoeia-stats")
def pharmacopoeia_stats():
    """[Phase 3] Show statistics about the local pharmacopoeia database."""
    _banner()
    s = db_stats()
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Total drugs", str(s["total_drugs"]))
    table.add_row("BP monographs", str(s["bp_count"]))
    table.add_row("USP monographs", str(s["usp_count"]))
    table.add_row("Both sources", str(s["both_sources"]))
    table.add_row("Last updated", str(s["last_updated"]))
    console.print(table)
    if s["total_drugs"] == 0:
        rprint("[yellow]Empty. Run: python cli.py build-pharmacopoeia-db --type BP[/yellow]")

if __name__ == "__main__":
    app()
'''

cli.write_text(new_content, encoding="utf-8")
print("cli.py fixed successfully.")