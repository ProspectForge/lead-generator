# tests/test_website_health.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from src.pipeline import Pipeline
from src.brand_grouper import BrandGroup


def _make_brand(name: str, website: str) -> BrandGroup:
    return BrandGroup(
        normalized_name=name,
        original_names=[name.title()],
        location_count=5,
        locations=[],
        website=website,
        cities=["Toronto"],
    )


@pytest.mark.asyncio
async def test_healthy_website_passes():
    """Brands with responsive websites pass through."""
    pipeline = Pipeline()
    brands = [_make_brand("good store", "https://goodstore.com")]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://goodstore.com")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 1
    assert result[0].normalized_name == "good store"


@pytest.mark.asyncio
async def test_404_website_filtered():
    """Brands with 404 websites are filtered out."""
    pipeline = Pipeline()
    brands = [_make_brand("dead store", "https://deadstore.com")]

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.url = httpx.URL("https://deadstore.com")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_dns_failure_filtered():
    """Brands with unresolvable domains are filtered out."""
    pipeline = Pipeline()
    brands = [_make_brand("expired store", "https://expired-domain.com")]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(side_effect=httpx.ConnectError("DNS resolution failed"))
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_parked_domain_filtered():
    """Brands redirecting to domain parking are filtered out."""
    pipeline = Pipeline()
    brands = [_make_brand("parked store", "https://parkedstore.com")]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://www.godaddy.com/parking")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_brand_without_website_passes():
    """Brands without websites pass through (filtered later by e-commerce check)."""
    pipeline = Pipeline()
    brands = [_make_brand("no website store", None)]

    result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_mixed_brands_filters_correctly():
    """Mix of healthy and dead websites filters correctly."""
    pipeline = Pipeline()
    brands = [
        _make_brand("healthy", "https://healthy.com"),
        _make_brand("dead", "https://dead.com"),
        _make_brand("no site", None),
    ]

    async def mock_head(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.url = httpx.URL(str(url))
        if "dead" in str(url):
            mock_resp.status_code = 404
        else:
            mock_resp.status_code = 200
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(side_effect=mock_head)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 2
    names = [b.normalized_name for b in result]
    assert "healthy" in names
    assert "no site" in names
    assert "dead" not in names
