# CLI Back Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add consistent back navigation to all CLI screens with "← Back" and "⌂ Main Menu" options.

**Architecture:** Navigation stack pattern - each screen pushes its ID, "Back" pops to previous, "Main Menu" clears stack and returns to root. Uses a centralized `NavigationStack` class with screen ID mapping.

**Tech Stack:** Python, InquirerPy, Rich

---

### Task 1: Create NavigationStack Class

**Files:**
- Create: `src/navigation.py`
- Test: `tests/test_navigation.py`

**Step 1: Write the failing test**

```python
# tests/test_navigation.py
import pytest
from src.navigation import NavigationStack, BACK_OPTION, MAIN_MENU_OPTION


def test_push_adds_screen_to_stack():
    nav = NavigationStack()
    nav.push("main")
    nav.push("step1")

    assert nav.current() == "step1"
    assert len(nav.stack) == 2


def test_pop_returns_previous_screen():
    nav = NavigationStack()
    nav.push("main")
    nav.push("step1")
    nav.push("step2")

    previous = nav.pop()

    assert previous == "step1"
    assert nav.current() == "step1"


def test_pop_returns_none_at_root():
    nav = NavigationStack()
    nav.push("main")

    previous = nav.pop()

    assert previous is None


def test_clear_empties_stack():
    nav = NavigationStack()
    nav.push("main")
    nav.push("step1")
    nav.push("step2")

    nav.clear()

    assert nav.current() is None
    assert len(nav.stack) == 0


def test_current_returns_none_for_empty_stack():
    nav = NavigationStack()

    assert nav.current() is None


def test_navigation_constants_exist():
    assert BACK_OPTION == "← Back"
    assert MAIN_MENU_OPTION == "⌂ Main Menu"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_navigation.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.navigation'"

**Step 3: Write minimal implementation**

```python
# src/navigation.py
"""Navigation stack for CLI back functionality."""
from typing import Optional


class NavigationStack:
    """Manages screen navigation history for back functionality."""

    def __init__(self):
        self.stack: list[str] = []

    def push(self, screen_id: str) -> None:
        """Add screen to navigation history."""
        self.stack.append(screen_id)

    def pop(self) -> Optional[str]:
        """Remove current and return the previous screen.

        Returns None if at root (only one item in stack).
        """
        if len(self.stack) > 1:
            self.stack.pop()  # Remove current
            return self.stack[-1]  # Return previous (now current)
        return None

    def clear(self) -> None:
        """Clear navigation history (for main menu jump)."""
        self.stack.clear()

    def current(self) -> Optional[str]:
        """Get current screen ID."""
        return self.stack[-1] if self.stack else None


