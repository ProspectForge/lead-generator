# tests/conftest.py
import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def sample_brand_data():
    return {
        "brand_name": "Test Brand",
        "location_count": 5,
        "website": "https://testbrand.com",
        "has_ecommerce": True,
    }
