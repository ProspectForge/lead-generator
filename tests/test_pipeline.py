# tests/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline import Pipeline
from src.brand_grouper import BrandGroup

@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    pipeline = Pipeline()

    # Create real BrandGroup objects instead of MagicMock for JSON serialization
    mock_brand = BrandGroup(
        normalized_name="test store",
        original_names=["Test Store"],
        location_count=5,
        locations=[{"name": "Test Store", "address": "123 Main St"}],
        website="https://teststore.com",
        cities=["New York"],
    )

    # Mock Discovery class to avoid real API calls in stage 1
    mock_discovery_instance = MagicMock()
    mock_discovery_instance.run = AsyncMock(return_value=[{"name": "Test Store", "address": "123 Main St"}])

    with patch('src.pipeline.Discovery', return_value=mock_discovery_instance) as mock_discovery_cls, \
         patch.object(pipeline, 'stage_2_group', new_callable=MagicMock) as mock_group, \
         patch.object(pipeline, 'stage_2b_verify_chain_size', new_callable=MagicMock) as mock_verify, \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock) as mock_ecom, \
         patch.object(pipeline, 'stage_4_enrich', new_callable=AsyncMock) as mock_enrich, \
         patch.object(pipeline, 'stage_5_export', new_callable=MagicMock) as mock_export, \
         patch.object(pipeline, '_save_checkpoint', new_callable=MagicMock) as mock_save_cp, \
         patch.object(pipeline, 'clear_checkpoint', new_callable=MagicMock) as mock_clear_cp:

        mock_group.return_value = [mock_brand]
        mock_verify.return_value = [mock_brand]
        mock_ecom.return_value = [mock_brand]
        mock_enrich.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_export.return_value = "output.csv"

        result = await pipeline.run(verticals=["apparel"], countries=["us"])

        mock_discovery_instance.run.assert_called_once()
        mock_group.assert_called_once()
        mock_verify.assert_called_once()
        mock_ecom.assert_called_once()
        mock_enrich.assert_called_once()
        mock_export.assert_called_once()
