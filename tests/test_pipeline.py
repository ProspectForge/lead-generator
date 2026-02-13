# tests/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline import Pipeline

@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    pipeline = Pipeline()

    with patch.object(pipeline, 'stage_1_search', new_callable=AsyncMock) as mock_search, \
         patch.object(pipeline, 'stage_2_group', new_callable=MagicMock) as mock_group, \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock) as mock_ecom, \
         patch.object(pipeline, 'stage_4_linkedin', new_callable=AsyncMock) as mock_linkedin, \
         patch.object(pipeline, 'stage_5_export', new_callable=MagicMock) as mock_export:

        mock_search.return_value = [{"name": "Test Store"}]
        mock_group.return_value = [MagicMock(location_count=5)]
        mock_ecom.return_value = [MagicMock(has_ecommerce=True)]
        mock_linkedin.return_value = [MagicMock()]
        mock_export.return_value = "output.csv"

        result = await pipeline.run(verticals=["apparel"], countries=["us"])

        mock_search.assert_called_once()
        mock_group.assert_called_once()
        mock_ecom.assert_called_once()
        mock_linkedin.assert_called_once()
        mock_export.assert_called_once()
