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
