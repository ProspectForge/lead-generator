# tests/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline import Pipeline
from src.brand_grouper import BrandGroup

@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    pipeline = Pipeline()

    mock_brand = BrandGroup(
        normalized_name="test store",
        original_names=["Test Store"],
        location_count=5,
        locations=[{"name": "Test Store", "address": "123 Main St"}],
        website="https://teststore.com",
        cities=["New York"],
    )

    mock_discovery_instance = MagicMock()
    mock_discovery_instance.run = AsyncMock(return_value=[{"name": "Test Store", "address": "123 Main St"}])

    with patch('src.pipeline.Discovery', return_value=mock_discovery_instance) as mock_discovery_cls, \
         patch.object(pipeline, 'stage_2_group', new_callable=MagicMock) as mock_group, \
         patch.object(pipeline, 'stage_2b_verify_chain_size', new_callable=MagicMock) as mock_verify, \
         patch.object(pipeline, 'stage_2c_website_health', new_callable=AsyncMock) as mock_health, \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock) as mock_ecom, \
         patch.object(pipeline, 'stage_4_enrich', new_callable=AsyncMock) as mock_enrich, \
         patch.object(pipeline, 'stage_4b_quality_gate', new_callable=AsyncMock) as mock_quality, \
         patch.object(pipeline, 'stage_5_score', new_callable=MagicMock) as mock_score, \
         patch.object(pipeline, 'stage_6_export', new_callable=MagicMock) as mock_export, \
         patch.object(pipeline, '_save_checkpoint', new_callable=MagicMock) as mock_save_cp, \
         patch.object(pipeline, 'clear_checkpoint', new_callable=MagicMock) as mock_clear_cp:

        mock_group.return_value = [mock_brand]
        mock_verify.return_value = [mock_brand]
        mock_health.return_value = [mock_brand]
        mock_ecom.return_value = [mock_brand]
        mock_enrich.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_quality.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_score.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com", "priority_score": 50}]
        mock_export.return_value = "output.csv"

        result = await pipeline.run(verticals=["apparel"], countries=["us"])

        mock_discovery_instance.run.assert_called_once()
        mock_group.assert_called_once()
        mock_verify.assert_called_once()
        mock_health.assert_called_once()
        mock_ecom.assert_called_once()
        mock_enrich.assert_called_once()
        mock_quality.assert_called_once()
        mock_score.assert_called_once()
        mock_export.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_includes_scoring_stage():
    """Test that pipeline adds tech stack scoring to enriched leads."""
    pipeline = Pipeline()

    # Mock enriched data with technology_names
    mock_enriched = [
        {
            "brand_name": "Fleet Feet",
            "location_count": 5,
            "has_ecommerce": True,
            "marketplaces": "Amazon",
            "technology_names": ["Lightspeed", "Klaviyo"],
            "contact_1_name": "John Smith",
        },
        {
            "brand_name": "Local Sports",
            "location_count": 4,
            "has_ecommerce": True,
            "marketplaces": "",
            "technology_names": ["Square"],
            "contact_1_name": "Jane Doe",
        },
    ]

    scored = pipeline.stage_5_score(mock_enriched)

    # Check scoring fields added
    assert "priority_score" in scored[0]
    assert "pos_platform" in scored[0]
    assert "uses_lightspeed" in scored[0]

    # Lightspeed lead should be first (highest score)
    assert scored[0]["brand_name"] == "Fleet Feet"
    assert scored[0]["uses_lightspeed"] is True
    assert scored[0]["priority_score"] > scored[1]["priority_score"]
