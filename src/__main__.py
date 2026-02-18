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
from InquirerPy.separator import Separator
from src.navigation import NavigationStack, BACK_OPTION, MAIN_MENU_OPTION

from src.pipeline import Pipeline
from src.config import settings
from src.outreach_generator import OutreachGenerator, MESSAGE_TYPES

app = typer.Typer(
    help="Lead Generator - Find omnichannel retail leads",
    invoke_without_command=True,
)
console = Console()
nav = NavigationStack()

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


@app.callback()
def main(ctx: typer.Context):
    """Lead Generator - Find omnichannel retail leads."""
    # If no command specified, show interactive main menu
    if ctx.invoked_subcommand is None:
        interactive_main_menu()


def interactive_main_menu():
    """Main interactive menu that ties all functionality together."""
    import pandas as pd

    show_banner()
    nav.clear()  # Ensure clean state at main menu
    nav.push("main")

    # Check for existing results and checkpoints
    output_dirs = [Path("output"), Path("data/output")]
    csv_files = []
    for output_dir in output_dirs:
        csv_files.extend(output_dir.glob("leads_*.csv"))
    csv_files = sorted(csv_files, key=lambda p: p.stat().st_mtime, reverse=True)

    pipeline = Pipeline()
    checkpoints = pipeline.list_checkpoints()

    # Build dynamic menu based on available data
    menu_choices = []

    # Always show run option
    if checkpoints:
        menu_choices.append({
            "name": "🔄 Resume previous run",
            "value": "resume"
        })

    menu_choices.append({
        "name": "🚀 Start new lead generation",
        "value": "new_run"
    })

    if csv_files:
        latest = csv_files[0]
        try:
            df = pd.read_csv(latest)
            lead_count = len(df)
        except Exception:
            lead_count = "?"
        menu_choices.append({
            "name": f"📊 View results ({lead_count} leads in {latest.name})",
            "value": "results"
        })
        menu_choices.append({
            "name": "🔍 Enrich leads with Apollo",
            "value": "enrich"
        })
        menu_choices.append({
            "name": "📈 Show statistics",
            "value": "stats"
        })

    if checkpoints:
        menu_choices.append({
            "name": f"💾 Manage checkpoints ({len(checkpoints)} saved)",
            "value": "checkpoints"
        })

    menu_choices.append({
        "name": "⚙️  Settings overview",
        "value": "settings"
    })

    menu_choices.append(Separator())

    menu_choices.append({
        "name": "❌ Exit",
        "value": "exit"
    })

    while True:
        console.print()
        action = inquirer.select(
            message="What would you like to do?",
            choices=menu_choices,
            instruction="(↑↓ navigate, Enter select)",
        ).execute()

        if action == "exit":
            console.print("[dim]Goodbye![/dim]")
            break

        elif action == "new_run":
            _interactive_new_run()
            nav.clear()
            nav.push("main")

        elif action == "resume":
            _interactive_resume_run(pipeline, checkpoints)
            nav.clear()
            nav.push("main")

        elif action == "results":
            _interactive_results()
            nav.clear()
            nav.push("main")

        elif action == "enrich":
            _interactive_enrich()
            nav.clear()
            nav.push("main")

        elif action == "stats":
            _interactive_stats()
            nav.clear()
            nav.push("main")

        elif action == "checkpoints":
            _interactive_checkpoints(pipeline)
            nav.clear()
            nav.push("main")
            # Refresh checkpoints count
            checkpoints = pipeline.list_checkpoints()

        elif action == "settings":
            _show_settings_overview()
            nav.clear()
            nav.push("main")


def _show_settings_overview():
    """Display and configure settings interactively."""
    nav.push("settings")
    while True:
        console.print()
        table = Table(title="Current Settings", box=box.ROUNDED)
        table.add_column("#", style="dim", width=3)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        # API Keys (masked)
        table.add_row("1", "Google Places API", "✓ Set" if settings.google_places_api_key else "✗ Not set")
        table.add_row("2", "Firecrawl API", "✓ Set" if settings.firecrawl_api_key else "✗ Not set")
        table.add_row("3", "OpenAI API", "✓ Set" if settings.openai_api_key else "✗ Not set")
        table.add_row("4", "Apollo API", "✓ Set" if settings.apollo_api_key else "✗ Not set")

        # Enrichment
        if settings.enrichment.enabled:
            table.add_row("5", "Enrichment Provider", f"{settings.enrichment.provider.capitalize()}")
            table.add_row("6", "Max Contacts", str(settings.enrichment.max_contacts))
        else:
            table.add_row("5", "Enrichment", "Disabled")

        # Email verification
        table.add_row("7", "Email Verification", "Enabled" if settings.email_verification.enabled else "Disabled")
        if settings.email_verification.enabled:
            table.add_row("8", "SMTP Verification", "Enabled" if settings.email_verification.verify_smtp else "Disabled")
            table.add_row("9", "Include Risky Emails", "Yes" if settings.email_verification.include_risky else "No")

        # Concurrency
        table.add_row("10", "Search Concurrency", str(settings.search_concurrency))
        table.add_row("11", "E-commerce Concurrency", str(settings.ecommerce_concurrency))

        # Outreach
        table.add_row("12", "Outreach LLM Provider", settings.outreach.llm_provider.capitalize())
        table.add_row("13", "Outreach LLM Model", settings.outreach.llm_model)

        console.print(table)

        action = inquirer.select(
            message="What would you like to configure?",
            choices=[
                {"name": "🔌 Enrichment settings", "value": "enrichment"},
                {"name": "📧 Email verification settings", "value": "email"},
                {"name": "⚡ Concurrency settings", "value": "concurrency"},
                {"name": "🔑 View API key setup instructions", "value": "api_help"},
                {"name": "✉️  Outreach LLM settings", "value": "outreach"},
                Separator(),
                {"name": BACK_OPTION, "value": "back"},
                {"name": MAIN_MENU_OPTION, "value": "main_menu"},
            ],
        ).execute()

        if action == "back":
            nav.pop()
            return "back"

        if action == "main_menu":
            nav.clear()
            return "main_menu"

        if action == "enrichment":
            _configure_enrichment()

        elif action == "email":
            _configure_email_verification()

        elif action == "concurrency":
            _configure_concurrency()

        elif action == "api_help":
            _show_api_help()

        elif action == "outreach":
            _configure_outreach()


def _configure_enrichment():
    """Configure enrichment settings."""
    console.print()

    # Enable/disable
    enabled = inquirer.confirm(
        message="Enable contact enrichment?",
        default=settings.enrichment.enabled,
    ).execute()

    settings.enrichment.enabled = enabled

    if enabled:
        # Provider selection
        provider = inquirer.select(
            message="Select enrichment provider:",
            choices=[
                {"name": "LinkedIn (free, web scraping)", "value": "linkedin"},
                {"name": "Apollo.io (paid, requires API key)", "value": "apollo"},
            ],
            default=settings.enrichment.provider,
        ).execute()
        settings.enrichment.provider = provider

        # Max contacts
        max_contacts = inquirer.number(
            message="Maximum contacts per company:",
            default=settings.enrichment.max_contacts,
            min_allowed=1,
            max_allowed=10,
        ).execute()
        settings.enrichment.max_contacts = int(max_contacts)

    console.print("[green]✓ Enrichment settings updated[/green]")


def _configure_email_verification():
    """Configure email verification settings."""
    console.print()

    enabled = inquirer.confirm(
        message="Enable email verification?",
        default=settings.email_verification.enabled,
    ).execute()

    settings.email_verification.enabled = enabled

    if enabled:
        smtp = inquirer.confirm(
            message="Enable SMTP verification? (slower, may be blocked by some servers)",
            default=settings.email_verification.verify_smtp,
        ).execute()
        settings.email_verification.verify_smtp = smtp

        risky = inquirer.confirm(
            message="Include risky emails? (catch-all domains, unknown status)",
            default=settings.email_verification.include_risky,
        ).execute()
        settings.email_verification.include_risky = risky

    console.print("[green]✓ Email verification settings updated[/green]")


