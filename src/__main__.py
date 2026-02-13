# src/__main__.py
import asyncio
import sys
from datetime import datetime
from pathlib import Path
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
    "pet_supplies": "Pet Supplies (pet food, accessories, grooming)",
    "beauty_cosmetics": "Beauty & Cosmetics (makeup, skincare, beauty supplies)",
    "specialty_food": "Specialty Food (gourmet, cheese, spices)",
    "running_athletic": "Running & Athletic (running, triathlon, marathon)",
    "cycling": "Cycling (bikes, cycling gear, accessories)",
    "outdoor_camping": "Outdoor & Camping (camping, hiking, backpacking)",
    "baby_kids": "Baby & Kids (baby products, children's clothing)",
    "home_goods": "Home Goods (kitchenware, cookware, home products)",
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


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to human-readable."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts or "Unknown"


def show_checkpoint_table(checkpoints: list[dict]):
    """Display a table of available checkpoints."""
    table = Table(title="Available Checkpoints", box=box.ROUNDED)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Stage", style="cyan", width=15)
    table.add_column("Verticals", style="green")
    table.add_column("Countries", style="blue")
    table.add_column("Progress", style="magenta")
    table.add_column("Saved At", style="yellow")

    for i, cp in enumerate(checkpoints, 1):
        # Format verticals nicely
        vert_names = [VERTICALS.get(v, v).split(" (")[0] for v in cp["verticals"]]

        # Format countries nicely
        country_names = [COUNTRIES.get(c, c).split(" (")[0] for c in cp["countries"]]

        # Progress summary
        progress = f"{cp['places_count']} places"
        if cp["brands_count"] > 0:
            progress += f" → {cp['brands_count']} brands"
        if cp["verified_count"] > 0:
            progress += f" → {cp['verified_count']} verified"
        if cp["ecommerce_count"] > 0:
            progress += f" → {cp['ecommerce_count']} e-commerce"

        table.add_row(
            str(i),
            f"Stage {cp['stage']}: {cp['stage_name']}",
            ", ".join(vert_names),
            ", ".join(country_names),
            progress,
            format_timestamp(cp["timestamp"]),
        )

    console.print()
    console.print(table)
    console.print()


