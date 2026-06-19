"""
NAFDAC Dossier Generator — CLI Entry Point
==========================================
All commands are registered here. Each command delegates
to its respective module. Stubs for future phases are
marked clearly so we fill them in phase by phase.
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from pathlib import Path
from typing import Optional

app = typer.Typer(
    name="nafdac",
    help="NAFDAC Nigeria Pharmaceutical Dossier Generator",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


def _banner():
    """Print project banner."""
    text = Text()
    text.append("NAFDAC", style="bold green")
    text.append(" Dossier Generator", style="bold white")
    text.append(" v0.1.0", style="dim")
    console.print(Panel(text, expand=False))


# ─────────────────────────────────────────────
# COMMAND: ingest
# ─────────────────────────────────────────────
@app.command()
def ingest(
    input: Path = typer.Option(..., "--input", "-i", help="Path to folder or file containing existing dossier(s)"),
    drug: str = typer.Option(..., "--drug", "-d", help="Drug name and strength e.g. 'Amoxicillin 500mg'"),
    output: Path = typer.Option(Path("templates/"), "--output", "-o", help="Where to save extracted templates"),
):
    """
    [Phase 2] Ingest an existing manually-written dossier and extract reusable templates.

    Example:
        nafdac ingest --input ./drafts/amoxicillin/ --drug "Amoxicillin 500mg"
    """
    _banner()
    console.print(f"[bold yellow]INGEST[/bold yellow] — Reading dossier from: [cyan]{input}[/cyan]")
    console.print(f"   Drug reference : [green]{drug}[/green]")
    console.print(f"   Template output: [green]{output}[/green]")
    console.print()

    suffix = input.suffix.lower() if input.is_file() else ""

    console.print("[bold]Step 1/3[/bold] Parsing dossier...")
    try:
        if input.is_dir() or suffix == ".docx":
            from ingestion.docx_parser import parse_dossier_docx
            parsed = parse_dossier_docx(input, drug_name_hint=drug)
        elif suffix == ".pdf":
            from ingestion.pdf_parser import parse_dossier_pdf
            parsed = parse_dossier_pdf(input, drug_name_hint=drug)
        else:
            console.print(f"[red]Unsupported file type. Use .docx, .pdf, or a folder.[/red]")
            raise typer.Exit(code=1)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    parsed.print_summary()

    console.print("[bold]Step 2/3[/bold] Detecting variables and building Jinja2 templates...")
    from ingestion.template_extractor import extract_templates
    library = extract_templates(parsed, drug_name_hint=drug, templates_root=output)

    console.print("[bold]Step 3/3[/bold] Saving manifest...")
    library.print_summary()
    console.print("[green]Ingestion complete.[/green]")
    console.print(f"   {len(library.entries)} templates saved to [cyan]{output}[/cyan]")
    console.print(f"   {library.total_variables_detected} variables detected")


# ─────────────────────────────────────────────
# COMMAND: new-drug
# ─────────────────────────────────────────────
@app.command(name="new-drug")
def new_drug(
    name: str = typer.Option(..., "--name", "-n", help="Drug name e.g. 'Metformin Hydrochloride'"),
    output: Path = typer.Option(Path("config/drug_profile.yaml"), "--output", "-o", help="Where to save the drug profile YAML"),
):
    """
    [Phase 1] Create a new drug profile YAML for a drug you want to register.

    Example:
        nafdac new-drug --name "Metformin 850mg" --output ./config/metformin.yaml
    """
    _banner()
    console.print(f"[bold yellow]NEW DRUG[/bold yellow] — Creating profile for: [cyan]{name}[/cyan]")

    from config_manager import create_blank_drug_profile
    create_blank_drug_profile(name=name, output_path=output)

    console.print(f"[green]Drug profile created at:[/green] {output}")
    console.print(f"[dim]Fill in the YAML fields then run: nafdac generate --drug-profile {output}[/dim]")


# ─────────────────────────────────────────────
# COMMAND: generate
# ─────────────────────────────────────────────
@app.command()
def generate(
    drug_profile: Path = typer.Option(..., "--drug-profile", "-p", help="Path to the filled drug_profile.yaml"),
    output: Path = typer.Option(Path("output/"), "--output", "-o", help="Root folder for generated submission"),
    skip_ai: bool = typer.Option(False, "--skip-ai", help="Skip AI narrative tweaking"),
):
    """
    [Phase 4] Generate a complete NAFDAC dossier from a drug profile.

    Example:
        nafdac generate --drug-profile ./config/metformin.yaml --output ./submissions/metformin/
    """
    _banner()
    console.print(f"[bold yellow]GENERATE[/bold yellow] — Drug profile: [cyan]{drug_profile}[/cyan]")
    console.print(f"   Output folder : [cyan]{output}[/cyan]")
    console.print(f"   AI narratives : [green]{'DISABLED' if skip_ai else 'ENABLED'}[/green]")
    console.print()
    console.print("[dim]Phase 4 not yet implemented.[/dim]")


# ─────────────────────────────────────────────
# COMMAND: validate
# ─────────────────────────────────────────────
@app.command()
def validate(
    path: Path = typer.Option(..., "--path", "-p", help="Path to the generated submission folder"),
    strict: bool = typer.Option(False, "--strict", help="Fail on warnings as well as errors"),
):
    """
    [Phase 7] Validate a generated submission against NAFDAC requirements.

    Example:
        nafdac validate --path ./submissions/metformin/
    """
    _banner()
    console.print(f"[bold yellow]VALIDATE[/bold yellow] — Checking: [cyan]{path}[/cyan]")
    console.print(f"   Strict mode: [green]{'ON' if strict else 'OFF'}[/green]")
    console.print()
    console.print("[dim]Phase 7 not yet implemented.[/dim]")


# ─────────────────────────────────────────────
# COMMAND: export-pdf
# ─────────────────────────────────────────────
@app.command(name="export-pdf")
def export_pdf(
    path: Path = typer.Option(..., "--path", "-p", help="Path to the submission folder containing .docx files"),
    keep_docx: bool = typer.Option(True, "--keep-docx/--no-keep-docx", help="Keep .docx files alongside PDFs"),
):
    """
    [Phase 4] Convert all .docx files in a submission folder to PDF via LibreOffice.

    Example:
        nafdac export-pdf --path ./submissions/metformin/
    """
    _banner()
    console.print(f"[bold yellow]EXPORT PDF[/bold yellow] — Converting: [cyan]{path}[/cyan]")
    console.print(f"   Keep .docx: [green]{'YES' if keep_docx else 'NO'}[/green]")
    console.print()
    console.print("[dim]Phase 4.4 not yet implemented.[/dim]")


# ─────────────────────────────────────────────
# COMMAND: diff
# ─────────────────────────────────────────────
@app.command()
def diff(
    original: Path = typer.Option(..., "--original", help="Path to the original Jinja2 template or source narrative"),
    generated: Path = typer.Option(..., "--generated", help="Path to the AI-generated .docx or .txt section"),
    export: Optional[Path] = typer.Option(None, "--export", help="Save diff report to this path"),
):
    """
    [Phase 6] Show a diff between the original template and AI-generated output.

    Example:
        nafdac diff --original ./templates/module2/qos.jinja2 --generated ./submissions/metformin/module2/qos.docx
    """
    _banner()
    console.print(f"[bold yellow]DIFF[/bold yellow]")
    console.print(f"   Original : [cyan]{original}[/cyan]")
    console.print(f"   Generated: [cyan]{generated}[/cyan]")
    if export:
        console.print(f"   Export to: [cyan]{export}[/cyan]")
    console.print()
    console.print("[dim]Phase 6.2 not yet implemented.[/dim]")


# ─────────────────────────────────────────────
# COMMAND: add-pharmacopoeia
# ─────────────────────────────────────────────
@app.command(name="add-pharmacopoeia")
def add_pharmacopoeia(
    source: Path = typer.Option(..., "--source", "-s", help="Path to the BP or USP monograph PDF"),
    type: str = typer.Option(..., "--type", "-t", help="Pharmacopoeia type: BP or USP"),
    drug: Optional[str] = typer.Option(None, "--drug", help="Drug name if parsing a single-drug monograph"),
):
    """
    [Phase 3] Parse and add a pharmacopoeia monograph to the local database.

    Example:
        nafdac add-pharmacopoeia --source ./refs/metformin_bp.pdf --type BP --drug "Metformin"
    """
    _banner()
    pharm_type = type.upper()
    if pharm_type not in ("BP", "USP"):
        console.print("[red]--type must be either BP or USP[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold yellow]ADD PHARMACOPOEIA[/bold yellow] — Source: [cyan]{source}[/cyan]")
    console.print(f"   Type: [green]{pharm_type}[/green]")
    if drug:
        console.print(f"   Drug: [green]{drug}[/green]")
    console.print()
    console.print("[dim]Phase 3 not yet implemented.[/dim]")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app()