def _configure_concurrency():
    """Configure concurrency settings."""
    console.print()

    search_conc = inquirer.number(
        message="Search concurrency (parallel API calls):",
        default=settings.search_concurrency,
        min_allowed=1,
        max_allowed=50,
    ).execute()
    settings.search_concurrency = int(search_conc)

    ecom_conc = inquirer.number(
        message="E-commerce check concurrency:",
        default=settings.ecommerce_concurrency,
        min_allowed=1,
        max_allowed=50,
    ).execute()
    settings.ecommerce_concurrency = int(ecom_conc)

    console.print("[green]✓ Concurrency settings updated[/green]")


def _configure_outreach():
    """Configure outreach LLM settings."""
    console.print()

    provider = inquirer.select(
        message="Select LLM provider for outreach generation:",
        choices=[
            {"name": "OpenAI (GPT-4o, GPT-4o-mini)", "value": "openai"},
            {"name": "Anthropic (Claude Sonnet, Claude Haiku)", "value": "anthropic"},
        ],
        default=settings.outreach.llm_provider,
    ).execute()
    settings.outreach.llm_provider = provider

    if provider == "openai":
        model_choices = [
            {"name": "gpt-4o (recommended)", "value": "gpt-4o"},
            {"name": "gpt-4o-mini (faster, cheaper)", "value": "gpt-4o-mini"},
        ]
    else:
        model_choices = [
            {"name": "claude-sonnet-4-5-20250929 (recommended)", "value": "claude-sonnet-4-5-20250929"},
            {"name": "claude-haiku-4-5-20251001 (faster, cheaper)", "value": "claude-haiku-4-5-20251001"},
        ]

    model = inquirer.select(
        message="Select model:",
        choices=model_choices,
        default=settings.outreach.llm_model,
    ).execute()
    settings.outreach.llm_model = model

    # Verify API key
    if provider == "openai" and not settings.openai_api_key:
        console.print("[yellow]Warning: OPENAI_API_KEY not set in .env[/yellow]")
    elif provider == "anthropic" and not settings.anthropic_api_key:
        console.print("[yellow]Warning: ANTHROPIC_API_KEY not set in .env[/yellow]")

    console.print(f"[green]✓ Outreach settings updated: {provider} / {model}[/green]")


def _show_api_help():
    """Show API key setup instructions."""
    console.print()
    console.print(Panel(
        "[bold]API Key Setup[/bold]\n\n"
        "Create a [cyan].env[/cyan] file in the lead-generator directory with:\n\n"
        "[dim]# Required[/dim]\n"
        "GOOGLE_PLACES_API_KEY=your_key\n"
        "FIRECRAWL_API_KEY=your_key\n\n"
        "[dim]# Optional[/dim]\n"
        "OPENAI_API_KEY=your_key      [dim]# For LLM disambiguation[/dim]\n"
        "ANTHROPIC_API_KEY=your_key   [dim]# For outreach generation with Claude[/dim]\n"
        "APOLLO_API_KEY=your_key      [dim]# For paid enrichment[/dim]\n\n"
        "[bold]Get API keys:[/bold]\n"
        "• Google Places: [link]https://console.cloud.google.com/[/link]\n"
        "• Firecrawl: [link]https://firecrawl.dev/[/link]\n"
        "• OpenAI: [link]https://platform.openai.com/[/link]\n"
        "• Anthropic: [link]https://console.anthropic.com/[/link]\n"
        "• Apollo: [link]https://app.apollo.io/[/link]",
        title="Setup Instructions",
        border_style="blue",
    ))
    inquirer.confirm(message="Press Enter to continue...", default=True).execute()