# Navigation option constants
BACK_OPTION = "← Back"
MAIN_MENU_OPTION = "⌂ Main Menu"
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_navigation.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/navigation.py tests/test_navigation.py
git commit -m "feat: add NavigationStack class for CLI back navigation"
```

---

### Task 2: Add Navigation to Settings Menu

**Files:**
- Modify: `src/__main__.py:161-220` (function `_show_settings_overview`)
- Modify: `src/__main__.py:1-17` (imports)

**Step 1: Add imports at top of file**

Add after line 13 (`from InquirerPy import inquirer`):

```python
from InquirerPy.separator import Separator
from src.navigation import NavigationStack, BACK_OPTION, MAIN_MENU_OPTION
```

**Step 2: Initialize global navigation stack**

Add after line 22 (`console = Console()`):

```python
nav = NavigationStack()
```

**Step 3: Update _show_settings_overview function**

Replace lines 161-220 with:

```python
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

        console.print(table)

        action = inquirer.select(
            message="What would you like to configure?",
            choices=[
                {"name": "🔌 Enrichment settings", "value": "enrichment"},
                {"name": "📧 Email verification settings", "value": "email"},
                {"name": "⚡ Concurrency settings", "value": "concurrency"},
                {"name": "🔑 View API key setup instructions", "value": "api_help"},
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

        elif action == "enrichment":
            _configure_enrichment()

        elif action == "email":
            _configure_email_verification()

        elif action == "concurrency":
            _configure_concurrency()

        elif action == "api_help":
            _show_api_help()
```

**Step 4: Run tests to verify nothing broke**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v -x`
Expected: All existing tests pass

**Step 5: Commit**

```bash
git add src/__main__.py
git commit -m "feat: add back navigation to settings menu"
```

---

### Task 3: Add Navigation to Results Menu

**Files:**
- Modify: `src/__main__.py:457-561` (function `_interactive_results`)

**Step 1: Update _interactive_results function**

Replace lines 457-561 with:

```python
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

        elif action == "browse":
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
```

**Step 2: Run tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/__main__.py
git commit -m "feat: add back navigation to results menu"
```

---

### Task 4: Add Navigation to Checkpoints Menu

**Files:**
- Modify: `src/__main__.py:919-956` (function `_interactive_checkpoints`)

**Step 1: Update _interactive_checkpoints function**

Replace lines 919-956 with:

```python
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
```

**Step 2: Run tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/__main__.py
git commit -m "feat: add back navigation to checkpoints menu"
```

---

### Task 5: Add Navigation to Pipeline Setup Wizard

**Files:**
- Modify: `src/__main__.py:331-420` (function `_interactive_new_run`)

**Step 1: Update _interactive_new_run function**

Replace lines 331-420 with:

```python
def _interactive_new_run():
    """Run the full interactive pipeline setup with back navigation."""
    console.print()
    nav.push("new_run")

    # Track wizard state for back navigation
    vertical_list = None
    country_list = None

    # Step 1: Verticals
    while True:
        nav.push("step1")
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
            nav.pop()
            continue

        break

    # Step 2: Countries
    while True:
        nav.push("step2")
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
            nav.pop()
            nav.pop()  # Go back to step 1
            # Re-run step 1
            console.print()
            continue

        country_list = [c for c in result if c not in ("back", "main_menu")]
        if not country_list:
            console.print("[red]No countries selected. Please select at least one.[/red]")
            nav.pop()
            continue

        break

    # Normalize
    country_list = ["canada" if c == "ca" else c for c in country_list]

    # Step 3: Advanced settings
    nav.push("step3")
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
        nav.pop()
        # This is complex - would need to restart the wizard
        # For now, restart the whole function
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
    nav.push("step4")
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
        nav.pop()
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
```

**Step 2: Run tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/__main__.py
git commit -m "feat: add back navigation to pipeline setup wizard"
```

---

### Task 6: Update Main Menu to Handle Navigation Returns

**Files:**
- Modify: `src/__main__.py:52-159` (function `interactive_main_menu`)

**Step 1: Update interactive_main_menu function**

Replace lines 52-159 with:

```python
def interactive_main_menu():
    """Main interactive menu that ties all functionality together."""
    import pandas as pd

    show_banner()
    nav.clear()  # Ensure clean state at main menu
    nav.push("main")

    while True:
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
            # Reset navigation state
            nav.clear()
            nav.push("main")

        elif action == "resume":
            _interactive_resume_run(pipeline, checkpoints)
            nav.clear()
            nav.push("main")

        elif action == "results":
            result = _interactive_results()
            # Reset navigation regardless of how user exited
            nav.clear()
            nav.push("main")

        elif action == "stats":
            _interactive_stats()
            nav.clear()
            nav.push("main")

        elif action == "checkpoints":
            result = _interactive_checkpoints(pipeline)
            nav.clear()
            nav.push("main")

        elif action == "settings":
            result = _show_settings_overview()
            nav.clear()
            nav.push("main")
```

**Step 2: Run all tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests pass

**Step 3: Manual verification**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src`
Expected:
- Navigate to Settings → see "← Back" and "⌂ Main Menu" options
- Navigate to Results → see back options
- Start new run → see back options at each step
- "← Back" returns to previous screen
- "⌂ Main Menu" returns to main menu

**Step 4: Commit**

```bash
git add src/__main__.py
git commit -m "feat: update main menu to handle navigation returns"
```

---

### Task 7: Add Navigation to Stats Screen

**Files:**
- Modify: `src/__main__.py:816-916` (function `_interactive_stats`)

**Step 1: Update _interactive_stats function**

Add navigation options to the end of the function. Replace the current "Press Enter to continue" with menu choices:

Find at the end of the function (around line 916):
```python
    console.print()
    inquirer.confirm(message="Press Enter to continue...", default=True).execute()
```

Replace with:
```python
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
```

**Step 2: Run tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/__main__.py
git commit -m "feat: add back navigation to stats screen"
```

---

### Task 8: Final Integration Test

**Files:**
- No new files

**Step 1: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Manual smoke test**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src`

Test these flows:
1. Main → Settings → Back → Main (verify back works)
2. Main → Settings → Main Menu (verify jump works)
3. Main → New Run → Step 2 → Back → Step 1 (verify wizard back works)
4. Main → New Run → Step 3 → Main Menu (verify escape from wizard)
5. Main → Results → Main Menu (verify results navigation)
6. Main → Checkpoints → Back (verify checkpoints navigation)

**Step 3: Commit all changes**

```bash
git add -A
git commit -m "feat: complete CLI back navigation implementation"
```