def select_checkpoint(pipeline: Pipeline) -> Optional[Path]:
    """Prompt user to select a checkpoint or start fresh."""
    checkpoints = pipeline.list_checkpoints()

    if not checkpoints:
        return None

    console.print("\n[bold yellow]Previous runs found![/bold yellow]")
    show_checkpoint_table(checkpoints)

    # Build choices for inquirer
    choices = [
        {"name": "Start fresh (new run)", "value": "fresh"},
    ]

    for i, cp in enumerate(checkpoints):
        vert_names = [VERTICALS.get(v, v).split(" (")[0] for v in cp["verticals"]]
        country_names = [COUNTRIES.get(c, c).split(" (")[0] for c in cp["countries"]]
        label = (
            f"Resume #{i+1}: Stage {cp['stage']} ({cp['stage_name']}) - "
            f"{', '.join(vert_names)} in {', '.join(country_names)}"
        )
        choices.append({"name": label, "value": cp["path"]})

    # Add delete and exit options
    choices.append({"name": "Delete a checkpoint", "value": "delete"})
    choices.append({"name": "Exit", "value": "exit"})

    selection = inquirer.select(
        message="What would you like to do?",
        choices=choices,
        instruction="(↑↓ navigate, Enter select)",
    ).execute()

    if selection == "fresh":
        return None
    elif selection == "exit":
        console.print("[yellow]Exiting...[/yellow]")
        raise typer.Exit(0)
    elif selection == "delete":
        # Let user select which checkpoint to delete
        delete_choices = [
            {"name": f"#{i+1}: Stage {cp['stage']} - {format_timestamp(cp['timestamp'])}", "value": cp["path"]}
            for i, cp in enumerate(checkpoints)
        ]
        delete_choices.append({"name": "Cancel", "value": "cancel"})

        to_delete = inquirer.select(
            message="Select checkpoint to delete:",
            choices=delete_choices,
        ).execute()

        if to_delete != "cancel":
            pipeline.delete_checkpoint(to_delete)
            console.print(f"[green]✓ Checkpoint deleted[/green]")

        # Recursively ask again
        return select_checkpoint(pipeline)
    else:
        return selection


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
        help="Verticals: all, or comma-separated list (health_wellness, sporting_goods, apparel, pet_supplies, beauty_cosmetics, specialty_food, running_athletic, cycling, outdoor_camping, baby_kids, home_goods)"
    ),
    countries: str = typer.Option(
        "us,ca",
        "--countries", "-c",
        help="Countries to search: us, ca (comma-separated)"
    ),
):
    """Run the full lead generation pipeline."""
    show_banner()

    # Initialize pipeline to check for checkpoints
    pipeline = Pipeline()
    resume_checkpoint: Optional[Path] = None

    # Check for existing checkpoints in interactive mode
    if interactive and pipeline.has_checkpoints():
        resume_checkpoint = select_checkpoint(pipeline)

        if resume_checkpoint:
            # If resuming, skip vertical/country selection
            console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

            try:
                output_file = asyncio.run(pipeline.run(resume_checkpoint=resume_checkpoint))

                # Final summary
                console.print()
                console.print(Panel(
                    f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
                    f"Output saved to:\n[cyan]{output_file}[/cyan]",
                    title="Success",
                    border_style="green",
                ))
                return
            except KeyboardInterrupt:
                console.print("\n[yellow]Pipeline interrupted. Progress saved to checkpoint.[/yellow]")
                raise typer.Exit(1)

    if interactive:
        # Interactive vertical selection
        console.print("[bold cyan]Step 1:[/bold cyan] Select retail verticals to search\n")

        vertical_choices = inquirer.checkbox(
            message="Select verticals (Space to select, Enter to confirm):",
            choices=[
                {"name": VERTICALS["health_wellness"], "value": "health_wellness"},
                {"name": VERTICALS["sporting_goods"], "value": "sporting_goods"},
                {"name": VERTICALS["apparel"], "value": "apparel"},
                {"name": VERTICALS["pet_supplies"], "value": "pet_supplies"},
                {"name": VERTICALS["beauty_cosmetics"], "value": "beauty_cosmetics"},
                {"name": VERTICALS["specialty_food"], "value": "specialty_food"},
                {"name": VERTICALS["running_athletic"], "value": "running_athletic"},
                {"name": VERTICALS["cycling"], "value": "cycling"},
                {"name": VERTICALS["outdoor_camping"], "value": "outdoor_camping"},
                {"name": VERTICALS["baby_kids"], "value": "baby_kids"},
                {"name": VERTICALS["home_goods"], "value": "home_goods"},
            ],
            instruction="(↑↓ navigate, Space select, Enter confirm)",
        ).execute()

        if not vertical_choices:
            console.print("[red]No verticals selected. Exiting.[/red]")
            raise typer.Exit(1)

        vertical_list = vertical_choices

        # Interactive country selection
        console.print("\n[bold cyan]Step 2:[/bold cyan] Select countries to search\n")

        country_choices = inquirer.checkbox(
            message="Select countries (Space to select, Enter to confirm):",
            choices=[
                {"name": COUNTRIES["us"], "value": "us"},
                {"name": COUNTRIES["canada"], "value": "canada"},
            ],
            instruction="(↑↓ navigate, Space select, Enter confirm)",
        ).execute()

        if not country_choices:
            console.print("[red]No countries selected. Exiting.[/red]")
            raise typer.Exit(1)

        country_list = country_choices

    else:
        # Parse from command line
        if verticals == "all":
            vertical_list = list(VERTICALS.keys())
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
    console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

    try:
        output_file = asyncio.run(pipeline.run(verticals=vertical_list, countries=country_list))

        # Final summary
        console.print()
        console.print(Panel(
            f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
            f"Output saved to:\n[cyan]{output_file}[/cyan]",
            title="Success",
            border_style="green",
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted. Progress saved to checkpoint.[/yellow]")
        raise typer.Exit(1)


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
                {"name": VERTICALS["pet_supplies"], "value": "pet_supplies"},
                {"name": VERTICALS["beauty_cosmetics"], "value": "beauty_cosmetics"},
                {"name": VERTICALS["specialty_food"], "value": "specialty_food"},
                {"name": VERTICALS["running_athletic"], "value": "running_athletic"},
                {"name": VERTICALS["cycling"], "value": "cycling"},
                {"name": VERTICALS["outdoor_camping"], "value": "outdoor_camping"},
                {"name": VERTICALS["baby_kids"], "value": "baby_kids"},
                {"name": VERTICALS["home_goods"], "value": "home_goods"},
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
    console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

    try:
        pipeline = Pipeline()
        results = asyncio.run(pipeline.stage_1_search([vertical], [country]))
        console.print(f"\n[green]✓ Found {len(results)} places[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Search interrupted.[/yellow]")
        raise typer.Exit(1)


@app.command()
def checkpoints():
    """List and manage saved checkpoints."""
    show_banner()

    pipeline = Pipeline()
    checkpoint_list = pipeline.list_checkpoints()

    if not checkpoint_list:
        console.print("[yellow]No checkpoints found.[/yellow]")
        console.print("[dim]Run the pipeline to create checkpoints automatically.[/dim]")
        return

    show_checkpoint_table(checkpoint_list)

    action = inquirer.select(
        message="What would you like to do?",
        choices=[
            {"name": "Delete a checkpoint", "value": "delete"},
            {"name": "Delete all checkpoints", "value": "delete_all"},
            {"name": "Exit", "value": "exit"},
        ],
    ).execute()

    if action == "delete":
        delete_choices = [
            {"name": f"#{i+1}: Stage {cp['stage']} ({cp['stage_name']}) - {format_timestamp(cp['timestamp'])}", "value": cp["path"]}
            for i, cp in enumerate(checkpoint_list)
        ]
        delete_choices.append({"name": "Cancel", "value": "cancel"})

        to_delete = inquirer.select(
            message="Select checkpoint to delete:",
            choices=delete_choices,
        ).execute()

        if to_delete != "cancel":
            pipeline.delete_checkpoint(to_delete)
            console.print(f"[green]✓ Checkpoint deleted[/green]")

    elif action == "delete_all":
        if Confirm.ask("[bold red]Delete all checkpoints?[/bold red]", default=False):
            for cp in checkpoint_list:
                pipeline.delete_checkpoint(cp["path"])
            console.print(f"[green]✓ All checkpoints deleted[/green]")

    elif action == "exit":
        console.print("[dim]Goodbye![/dim]")


if __name__ == "__main__":
    app()
