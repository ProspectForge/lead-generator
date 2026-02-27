# tests/conftest.py
import os
import socket

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def _has_network() -> bool:
    """Check if we can reach the internet."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "live: marks tests that hit real websites (deselect with '-m not live')")


def pytest_collection_modifyitems(config, items):
    # Skip live tests unless --run-live is passed or RUN_LIVE_TESTS=1
    run_live = config.getoption("--run-live", default=False) or os.environ.get("RUN_LIVE_TESTS") == "1"
    if not run_live:
        skip_live = pytest.mark.skip(reason="Live tests skipped. Use --run-live or RUN_LIVE_TESTS=1")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False, help="Run live integration tests against real websites")


@pytest.fixture
def sample_brand_data():
    return {
        "brand_name": "Test Brand",
        "location_count": 5,
        "website": "https://testbrand.com",
        "has_ecommerce": True,
    }