def _interactive_new_run():
    """Run the full interactive pipeline setup with back navigation."""
    console.print()
    nav.push("new_run")

    vertical_list = None
    country_list = None

    # Step 1: Verticals
    while True:
        console.print("[bold cyan]Step 1:[/bold cyan] Select retail verticals to search\n")

        vertical_choices = [{"name": VERTICALS[k], "value": k} for k in VERTICALS]
        vertical_choices.append(Separator())
        vertical_choices.append({"name": MAIN_MENU_OPTION, "value": "main_menu"})

        result = inquirer.checkbox(
            message="Select verticals (Space to select, Enter to confirm):",
            choices=vertical_choices,
            instruction="(↑↓ navigate, Space select, Enter confirm)",
        ).execute()

        if "main_menu" in result:
            nav.clear()
            return

        vertical_list = [v for v in result if v != "main_menu"]
        if not vertical_list:
            console.print("[red]No verticals selected. Please select at least one.[/red]")
            continue

        break

    # Step 2: Countries
    while True:
        console.print("\n[bold cyan]Step 2:[/bold cyan] Select countries to search\n")

        country_choices = [{"name": COUNTRIES[k], "value": k} for k in COUNTRIES]
        country_choices.append(Separator())
        country_choices.append({"name": BACK_OPTION, "value": "back"})
        country_choices.append({"name": MAIN_MENU_OPTION, "value": "main_menu"})

        result = inquirer.checkbox(
            message="Select countries (Space to select, Enter to confirm):",
            choices=country_choices,
            instruction="(↑↓ navigate, Space select, Enter confirm)",
        ).execute()

        if "main_menu" in result:
            nav.clear()
            return

        if "back" in result:
            # Go back to step 1 by restarting the function
            nav.clear()
            return _interactive_new_run()

        country_list = [c for c in result if c not in ("back", "main_menu")]
        if not country_list:
            console.print("[red]No countries selected. Please select at least one.[/red]")
            continue

        break

    # Normalize
    country_list = ["canada" if c == "ca" else c for c in country_list]

    # Step 3: Advanced settings
    console.print("\n[bold cyan]Step 3:[/bold cyan] Advanced settings\n")

    enrichment_choice = inquirer.select(
        message="Select contact enrichment provider:",
        choices=[
            {"name": "LinkedIn (free, web scraping)", "value": "linkedin"},
            {"name": "Apollo.io (paid, requires API key)", "value": "apollo"},
            {"name": "Skip enrichment", "value": "skip"},
            Separator(),
            {"name": BACK_OPTION, "value": "back"},
            {"name": MAIN_MENU_OPTION, "value": "main_menu"},
        ],
        default="linkedin",
    ).execute()

    if enrichment_choice == "main_menu":
        nav.clear()
        return

    if enrichment_choice == "back":
        nav.clear()
        return _interactive_new_run()

    if enrichment_choice == "skip":
        settings.enrichment.enabled = False
    else:
        settings.enrichment.provider = enrichment_choice

    verify_choice = inquirer.confirm(
        message="Enable email verification? (checks MX records)",
        default=False,
    ).execute()

    if verify_choice:
        settings.email_verification.enabled = True
        settings.email_verification.verify_smtp = inquirer.confirm(
            message="Enable SMTP verification? (slower, may be blocked)",
            default=False,
        ).execute()
        settings.email_verification.include_risky = inquirer.confirm(
            message="Include risky emails? (catch-all domains)",
            default=False,
        ).execute()

    # Step 4: Confirmation
    show_summary(vertical_list, country_list)

    confirm_choices = [
        {"name": "✅ Yes, start the pipeline", "value": "start"},
        {"name": "❌ No, cancel", "value": "cancel"},
        Separator(),
        {"name": BACK_OPTION, "value": "back"},
        {"name": MAIN_MENU_OPTION, "value": "main_menu"},
    ]

    confirm = inquirer.select(
        message="Start the pipeline?",
        choices=confirm_choices,
    ).execute()

    if confirm == "main_menu":
        nav.clear()
        return

    if confirm == "back":
        nav.clear()
        return _interactive_new_run()

    if confirm == "cancel":
        console.print("[yellow]Cancelled.[/yellow]")
        nav.clear()
        return

    console.print()
    console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

    try:
        pipeline = Pipeline()
        output_file = asyncio.run(pipeline.run(verticals=vertical_list, countries=country_list))

        console.print()
        console.print(Panel(
            f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
            f"Output saved to:\n[cyan]{output_file}[/cyan]",
            title="Success",
            border_style="green",
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted. Progress saved to checkpoint.[/yellow]")
    finally:
        nav.clear()


def _interactive_resume_run(pipeline: Pipeline, checkpoints: list):
    """Resume from a checkpoint."""
    console.print()
    show_checkpoint_table(checkpoints)

    choices = [{"name": "Cancel", "value": None}]
    for i, cp in enumerate(checkpoints):
        vert_names = [VERTICALS.get(v, v).split(" (")[0] for v in cp["verticals"]]
        label = f"Stage {cp['stage']} ({cp['stage_name']}) - {', '.join(vert_names)}"
        choices.insert(0, {"name": label, "value": cp["path"]})

    selection = inquirer.select(
        message="Select checkpoint to resume:",
        choices=choices,
    ).execute()

    if not selection:
        return

    console.print()
    console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

    try:
        output_file = asyncio.run(pipeline.run(resume_checkpoint=selection))
        console.print()
        console.print(Panel(
            f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
            f"Output saved to:\n[cyan]{output_file}[/cyan]",
            title="Success",
            border_style="green",
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted. Progress saved to checkpoint.[/yellow]")


def _interactive_results():
    """Interactive results browser."""
    import pandas as pd

    nav.push("results")

    output_dirs = [Path("output"), Path("data/output")]
    csv_files = []
    for output_dir in output_dirs:
        csv_files.extend(output_dir.glob("leads_*.csv"))

    if not csv_files:
        console.print("[yellow]No results found.[/yellow]")
        nav.pop()
        return

    csv_files = sorted(csv_files, key=lambda p: p.stat().st_mtime, reverse=True)

    # Select file if multiple
    if len(csv_files) > 1:
        file_choices = [
            {"name": f"{p.name} ({format_timestamp(datetime.fromtimestamp(p.stat().st_mtime).isoformat())})", "value": p}
            for p in csv_files[:10]
        ]
        csv_path = inquirer.select(
            message="Select results file:",
            choices=file_choices,
        ).execute()
    else:
        csv_path = csv_files[0]

    df = pd.read_csv(csv_path)
    console.print(f"\n[bold]Loaded:[/bold] {csv_path.name} ({len(df)} leads)\n")

    while True:
        action = inquirer.select(
            message="What would you like to do?",
            choices=[
                {"name": "📋 Browse leads (select to view details)", "value": "browse"},
                {"name": "📊 View table (with contact indicators)", "value": "view"},
                {"name": "🔍 Select columns to display", "value": "columns"},
                {"name": "🔎 Filter by column", "value": "filter"},
                {"name": "↕️  Sort by column", "value": "sort"},
                {"name": "💾 Export filtered results", "value": "export"},
                Separator(),
                {"name": BACK_OPTION, "value": "back"},
                {"name": MAIN_MENU_OPTION, "value": "main_menu"},
            ],
        ).execute()

        if action == "back":
            nav.pop()
            return "back"

        if action == "main_menu":
            nav.clear()
            return "main_menu"

        if action == "browse":
            _browse_leads_interactive(df)

        elif action == "view":
            _display_leads_table(df, limit=20)

        elif action == "columns":
            cols = inquirer.checkbox(
                message="Select columns:",
                choices=[{"name": c, "value": c} for c in df.columns],
            ).execute()
            if cols:
                _display_leads_table(df[cols], limit=20)

        elif action == "filter":
            col = inquirer.select(
                message="Filter by column:",
                choices=[{"name": c, "value": c} for c in df.columns],
            ).execute()

            unique_vals = df[col].dropna().unique()
            if len(unique_vals) <= 15:
                val = inquirer.select(
                    message=f"Select {col} value:",
                    choices=[{"name": str(v), "value": str(v)} for v in unique_vals],
                ).execute()
            else:
                val = inquirer.text(message=f"Search in {col}:").execute()

            mask = df[col].astype(str).str.lower().str.contains(val.lower(), na=False)
            filtered = df[mask]
            console.print(f"\n[dim]Found {len(filtered)} matching leads[/dim]\n")
            _display_leads_table(filtered, limit=20)

        elif action == "sort":
            col = inquirer.select(
                message="Sort by column:",
                choices=[{"name": c, "value": c} for c in df.columns],
            ).execute()
            order = inquirer.select(
                message="Order:",
                choices=[
                    {"name": "Ascending", "value": True},
                    {"name": "Descending", "value": False},
                ],
            ).execute()
            sorted_df = df.sort_values(col, ascending=order)
            _display_leads_table(sorted_df, limit=20)

        elif action == "export":
            filename = inquirer.text(
                message="Export filename:",
                default="filtered_leads.csv",
            ).execute()
            df.to_csv(filename, index=False)
            console.print(f"[green]✓ Exported {len(df)} leads to {filename}[/green]\n")


def _browse_leads_interactive(df):
    """Browse leads with arrow keys, Enter to select and view details."""
    import pandas as pd

    current_page = 0
    page_size = 15
    total_leads = len(df)
    total_pages = (total_leads + page_size - 1) // page_size

    while True:
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_leads)
        page_df = df.iloc[start_idx:end_idx]

        # Build choices for this page
        choices = []
        for i, (_, row) in enumerate(page_df.iterrows()):
            idx = start_idx + i
            brand = str(row.get('brand_name', 'Unknown'))[:28]
            website = str(row.get('website', ''))[:30]
            locs = row.get('location_count', '?')

            # Build fixed-width status indicators (4 chars each: icon + space)
            # E=has emails, C=has contacts only, L=LinkedIn, P=platform
            contact_count = 0
            email_count = 0
            for j in range(1, 5):
                if pd.notna(row.get(f'contact_{j}_name')) and str(row.get(f'contact_{j}_name')).strip():
                    contact_count += 1
                    if pd.notna(row.get(f'contact_{j}_email')) and str(row.get(f'contact_{j}_email')).strip():
                        email_count += 1

            # Use single-char indicators for consistent width
            e_flag = f"E{email_count}" if email_count > 0 else ("C" + str(contact_count) if contact_count > 0 else "--")
            l_flag = "L" if pd.notna(row.get('linkedin_company')) and str(row.get('linkedin_company')).strip() else "-"
            p_flag = "P" if pd.notna(row.get('ecommerce_platform')) and str(row.get('ecommerce_platform')).strip() else "-"

            # Fixed format: [E2 L P] or [-- - -]
            status = f"[{e_flag:>2} {l_flag} {p_flag}]"

            label = f"{idx+1:3}. {status} {brand:<28} {locs:>2} locs  {website}"
            choices.append({"name": label, "value": idx})

        # Add navigation options
        choices.append({"name": "─" * 60, "value": "separator"})

        if current_page > 0:
            choices.append({"name": f"⬅️  Previous page ({current_page}/{total_pages})", "value": "prev_page"})

        if current_page < total_pages - 1:
            choices.append({"name": f"➡️  Next page ({current_page + 2}/{total_pages})", "value": "next_page"})

        choices.append({"name": "🔢 Jump to lead #", "value": "jump"})
        choices.append({"name": "← Back to menu", "value": "back"})

        console.print(f"\n[dim]Page {current_page + 1} of {total_pages} ({total_leads} leads) | [En=emails Cn=contacts L=LinkedIn P=platform][/dim]")

        selected = inquirer.select(
            message="Select a lead (↑↓ scroll, Enter to view):",
            choices=choices,
            instruction="",
        ).execute()

        if selected == "back":
            break
        elif selected == "separator":
            continue
        elif selected == "prev_page":
            current_page = max(0, current_page - 1)
        elif selected == "next_page":
            current_page = min(total_pages - 1, current_page + 1)
        elif selected == "jump":
            jump_to = inquirer.number(
                message=f"Go to lead # (1-{total_leads}):",
                min_allowed=1,
                max_allowed=total_leads,
                default=1,
            ).execute()
            lead_idx = int(jump_to) - 1
            # Jump to that lead's page and show details
            current_page = lead_idx // page_size
            _display_lead_details(df, lead_idx, allow_navigation=True)
        elif isinstance(selected, int):
            # User selected a lead - show details with navigation
            new_idx = _display_lead_details(df, selected, allow_navigation=True)
            # Update page to show where user ended up
            current_page = new_idx // page_size


def _display_leads_table(df, limit: int = 20, columns: list = None, show_contacts: bool = False, allow_selection: bool = False):
    """Display a DataFrame as a rich table with optional lead selection."""
    import pandas as pd

    if columns:
        df_display = df[columns].copy()
    else:
        # Default columns with contact info indicators
        default_cols = ["brand_name", "website", "location_count", "has_ecommerce"]
        available = [c for c in default_cols if c in df.columns]
        df_display = df[available].copy() if available else df.iloc[:, :5].copy()

        # Add contact indicators
        if "linkedin_company" in df.columns:
            df_display["company_linkedin"] = df["linkedin_company"].apply(
                lambda x: "✓" if pd.notna(x) and str(x).strip() else "✗"
            )

        if "contact_1_name" in df.columns:
            def count_contacts(row):
                count = 0
                for i in range(1, 5):
                    if pd.notna(row.get(f"contact_{i}_name")):
                        count += 1
                return f"{count} contacts" if count > 0 else "None"
            df_display["contacts"] = df.apply(count_contacts, axis=1)

    # Add row numbers for selection
    if allow_selection:
        df_display.insert(0, "#", range(1, len(df_display) + 1))

    table = Table(title=f"Leads ({min(limit, len(df))} of {len(df)})", box=box.ROUNDED)

    for col in df_display.columns:
        style = "cyan" if col in ("brand_name", "company_name") else None
        if col == "contacts":
            style = "green"
        elif col == "company_linkedin":
            style = "blue"
        elif col == "#":
            style = "dim"
        table.add_column(col, style=style)

    for idx, (_, row) in enumerate(df_display.head(limit).iterrows()):
        table.add_row(*[str(v) if pd.notna(v) else "" for v in row])

    console.print(table)

    if allow_selection:
        console.print(f"\n[dim]Enter a number (1-{min(limit, len(df))}) to view details, or press Enter to go back[/dim]")
        return df.head(limit)  # Return the displayed subset for selection
    else:
        console.print(f"\n[dim]Available columns: {', '.join(df.columns)}[/dim]\n")
        return None


def _display_lead_details(df, row_idx: int, allow_navigation: bool = True):
    """Display detailed information about a single lead with navigation."""
    import pandas as pd

    current_idx = row_idx
    total_leads = len(df)

    while True:
        row = df.iloc[current_idx]

        console.print()
        console.print(Panel(
            f"[bold cyan]{row.get('brand_name', 'Unknown')}[/bold cyan]\n"
            f"[dim]Lead {current_idx + 1} of {total_leads}[/dim]",
            title="Lead Details",
            border_style="blue",
        ))

        # Basic info
        info_table = Table(box=box.SIMPLE, show_header=False)
        info_table.add_column("Field", style="dim")
        info_table.add_column("Value")

        info_table.add_row("Website", str(row.get("website", "")))
        info_table.add_row("Locations", str(row.get("location_count", "")))
        info_table.add_row("E-commerce", "Yes" if row.get("has_ecommerce") else "No")

        if pd.notna(row.get("ecommerce_platform")) and str(row.get("ecommerce_platform")).strip():
            platform = str(row.get("ecommerce_platform")).title()
            info_table.add_row("Platform", f"[bold magenta]{platform}[/bold magenta]")

        # Apollo enrichment data
        if pd.notna(row.get("industry")) and str(row.get("industry")).strip():
            info_table.add_row("Industry", f"[cyan]{row.get('industry')}[/cyan]")

        if pd.notna(row.get("employee_count")) and str(row.get("employee_count")).strip():
            info_table.add_row("Employees", f"[green]{row.get('employee_count'):,}[/green]" if isinstance(row.get("employee_count"), (int, float)) else str(row.get("employee_count")))

        if pd.notna(row.get("cities")):
            info_table.add_row("Cities", str(row.get("cities", ""))[:60])

        if pd.notna(row.get("linkedin_company")):
            info_table.add_row("Company LinkedIn", str(row.get("linkedin_company", "")))

        if pd.notna(row.get("marketplaces")):
            info_table.add_row("Marketplaces", str(row.get("marketplaces", "")))

        console.print(info_table)

        # Store Locations section
        if pd.notna(row.get("addresses")) and str(row.get("addresses")).strip():
            console.print("\n[bold]Store Locations:[/bold]")
            addresses_str = str(row.get("addresses", ""))
            addresses = [addr.strip() for addr in addresses_str.split("|") if addr.strip()]

            addr_table = Table(box=box.SIMPLE, show_header=False)
            addr_table.add_column("", style="dim", width=3)
            addr_table.add_column("Address")

            for i, addr in enumerate(addresses[:10], 1):  # Limit to 10 addresses in display
                addr_table.add_row(f"{i}.", addr)

            if len(addresses) > 10:
                addr_table.add_row("", f"[dim]... and {len(addresses) - 10} more locations[/dim]")

            console.print(addr_table)

        # Contacts
        has_contacts = False
        for i in range(1, 5):
            name = row.get(f"contact_{i}_name")
            if pd.notna(name):
                has_contacts = True
                break

        if has_contacts:
            console.print("\n[bold]Contacts:[/bold]")
            contact_table = Table(box=box.ROUNDED)
            contact_table.add_column("Name", style="cyan")
            contact_table.add_column("Title")
            contact_table.add_column("Email", style="green")
            contact_table.add_column("Phone", style="yellow")
            contact_table.add_column("LinkedIn")

            for i in range(1, 5):
                name = row.get(f"contact_{i}_name")
                if pd.notna(name) and str(name).strip():
                    title = row.get(f"contact_{i}_title", "")
                    email = row.get(f"contact_{i}_email", "")
                    phone = row.get(f"contact_{i}_phone", "")
                    linkedin = row.get(f"contact_{i}_linkedin", "")
                    contact_table.add_row(
                        str(name),
                        str(title) if pd.notna(title) else "",
                        str(email) if pd.notna(email) and str(email).strip() else "[dim]-[/dim]",
                        str(phone) if pd.notna(phone) and str(phone).strip() else "[dim]-[/dim]",
                        str(linkedin)[:40] + "..." if pd.notna(linkedin) and len(str(linkedin)) > 40 else (str(linkedin) if pd.notna(linkedin) else "")
                    )

            console.print(contact_table)
        else:
            console.print("\n[dim]No contacts found for this lead[/dim]")

        if not allow_navigation:
            console.print()
            inquirer.confirm(message="Press Enter to continue...", default=True).execute()
            return current_idx

        # Navigation options
        nav_choices = []

        # Apollo enrichment option
        has_contacts = any(
            pd.notna(row.get(f"contact_{j}_name")) and str(row.get(f"contact_{j}_name")).strip()
            for j in range(1, 5)
        )
        if has_contacts:
            nav_choices.append({"name": "🔄 Re-enrich with Apollo", "value": "apollo"})
        else:
            nav_choices.append({"name": "🚀 Enrich with Apollo", "value": "apollo"})

        # Outreach generation option
        brand_name = str(row.get("brand_name", "Unknown"))
        outreach_gen = OutreachGenerator()
        has_outreach = outreach_gen.has_cached_outreach(brand_name)

        if has_outreach:
            nav_choices.append({"name": "✉️  View outreach messages", "value": "outreach"})
        else:
            nav_choices.append({"name": "✉️  Generate outreach", "value": "outreach"})

        if current_idx > 0:
            nav_choices.append({"name": "⬅️  Previous lead", "value": "prev"})

        if current_idx < total_leads - 1:
            nav_choices.append({"name": "➡️  Next lead", "value": "next"})

        nav_choices.append({"name": "🔢 Jump to lead #", "value": "jump"})
        nav_choices.append({"name": "← Back to list", "value": "back"})

        console.print()
        action = inquirer.select(
            message=f"Navigate ({current_idx + 1}/{total_leads}):",
            choices=nav_choices,
        ).execute()

        if action == "back":
            return current_idx
        elif action == "apollo":
            _enrich_single_lead(df, current_idx)
        elif action == "outreach":
            _outreach_flow(row)
        elif action == "prev" and current_idx > 0:
            current_idx -= 1
        elif action == "next" and current_idx < total_leads - 1:
            current_idx += 1
        elif action == "jump":
            jump_to = inquirer.number(
                message=f"Go to lead # (1-{total_leads}):",
                min_allowed=1,
                max_allowed=total_leads,
                default=current_idx + 1,
            ).execute()
            current_idx = int(jump_to) - 1


def _enrich_single_lead(df, row_idx: int):
    """Enrich a single lead with Apollo and update the DataFrame in-place."""
    import pandas as pd
    from src.apollo_enrich import ApolloEnricher

    row = df.iloc[row_idx]
    brand_name = str(row.get("brand_name", "Unknown"))
    website = str(row.get("website", ""))

    if not website or website == "nan":
        console.print("\n[yellow]No website for this lead — cannot enrich.[/yellow]")
        return

    if not settings.apollo_api_key:
        console.print("\n[red]APOLLO_API_KEY not set in .env[/red]")
        console.print("[dim]Get your key at: https://app.apollo.io/[/dim]")
        return

    console.print(f"\n[cyan]Enriching {brand_name}...[/cyan]")

    async def _do_enrich():
        enricher = ApolloEnricher(api_key=settings.apollo_api_key)
        return await enricher.enrich(brand_name, website, max_contacts=4)

    try:
        result = asyncio.get_event_loop().run_until_complete(_do_enrich())
    except RuntimeError:
        result = asyncio.run(_do_enrich())

    if not result:
        console.print("[yellow]No data found on Apollo for this company.[/yellow]")
        return

    # Ensure contact columns exist as string type (pandas may infer them as numeric)
    contact_cols = []
    for i in range(1, 5):
        for suffix in ("name", "title", "email", "phone", "linkedin"):
            contact_cols.append(f"contact_{i}_{suffix}")
    for col in contact_cols + ["linkedin_company", "industry"]:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].astype(object)

    # Update DataFrame in-place
    idx = df.index[row_idx]
    if result.company.linkedin_url:
        df.at[idx, "linkedin_company"] = result.company.linkedin_url
    if result.company.industry:
        df.at[idx, "industry"] = result.company.industry
    if result.company.employee_count:
        df.at[idx, "employee_count"] = result.company.employee_count

    contact_count = 0
    email_count = 0
    for i, contact in enumerate(result.contacts[:4], 1):
        df.at[idx, f"contact_{i}_name"] = contact.name
        df.at[idx, f"contact_{i}_title"] = contact.title
        df.at[idx, f"contact_{i}_email"] = contact.email or ""
        df.at[idx, f"contact_{i}_phone"] = contact.phone or ""
        df.at[idx, f"contact_{i}_linkedin"] = contact.linkedin_url or ""
        contact_count += 1
        if contact.email:
            email_count += 1

    if contact_count > 0:
        console.print(f"[green]✓ Found {contact_count} contacts ({email_count} with email)[/green]")
    else:
        console.print("[yellow]Company found but no contacts matched target titles.[/yellow]")


def _outreach_flow(lead_row):
    """Outreach generation and viewing flow for a single lead."""
    import pandas as pd

    brand_name = str(lead_row.get("brand_name", "Unknown"))
    gen = OutreachGenerator()

    # Check for cached messages
    cached = gen.load_cached_outreach(brand_name)

    if cached:
        # Show existing messages
        _display_outreach_messages(cached, brand_name)

        action = inquirer.select(
            message="What would you like to do?",
            choices=[
                {"name": "🔄 Regenerate all messages", "value": "regen_all"},
                {"name": "✏️  Regenerate with instructions", "value": "regen_guided"},
                {"name": "🎯 Regenerate specific message", "value": "regen_single"},
                Separator(),
                {"name": "← Back to lead", "value": "back"},
            ],
        ).execute()

        if action == "back":
            return

        if action == "regen_all":
            _do_generate(gen, lead_row, brand_name)

        elif action == "regen_guided":
            instructions = inquirer.text(
                message="Enter instructions (e.g. 'make it shorter', 'more casual tone'):",
            ).execute()
            if instructions.strip():
                _do_generate(gen, lead_row, brand_name, instructions=instructions)

        elif action == "regen_single":
            msg_type = inquirer.select(
                message="Which message to regenerate?",
                choices=[
                    {"name": heading, "value": key}
                    for key, heading in MESSAGE_TYPES.items()
                ],
            ).execute()

            instructions = inquirer.text(
                message="Instructions (optional, press Enter to skip):",
                default="",
            ).execute()

            with console.status(f"[bold cyan]Regenerating {MESSAGE_TYPES[msg_type]}..."):
                try:
                    messages = gen.regenerate_single(
                        lead_row,
                        message_type=msg_type,
                        instructions=instructions if instructions.strip() else None,
                    )
                    console.print(f"[green]✓ Regenerated {MESSAGE_TYPES[msg_type]}[/green]\n")
                    _display_outreach_messages(messages, brand_name)
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
    else:
        # No cached messages — generate new ones
        _do_generate(gen, lead_row, brand_name)


def _do_generate(gen: OutreachGenerator, lead_row, brand_name: str, instructions: str = None):
    """Run the generation flow: pick mode, template, contact, generate."""
    import pandas as pd

    # Pick mode
    mode = inquirer.select(
        message="Generation mode:",
        choices=[
            {"name": "📝 Template-guided (follows your template's style)", "value": "template"},
            {"name": "✨ Free-form (original copy from lead data)", "value": "freeform"},
        ],
    ).execute()

    template_name = None
    if mode == "template":
        templates = gen.list_templates()
        if not templates:
            console.print("[yellow]No templates found in templates/ directory. Using free-form mode.[/yellow]")
        else:
            template_choices = [
                {"name": f"{t['name']} — {t['title']}", "value": t["name"]}
                for t in templates
            ]
            template_name = inquirer.select(
                message="Select template:",
                choices=template_choices,
            ).execute()

    # Pick contact if multiple
    contact_index = 1
    contacts = []
    for i in range(1, 5):
        name = lead_row.get(f"contact_{i}_name")
        if pd.notna(name) and str(name).strip():
            title = lead_row.get(f"contact_{i}_title", "")
            title_str = f" ({title})" if pd.notna(title) and str(title).strip() else ""
            contacts.append({"name": f"{name}{title_str}", "value": i})

    if len(contacts) > 1:
        contact_index = inquirer.select(
            message="Generate for which contact?",
            choices=contacts,
        ).execute()
    elif len(contacts) == 0:
        console.print("[yellow]No contacts found for this lead. Using placeholder.[/yellow]")

    # Generate
    with console.status("[bold cyan]Generating outreach messages..."):
        try:
            if instructions:
                messages = gen.regenerate(
                    lead_row,
                    template_name=template_name,
                    contact_index=contact_index,
                    instructions=instructions,
                )
            else:
                messages = gen.generate(
                    lead_row,
                    template_name=template_name,
                    contact_index=contact_index,
                )

                # Save to cache
                contact_name = str(lead_row.get(f"contact_{contact_index}_name", "Unknown"))
                from src.config import settings
                gen.save_outreach(
                    brand_name,
                    messages,
                    template_name or "free-form",
                    contact_name,
                    settings.outreach.llm_model,
                )

            console.print("[green]✓ Messages generated and saved[/green]\n")
            _display_outreach_messages(messages, brand_name)

        except Exception as e:
            console.print(f"[red]Error generating outreach: {e}[/red]")
            console.print("[dim]Check your API key and LLM provider settings.[/dim]")


def _display_outreach_messages(messages: dict[str, str], brand_name: str):
    """Display outreach messages in Rich panels."""
    console.print()
    for msg_type, heading in MESSAGE_TYPES.items():
        content = messages.get(msg_type)
        if content:
            console.print(Panel(
                content,
                title=f"[bold]{heading}[/bold]",
                subtitle=brand_name,
                border_style="cyan",
                padding=(1, 2),
            ))
            console.print()


def _interactive_enrich():
    """Enrich existing leads CSV with Apollo contact data."""
    import pandas as pd

    nav.push("enrich")

    # Check API key first
    if not settings.apollo_api_key:
        console.print()
        console.print(Panel(
            "[bold red]APOLLO_API_KEY not set[/bold red]\n\n"
            "To enrich leads with contacts, set APOLLO_API_KEY in your .env file.\n"
            "Get your key at: [link]https://app.apollo.io/[/link]",
            title="API Key Required",
            border_style="red",
        ))
        nav.pop()
        return

    # Find CSV files
    output_dirs = [Path("output"), Path("data/output")]
    csv_files = []
    for output_dir in output_dirs:
        csv_files.extend(output_dir.glob("leads_*.csv"))

    if not csv_files:
        console.print("[yellow]No leads files found. Run the pipeline first.[/yellow]")
        nav.pop()
        return

    csv_files = sorted(csv_files, key=lambda p: p.stat().st_mtime, reverse=True)

    # Select file
    file_choices = [
        {"name": f"{p.name} ({format_timestamp(datetime.fromtimestamp(p.stat().st_mtime).isoformat())})", "value": p}
        for p in csv_files[:10]
    ]
    file_choices.append({"name": "← Back", "value": "back"})

    console.print()
    selected = inquirer.select(
        message="Select leads file to enrich:",
        choices=file_choices,
    ).execute()

    if selected == "back":
        nav.pop()
        return

    csv_path = selected

    # Show preview
    try:
        df = pd.read_csv(csv_path)
        has_contacts = any(
            df.get(f"contact_1_name", pd.Series()).notna().any()
            for _ in [1]
            if f"contact_1_name" in df.columns
        )

        console.print(f"\n  [bold]File:[/bold] {csv_path.name}")
        console.print(f"  [bold]Leads:[/bold] {len(df)}")
        if has_contacts:
            console.print(f"  [yellow]Note: This file already has some contact data. Existing contacts will be updated.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        nav.pop()
        return

    # Confirm
    confirm = inquirer.confirm(
        message=f"Enrich {len(df)} leads with Apollo? (uses API credits)",
        default=True,
    ).execute()

    if not confirm:
        nav.pop()
        return

    console.print()
    console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

    try:
        pipeline = Pipeline()
        output_file = asyncio.run(pipeline.enrich_csv(str(csv_path)))
        console.print()
        console.print(Panel(
            f"[bold green]Enrichment complete![/bold green]\n\n"
            f"Output saved to:\n[cyan]{output_file}[/cyan]",
            title="Success",
            border_style="green",
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Enrichment interrupted.[/yellow]")
    finally:
        nav.pop()


def _interactive_stats():
    """Show statistics interactively."""
    import pandas as pd

    output_dirs = [Path("output"), Path("data/output")]
    csv_files = []
    for output_dir in output_dirs:
        csv_files.extend(output_dir.glob("leads_*.csv"))

    if not csv_files:
        console.print("[yellow]No results found.[/yellow]")
        return

    csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
    df = pd.read_csv(csv_path)

    console.print(f"\n[bold]Results:[/bold] {csv_path.name}\n")

    stats_table = Table(title="Lead Statistics", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green")

    stats_table.add_row("Total Leads", str(len(df)))

    if "has_ecommerce" in df.columns:
        ecom = (df["has_ecommerce"] == True).sum()
        stats_table.add_row("With E-commerce", str(int(ecom)))

    if "location_count" in df.columns:
        stats_table.add_row("Avg Locations", f"{df['location_count'].mean():.1f}")

    if "cities" in df.columns:
        # Count unique cities across all leads
        all_cities = set()
        for cities_str in df["cities"].dropna():
            all_cities.update(c.strip() for c in str(cities_str).split(","))
        stats_table.add_row("Cities Covered", str(len(all_cities)))

    # Company LinkedIn stats
    if "linkedin_company" in df.columns:
        with_linkedin = df["linkedin_company"].notna().sum()
        pct = (with_linkedin / len(df)) * 100 if len(df) > 0 else 0
        stats_table.add_row("With Company LinkedIn", f"{with_linkedin} ({pct:.0f}%)")

    # Contact stats
    if "contact_1_name" in df.columns:
        with_any_contact = df["contact_1_name"].notna().sum()
        pct = (with_any_contact / len(df)) * 100 if len(df) > 0 else 0
        stats_table.add_row("With Contacts", f"{with_any_contact} ({pct:.0f}%)")

        # Count total contacts
        total_contacts = 0
        for i in range(1, 5):
            col = f"contact_{i}_name"
            if col in df.columns:
                total_contacts += df[col].notna().sum()
        stats_table.add_row("Total Contacts Found", str(total_contacts))

    # E-commerce platform stats
    if "ecommerce_platform" in df.columns:
        with_platform = df["ecommerce_platform"].notna() & (df["ecommerce_platform"] != "")
        platform_count = with_platform.sum()
        pct = (platform_count / len(df)) * 100 if len(df) > 0 else 0
        stats_table.add_row("With Platform Detected", f"{platform_count} ({pct:.0f}%)")

    console.print(stats_table)

    # Platform breakdown if available
    if "ecommerce_platform" in df.columns:
        platform_counts = df["ecommerce_platform"].dropna()
        platform_counts = platform_counts[platform_counts != ""]
        if len(platform_counts) > 0:
            console.print("\n[bold]E-commerce Platforms:[/bold]")
            platform_table = Table(box=box.SIMPLE)
            platform_table.add_column("Platform", style="magenta")
            platform_table.add_column("Count", justify="right")

            for platform, count in platform_counts.value_counts().items():
                platform_table.add_row(str(platform).title(), str(count))

            console.print(platform_table)

    # Top by location count
    if "brand_name" in df.columns and "location_count" in df.columns:
        console.print("\n[bold]Top Leads by Locations:[/bold]")
        top_table = Table(box=box.SIMPLE)
        top_table.add_column("Brand", style="cyan")
        top_table.add_column("Locations", justify="right")
        top_table.add_column("Website")

        for _, row in df.nlargest(10, "location_count").iterrows():
            top_table.add_row(
                str(row.get("brand_name", "")),
                str(row.get("location_count", "")),
                str(row.get("website", ""))[:40]
            )

        console.print(top_table)

    console.print()
    action = inquirer.select(
        message="What next?",
        choices=[
            {"name": BACK_OPTION, "value": "back"},
            {"name": MAIN_MENU_OPTION, "value": "main_menu"},
        ],
    ).execute()

    if action == "main_menu":
        nav.clear()
    # "back" just returns normally


def _interactive_checkpoints(pipeline: Pipeline):
    """Manage checkpoints interactively."""
    nav.push("checkpoints")
    checkpoints = pipeline.list_checkpoints()

    if not checkpoints:
        console.print("[yellow]No checkpoints found.[/yellow]")
        nav.pop()
        return

    console.print()
    show_checkpoint_table(checkpoints)

    action = inquirer.select(
        message="What would you like to do?",
        choices=[
            {"name": "Delete a checkpoint", "value": "delete"},
            {"name": "Delete all checkpoints", "value": "delete_all"},
            Separator(),
            {"name": BACK_OPTION, "value": "back"},
            {"name": MAIN_MENU_OPTION, "value": "main_menu"},
        ],
    ).execute()

    if action == "back":
        nav.pop()
        return "back"

    if action == "main_menu":
        nav.clear()
        return "main_menu"

    if action == "delete":
        choices = [
            {"name": f"#{i+1}: Stage {cp['stage']} - {format_timestamp(cp['timestamp'])}", "value": cp["path"]}
            for i, cp in enumerate(checkpoints)
        ]
        choices.append({"name": "Cancel", "value": None})

        to_delete = inquirer.select(message="Select checkpoint:", choices=choices).execute()
        if to_delete:
            pipeline.delete_checkpoint(to_delete)
            console.print("[green]✓ Checkpoint deleted[/green]")

    elif action == "delete_all":
        if Confirm.ask("[bold red]Delete all checkpoints?[/bold red]", default=False):
            for cp in checkpoints:
                pipeline.delete_checkpoint(cp["path"])
            console.print("[green]✓ All checkpoints deleted[/green]")


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

    # Enrichment settings
    if settings.enrichment.enabled:
        provider = settings.enrichment.provider.capitalize()
        table.add_row("Enrichment", f"{provider} (max {settings.enrichment.max_contacts} contacts)")
    else:
        table.add_row("Enrichment", "Disabled")

    # Email verification settings
    if settings.email_verification.enabled:
        verify_opts = ["MX records"]
        if settings.email_verification.verify_smtp:
            verify_opts.append("SMTP")
        if settings.email_verification.include_risky:
            verify_opts.append("include risky")
        table.add_row("Email Verification", ", ".join(verify_opts))
    else:
        table.add_row("Email Verification", "Disabled")

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
    enrichment_provider: str = typer.Option(
        None,
        "--enrichment", "-e",
        help="Enrichment provider: linkedin (free) or apollo (paid, requires API key)"
    ),
    verify_emails: Optional[bool] = typer.Option(
        None,
        "--verify-emails/--no-verify-emails",
        help="Enable email verification"
    ),
    verify_smtp: Optional[bool] = typer.Option(
        None,
        "--verify-smtp/--no-verify-smtp",
        help="Enable SMTP verification (slower, may be blocked)"
    ),
    include_risky: Optional[bool] = typer.Option(
        None,
        "--include-risky/--no-include-risky",
        help="Include catch-all/unknown emails"
    ),
):
    """Run the full lead generation pipeline."""
    show_banner()

    # Apply CLI overrides to settings
    if enrichment_provider is not None:
        if enrichment_provider not in ("linkedin", "apollo"):
            console.print(f"[red]Invalid enrichment provider: {enrichment_provider}. Use 'linkedin' or 'apollo'.[/red]")
            raise typer.Exit(1)
        settings.enrichment.provider = enrichment_provider
        console.print(f"[dim]Using enrichment provider: {enrichment_provider}[/dim]")

    if verify_emails is not None:
        settings.email_verification.enabled = verify_emails
        if verify_emails:
            console.print("[dim]Email verification enabled[/dim]")

    if verify_smtp is not None:
        settings.email_verification.verify_smtp = verify_smtp
        if verify_smtp:
            console.print("[dim]SMTP verification enabled[/dim]")

    if include_risky is not None:
        settings.email_verification.include_risky = include_risky

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

        # Interactive advanced settings
        console.print("\n[bold cyan]Step 3:[/bold cyan] Advanced settings\n")

        # Enrichment provider selection
        if enrichment_provider is None:
            enrichment_choice = inquirer.select(
                message="Select contact enrichment provider:",
                choices=[
                    {"name": "LinkedIn (free, web scraping)", "value": "linkedin"},
                    {"name": "Apollo.io (paid, requires API key)", "value": "apollo"},
                    {"name": "Skip enrichment", "value": "skip"},
                ],
                default="linkedin",
            ).execute()

            if enrichment_choice == "skip":
                settings.enrichment.enabled = False
            else:
                settings.enrichment.provider = enrichment_choice

        # Email verification settings
        if verify_emails is None:
            verify_choice = inquirer.confirm(
                message="Enable email verification? (checks MX records)",
                default=False,
            ).execute()

            if verify_choice:
                settings.email_verification.enabled = True

                # Ask about SMTP verification
                smtp_choice = inquirer.confirm(
                    message="Enable SMTP verification? (slower, may be blocked by some servers)",
                    default=False,
                ).execute()
                settings.email_verification.verify_smtp = smtp_choice

                # Ask about risky emails
                risky_choice = inquirer.confirm(
                    message="Include risky emails? (catch-all domains, unknown status)",
                    default=False,
                ).execute()
                settings.email_verification.include_risky = risky_choice

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
def enrich(
    file: str = typer.Argument(None, help="CSV file to enrich (or picks latest)"),
    max_contacts: int = typer.Option(4, "--max-contacts", "-n", help="Maximum contacts per company"),
):
    """Enrich an existing leads CSV with Apollo contact data."""
    show_banner()

    if not settings.apollo_api_key:
        console.print("[red]APOLLO_API_KEY not set in .env[/red]")
        console.print("[dim]Get your key at: https://app.apollo.io/[/dim]")
        raise typer.Exit(1)

    # Find file
    output_dirs = [Path("output"), Path("data/output")]

    if file:
        csv_path = Path(file)
        if not csv_path.exists():
            for output_dir in output_dirs:
                if (output_dir / file).exists():
                    csv_path = output_dir / file
                    break
    else:
        csv_files = []
        for output_dir in output_dirs:
            csv_files.extend(output_dir.glob("leads_*.csv"))

        if not csv_files:
            console.print("[yellow]No leads files found. Run the pipeline first.[/yellow]")
            raise typer.Exit(1)

        csv_files = sorted(csv_files, key=lambda p: p.stat().st_mtime, reverse=True)
        csv_path = csv_files[0]

    if not csv_path.exists():
        console.print(f"[red]File not found: {csv_path}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Enriching: {csv_path}[/dim]")
    console.print("[dim]Press Ctrl+C to interrupt[/dim]\n")

    try:
        pipeline = Pipeline()
        output_file = asyncio.run(pipeline.enrich_csv(str(csv_path), max_contacts))
        console.print()
        console.print(Panel(
            f"[bold green]Enrichment complete![/bold green]\n\n"
            f"Output saved to:\n[cyan]{output_file}[/cyan]",
            title="Success",
            border_style="green",
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Enrichment interrupted.[/yellow]")
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


@app.command()
def results(
    file: str = typer.Argument(None, help="CSV file to view (or picks latest)"),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive", "-i/-I",
        help="Run in interactive mode"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of rows to show"),
    columns: str = typer.Option(None, "--columns", "-c", help="Columns to show (comma-separated)"),
    sort_by: str = typer.Option(None, "--sort", "-s", help="Column to sort by"),
    filter_col: str = typer.Option(None, "--filter", "-f", help="Filter: column=value"),
    export: str = typer.Option(None, "--export", "-o", help="Export filtered results to new CSV"),
):
    """View and filter lead generation results."""
    import pandas as pd

    show_banner()

    # Check multiple possible output directories
    output_dirs = [Path("output"), Path("data/output")]

    # Find all CSV files
    csv_files = []
    for output_dir in output_dirs:
        csv_files.extend(output_dir.glob("leads_*.csv"))

    if not csv_files:
        console.print("[yellow]No results found.[/yellow]")
        console.print("[dim]Run the pipeline first to generate leads.[/dim]")
        raise typer.Exit(1)

    # Sort by modification time (newest first)
    csv_files = sorted(csv_files, key=lambda p: p.stat().st_mtime, reverse=True)

    # Interactive file selection
    if file:
        csv_path = Path(file)
        if not csv_path.exists():
            for output_dir in output_dirs:
                if (output_dir / file).exists():
                    csv_path = output_dir / file
                    break
    elif interactive and len(csv_files) > 1:
        file_choices = [
            {"name": f"{p.name} ({format_timestamp(datetime.fromtimestamp(p.stat().st_mtime).isoformat())})", "value": p}
            for p in csv_files[:10]  # Show up to 10 most recent
        ]
        csv_path = inquirer.select(
            message="Select results file:",
            choices=file_choices,
            default=csv_files[0],
        ).execute()
        console.print()
    else:
        csv_path = csv_files[0]
        console.print(f"[dim]Latest results: {csv_path.name}[/dim]\n")

    if not csv_path.exists():
        console.print(f"[red]File not found: {csv_path}[/red]")
        raise typer.Exit(1)

    # Load CSV
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        console.print(f"[red]Error reading CSV: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Total leads:[/bold] {len(df)}\n")

    # Interactive mode: let user choose columns and filters
    if interactive and not columns and not filter_col:
        # Ask what they want to do
        action = inquirer.select(
            message="What would you like to do?",
            choices=[
                {"name": "View all leads (default columns)", "value": "view"},
                {"name": "Select specific columns to display", "value": "columns"},
                {"name": "Filter leads by a column value", "value": "filter"},
                {"name": "Export to a new file", "value": "export"},
            ],
        ).execute()

        if action == "columns":
            # Let user pick columns
            col_choices = inquirer.checkbox(
                message="Select columns to display:",
                choices=[{"name": col, "value": col} for col in df.columns],
                instruction="(Space to select, Enter to confirm)",
            ).execute()
            if col_choices:
                columns = ",".join(col_choices)

        elif action == "filter":
            # Let user pick a column to filter
            filter_column = inquirer.select(
                message="Select column to filter:",
                choices=[{"name": col, "value": col} for col in df.columns],
            ).execute()

            # Show unique values if not too many
            unique_vals = df[filter_column].dropna().unique()
            if len(unique_vals) <= 20:
                filter_value = inquirer.select(
                    message=f"Select {filter_column} value:",
                    choices=[{"name": str(v), "value": str(v)} for v in unique_vals[:20]],
                ).execute()
            else:
                filter_value = inquirer.text(
                    message=f"Enter value to search in {filter_column}:",
                ).execute()

            filter_col = f"{filter_column}={filter_value}"

        elif action == "export":
            export = inquirer.text(
                message="Export filename:",
                default="filtered_leads.csv",
            ).execute()

        console.print()

    # Apply filter if specified
    if filter_col and "=" in filter_col:
        col, val = filter_col.split("=", 1)
        col = col.strip()
        val = val.strip()
        if col in df.columns:
            # Case-insensitive contains
            mask = df[col].astype(str).str.lower().str.contains(val.lower(), na=False)
            df = df[mask]
            console.print(f"[dim]Filtered by {col} containing '{val}': {len(df)} results[/dim]\n")
        else:
            console.print(f"[yellow]Column '{col}' not found. Available: {', '.join(df.columns)}[/yellow]")

    # Sort if specified
    if sort_by:
        if sort_by.startswith("-"):
            sort_col = sort_by[1:]
            ascending = False
        else:
            sort_col = sort_by
            ascending = True

        if sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=ascending)
        else:
            console.print(f"[yellow]Sort column '{sort_col}' not found.[/yellow]")

    # Select columns if specified
    if columns:
        col_list = [c.strip() for c in columns.split(",")]
        valid_cols = [c for c in col_list if c in df.columns]
        if valid_cols:
            df_display = df[valid_cols]
        else:
            console.print(f"[yellow]None of specified columns found. Available: {', '.join(df.columns)}[/yellow]")
            df_display = df
    else:
        # Default columns for display
        default_cols = ["company_name", "website", "city", "location_count", "has_ecommerce"]
        available_default = [c for c in default_cols if c in df.columns]
        df_display = df[available_default] if available_default else df.iloc[:, :5]

    # Export if requested
    if export:
        export_path = Path(export)
        df.to_csv(export_path, index=False)
        console.print(f"[green]✓ Exported {len(df)} leads to {export_path}[/green]\n")

    # Display as table
    table = Table(title=f"Leads ({min(limit, len(df))} of {len(df)})", box=box.ROUNDED)

    for col in df_display.columns:
        table.add_column(col, style="cyan" if col == "company_name" else None)

    for _, row in df_display.head(limit).iterrows():
        table.add_row(*[str(v) if pd.notna(v) else "" for v in row])

    console.print(table)

    # Show column info
    console.print(f"\n[dim]Available columns: {', '.join(df.columns)}[/dim]")
    console.print("[dim]Use --columns to select, --filter to search, --sort to order[/dim]")


@app.command()
def stats(
    file: str = typer.Argument(None, help="CSV file to analyze (or picks latest)"),
):
    """Show statistics about lead generation results."""
    import pandas as pd

    show_banner()

    output_dirs = [Path("output"), Path("data/output")]

    # Find the file
    if file:
        csv_path = Path(file)
        if not csv_path.exists():
            for output_dir in output_dirs:
                if (output_dir / file).exists():
                    csv_path = output_dir / file
                    break
    else:
        csv_files = []
        for output_dir in output_dirs:
            csv_files.extend(output_dir.glob("leads_*.csv"))

        if not csv_files:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(1)
        csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        console.print(f"[red]Error reading CSV: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Results:[/bold] {csv_path.name}\n")

    # Summary stats
    stats_table = Table(title="Lead Statistics", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green")

    stats_table.add_row("Total Leads", str(len(df)))

    if "has_ecommerce" in df.columns:
        ecom_count = df["has_ecommerce"].sum() if df["has_ecommerce"].dtype == bool else (df["has_ecommerce"] == True).sum()
        stats_table.add_row("With E-commerce", str(int(ecom_count)))

    if "location_count" in df.columns:
        avg_locs = df["location_count"].mean()
        stats_table.add_row("Avg Locations", f"{avg_locs:.1f}")

    if "city" in df.columns:
        unique_cities = df["city"].nunique()
        stats_table.add_row("Unique Cities", str(unique_cities))

    if "contact_name" in df.columns:
        with_contacts = df["contact_name"].notna().sum()
        stats_table.add_row("With Contacts", str(with_contacts))

    if "contact_email" in df.columns:
        with_emails = df["contact_email"].notna().sum()
        stats_table.add_row("With Emails", str(with_emails))

    console.print(stats_table)

    # Top cities
    if "city" in df.columns:
        console.print("\n[bold]Top Cities:[/bold]")
        top_cities = df["city"].value_counts().head(10)
        city_table = Table(box=box.SIMPLE)
        city_table.add_column("City", style="cyan")
        city_table.add_column("Leads", style="green", justify="right")

        for city, count in top_cities.items():
            city_table.add_row(str(city), str(count))

        console.print(city_table)


if __name__ == "__main__":
    app()
