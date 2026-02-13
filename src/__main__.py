# src/__main__.py
import asyncio
import typer
from typing import Optional
from rich.console import Console

from src.pipeline import Pipeline

app = typer.Typer(help="Lead Generator - Find omnichannel retail leads")
console = Console()

@app.command()
def run(
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

    # Parse verticals
    if verticals == "all":
        vertical_list = ["health_wellness", "sporting_goods", "apparel"]
    else:
        vertical_list = [v.strip() for v in verticals.split(",")]

    # Parse countries
    country_list = [c.strip() for c in countries.split(",")]
    country_list = ["canada" if c == "ca" else c for c in country_list]

    console.print(f"[bold]Verticals:[/bold] {vertical_list}")
    console.print(f"[bold]Countries:[/bold] {country_list}")

    pipeline = Pipeline()
    output_file = asyncio.run(pipeline.run(verticals=vertical_list, countries=country_list))

    console.print(f"\n[bold green]Done! Output: {output_file}[/bold green]")

@app.command()
def search(
    vertical: str = typer.Argument(..., help="Vertical to search"),
    country: str = typer.Option("us", "--country", "-c", help="Country to search"),
):
    """Run only the Google Places search stage."""
    pipeline = Pipeline()
    country = "canada" if country == "ca" else country
    results = asyncio.run(pipeline.stage_1_search([vertical], [country]))
    console.print(f"[green]Found {len(results)} places[/green]")

if __name__ == "__main__":
    app()
