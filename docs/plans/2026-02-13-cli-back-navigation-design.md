# CLI Back Navigation Design

**Date:** 2026-02-13
**Status:** Approved

## Problem

The CLI interactive interface lacks back navigation. Users cannot return to previous screens without restarting the entire flow. This is frustrating when:
- Making a mistake in the pipeline setup wizard
- Wanting to change options after viewing results
- Accidentally entering the wrong submenu

## Solution

Add consistent back navigation to all CLI screens using a navigation stack pattern:
- `← Back` option on every menu (returns to previous screen)
- `⌂ Main Menu` option on every menu (jumps directly to main menu)

## Architecture

```
Navigation Stack Pattern:

main_menu() → push("main")
    ↓
step_1_search_type() → push("step1")
    ↓
step_2_location() → push("step2")
    ↓
step_3_query() → push("step3")

User selects "← Back":
    pop() → returns "step2" → call step_2_location()

User selects "⌂ Main Menu":
    clear() → call main_menu()
```

## Changes Required

### 1. New Module: `src/navigation.py`

```python
from typing import Optional

class NavigationStack:
    """Manages screen navigation history for back functionality."""

    def __init__(self):
        self.stack: list[str] = []

    def push(self, screen_id: str) -> None:
        """Add screen to navigation history."""
        self.stack.append(screen_id)

    def pop(self) -> Optional[str]:
        """Remove and return the previous screen."""
        if len(self.stack) > 1:
            self.stack.pop()  # Remove current
            return self.stack[-1]  # Return previous
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

### 2. Update `src/__main__.py`

**Add imports:**
```python
from src.navigation import NavigationStack, BACK_OPTION, MAIN_MENU_OPTION
```

**Initialize navigation:**
```python
nav = NavigationStack()
```

**Update each menu function to:**
1. Push current screen ID to stack
2. Append navigation options to choices
3. Handle BACK_OPTION and MAIN_MENU_OPTION returns

**Example pattern:**
```python
def some_menu():
    nav.push("some_menu")

    choices = [
        "Option 1",
        "Option 2",
        Separator(),
        BACK_OPTION,
        MAIN_MENU_OPTION,
    ]

    result = inquirer.select(
        message="Choose an option:",
        choices=choices,
    ).execute()

    if result == BACK_OPTION:
        prev = nav.pop()
        return SCREEN_MAP.get(prev, main_menu)()

    if result == MAIN_MENU_OPTION:
        nav.clear()
        return main_menu()

    # Handle other options...
```

**Screen mapping:**
```python
SCREEN_MAP = {
    "main": main_menu,
    "step1": step_1_search_type,
    "step2": step_2_location,
    "step3": step_3_query,
    "step4": step_4_confirm,
    "results": results_menu,
    "checkpoints": checkpoints_menu,
    "settings": settings_menu,
}
```

### 3. Affected Functions

| Function | Screen ID | Back Target |
|----------|-----------|-------------|
| `main_menu()` | "main" | N/A (root) |
| `step_1_search_type()` | "step1" | main_menu |
| `step_2_location()` | "step2" | step1 |
| `step_3_query()` | "step3" | step2 |
| `step_4_confirm()` | "step4" | step3 |
| `results_menu()` | "results" | main_menu |
| `checkpoints_menu()` | "checkpoints" | main_menu |
| `settings_menu()` | "settings" | main_menu |

### 4. Special Cases

**Main Menu:**
- No "← Back" option (already at root)
- No "⌂ Main Menu" option (redundant)

**Nested Submenus:**
- Export submenu backs to results_menu
- Individual result view backs to results_menu

**During Pipeline Execution:**
- Pipeline runs non-interactively after confirmation
- No navigation during execution (not applicable)

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Back at main menu | Option not shown |
| Invalid screen ID | Fall back to main_menu |
| Ctrl+C interrupt | Existing behavior preserved |

## Testing

1. Unit tests for `NavigationStack` class
2. Integration tests for navigation flow
3. Manual testing of wizard back navigation

## Output

No new output. This is a UX improvement only.
