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
