# src/__main__.py
import asyncio
import typer
from typing import Optional
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich.panel import Panel
from rich import box
from InquirerPy import inquirer

from src.pipeline import Pipeline
from src.config import settings

app = typer.Typer(help="Lead Generator - Find omnichannel retail leads")
console = Console()

VERTICALS = {
    "health_wellness": "Health & Wellness (supplements, vitamins, nutrition)",
    "sporting_goods": "Sporting Goods (outdoor gear, athletics, equipment)",
    "apparel": "Apparel (clothing, fashion, boutiques)",
}

COUNTRIES = {
    "us": "United States (35 major cities)",
    "canada": "Canada (15 major cities)",
}


def show_banner():
    """Display the application banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                     🎯 LEAD GENERATOR                         ║
║         Find Omnichannel Retailers with 3-10 Locations        ║
╚═══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold blue")


def show_summary(verticals: list[str], countries: list[str]):
    """Display a summary of what will be searched."""
    table = Table(title="Search Configuration", box=box.ROUNDED)
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    # Verticals - from actual selection
    vertical_names = [VERTICALS.get(v, v).split(" (")[0] for v in verticals]
    table.add_row("Verticals", ", ".join(vertical_names))

    # Countries - from actual selection
    country_names = [COUNTRIES.get(c, c).split(" (")[0] for c in countries]
    table.add_row("Countries", ", ".join(country_names))

    # Calculate actual cities from config
    cities = []
    for country in countries:
        cities.extend(settings.cities.get(country, []))
    cities_count = len(cities)

    # Calculate actual queries from config
    queries = []
    for vertical in verticals:
        queries.extend(settings.search_queries.get(vertical, []))
    queries_count = len(queries)

    total_searches = cities_count * queries_count
    table.add_row("Cities", str(cities_count))
    table.add_row("Queries per city", str(queries_count))
    table.add_row("Est. API Calls", f"~{total_searches}")

    console.print()
    console.print(table)
    console.print()


@app.command()
def run(
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive", "-i/-I",
        help="Run in interactive mode with prompts"
    ),
    verticals: str = typer.Option(
        "all",
        "--verticals", "-v",
        help="Verticals to search: all, health_wellness, sporting_goods, apparel (comma-separated)"
    ),
    countries: str = typer.Option(
        "us,ca",
        "--countries", "-c",
        help="Countries to search: us, ca (comma-separated)"
    ),
):
    """Run the full lead generation pipeline."""
    show_banner()

    if interactive:
        # Interactive vertical selection
        console.print("[bold cyan]Step 1:[/bold cyan] Select retail verticals to search\n")

        vertical_choices = inquirer.checkbox(
            message="Select verticals (Space to toggle, Enter to confirm):",
            choices=[
                {"name": VERTICALS["health_wellness"], "value": "health_wellness", "enabled": True},
                {"name": VERTICALS["sporting_goods"], "value": "sporting_goods", "enabled": True},
                {"name": VERTICALS["apparel"], "value": "apparel", "enabled": True},
            ],
            instruction="(Use arrow keys and space to select)",
        ).execute()

        if not vertical_choices:
            console.print("[red]No verticals selected. Exiting.[/red]")
            raise typer.Exit(1)

        vertical_list = vertical_choices

        # Interactive country selection
        console.print("\n[bold cyan]Step 2:[/bold cyan] Select countries to search\n")

        country_choices = inquirer.checkbox(
            message="Select countries (Space to toggle, Enter to confirm):",
            choices=[
                {"name": COUNTRIES["us"], "value": "us", "enabled": True},
                {"name": COUNTRIES["canada"], "value": "canada", "enabled": True},
            ],
            instruction="(Use arrow keys and space to select)",
        ).execute()

        if not country_choices:
            console.print("[red]No countries selected. Exiting.[/red]")
            raise typer.Exit(1)

        country_list = country_choices

    else:
        # Parse from command line
        if verticals == "all":
            vertical_list = ["health_wellness", "sporting_goods", "apparel"]
        else:
            vertical_list = [v.strip() for v in verticals.split(",")]

        country_list = [c.strip() for c in countries.split(",")]

    # Normalize country codes
    country_list = ["canada" if c == "ca" else c for c in country_list]

    # Show summary
    show_summary(vertical_list, country_list)

    # Confirm before starting
    if interactive:
        if not Confirm.ask("[bold yellow]Start the pipeline?[/bold yellow]", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    console.print()
    pipeline = Pipeline()
    output_file = asyncio.run(pipeline.run(verticals=vertical_list, countries=country_list))

    # Final summary
    console.print()
    console.print(Panel(
        f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
        f"Output saved to:\n[cyan]{output_file}[/cyan]",
        title="Success",
        border_style="green",
    ))


@app.command()
def search(
    vertical: str = typer.Argument(None, help="Vertical to search"),
    country: str = typer.Option(None, "--country", "-c", help="Country to search"),
):
    """Run only the Google Places search stage."""
    show_banner()

    # Interactive if no arguments provided
    if vertical is None:
        vertical = inquirer.select(
            message="Select vertical to search:",
            choices=[
                {"name": VERTICALS["health_wellness"], "value": "health_wellness"},
                {"name": VERTICALS["sporting_goods"], "value": "sporting_goods"},
                {"name": VERTICALS["apparel"], "value": "apparel"},
            ],
        ).execute()

    if country is None:
        country = inquirer.select(
            message="Select country to search:",
            choices=[
                {"name": COUNTRIES["us"], "value": "us"},
                {"name": COUNTRIES["canada"], "value": "canada"},
            ],
        ).execute()

    country = "canada" if country == "ca" else country

    console.print(f"\n[bold]Searching:[/bold] {VERTICALS.get(vertical, vertical)}")
    console.print(f"[bold]Country:[/bold] {COUNTRIES.get(country, country)}\n")

    pipeline = Pipeline()
    results = asyncio.run(pipeline.stage_1_search([vertical], [country]))
    console.print(f"\n[green]✓ Found {len(results)} places[/green]")


if __name__ == "__main__":
    app()
