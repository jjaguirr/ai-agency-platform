"""
Tests for TemplateCatalog: local keyword search + community API.

Local search is deterministic (no LLM). Community search uses httpx
with caching and graceful failure.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from src.integrations.n8n.catalog import TemplateCatalog


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    """Create a temp directory with templates + sidecars."""
    # Template 1: Weekly Report
    (tmp_path / "report_generation.json").write_text(json.dumps({
        "name": "Weekly Business Report",
        "description": "Generate weekly summary reports",
        "category": "reporting",
        "triggers": [{"type": "schedule", "cron": "0 8 * * 1"}],
        "actions": [{"type": "aggregate_metrics"}, {"type": "send_email"}],
    }))
    (tmp_path / "report_generation_meta.json").write_text(json.dumps({
        "name": "Weekly Business Report",
        "description": "Automated weekly business report generation and distribution",
        "required_integrations": ["email", "metrics_api"],
        "category": "reporting",
        "tags": ["report", "weekly", "email", "metrics", "schedule", "business"],
    }))

    # Template 2: Invoice
    (tmp_path / "invoice_generation.json").write_text(json.dumps({
        "name": "Invoice Generation",
        "description": "Generate and send invoices",
        "category": "finance",
        "triggers": [{"type": "schedule", "cron": "0 0 1 * *"}],
        "actions": [{"type": "generate_invoice"}, {"type": "send_email"}],
    }))
    (tmp_path / "invoice_generation_meta.json").write_text(json.dumps({
        "name": "Invoice Generation",
        "description": "Generate and send invoices based on completed work or recurring schedules",
        "required_integrations": ["email", "accounting"],
        "category": "finance",
        "tags": ["invoice", "billing", "finance", "email", "accounting", "schedule"],
    }))

    # Template 3: Social Media
    (tmp_path / "social_media_automation.json").write_text(json.dumps({
        "name": "Social Media Post Automation",
        "description": "Schedule and post content across platforms",
        "category": "marketing",
        "triggers": [{"type": "schedule"}],
        "actions": [{"type": "generate_content"}, {"type": "schedule_post"}],
    }))
    (tmp_path / "social_media_automation_meta.json").write_text(json.dumps({
        "name": "Social Media Post Automation",
        "description": "Automatically schedule and post content across social media platforms",
        "required_integrations": ["instagram", "facebook"],
        "category": "marketing",
        "tags": ["social", "instagram", "facebook", "content", "marketing", "post"],
    }))

    return tmp_path


@pytest.fixture
def catalog(catalog_dir: Path) -> TemplateCatalog:
    return TemplateCatalog(template_dir=catalog_dir)


# --- Local search -----------------------------------------------------------

class TestSearchLocal:
    def test_matches_by_name(self, catalog):
        results = catalog.search_local("invoice")
        assert len(results) >= 1
        assert results[0].name == "Invoice Generation"

    def test_matches_by_tags(self, catalog):
        results = catalog.search_local("billing")
        assert any(r.name == "Invoice Generation" for r in results)

    def test_matches_by_description(self, catalog):
        results = catalog.search_local("weekly business report")
        assert results[0].name == "Weekly Business Report"

    def test_filters_by_tag_parameter(self, catalog):
        results = catalog.search_local("email", tags=["finance"])
        # Both report and invoice have "email", but only invoice has finance tag
        names = [r.name for r in results]
        assert "Invoice Generation" in names
        assert "Weekly Business Report" not in names

    def test_returns_empty_on_no_match(self, catalog):
        results = catalog.search_local("xyznonexistent")
        assert results == []

    def test_ranks_by_relevance(self, catalog):
        # "report weekly email" should rank Weekly Report highest (3 hits)
        results = catalog.search_local("report weekly email")
        assert results[0].name == "Weekly Business Report"

    def test_returns_at_most_10(self, catalog_dir):
        # Add 15 templates
        for i in range(15):
            (catalog_dir / f"tpl_{i}.json").write_text(json.dumps({"name": f"Tpl {i}"}))
            (catalog_dir / f"tpl_{i}_meta.json").write_text(json.dumps({
                "name": f"Tpl {i}", "description": "match", "required_integrations": [],
                "category": "test", "tags": ["match"],
            }))
        cat = TemplateCatalog(template_dir=catalog_dir)
        results = cat.search_local("match")
        assert len(results) <= 10


# --- Community search -------------------------------------------------------

class TestSearchCommunity:
    async def test_calls_n8n_api(self):
        api_response = {
            "totalWorkflows": 1,
            "workflows": [
                {"id": 42, "name": "HubSpot Report", "description": "Weekly HubSpot report", "nodes": []},
            ],
        }

        def handler(request: httpx.Request):
            assert "search=hubspot" in str(request.url)
            return httpx.Response(200, json=api_response)

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        cat = TemplateCatalog(template_dir=Path("/nonexistent"), http_client=http)
        results = await cat.search_community("hubspot")
        assert len(results) == 1
        assert results[0].name == "HubSpot Report"

    async def test_caches_results(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"totalWorkflows": 0, "workflows": []})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        cat = TemplateCatalog(template_dir=Path("/nonexistent"), http_client=http)
        await cat.search_community("test")
        await cat.search_community("test")
        assert call_count == 1  # second call was cached

    async def test_handles_api_failure_gracefully(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, text="Internal Server Error")

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        cat = TemplateCatalog(template_dir=Path("/nonexistent"), http_client=http)
        results = await cat.search_community("anything")
        assert results == []

    async def test_handles_connection_error(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        cat = TemplateCatalog(template_dir=Path("/nonexistent"), http_client=http)
        results = await cat.search_community("anything")
        assert results == []

    async def test_failure_does_not_cache_stale_results(self):
        """After a successful fetch, a subsequent failure must NOT return
        previously cached results — it must return empty."""
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={
                    "totalWorkflows": 1,
                    "workflows": [{"id": 1, "name": "Cached", "description": "", "nodes": []}],
                })
            return httpx.Response(500, text="down")

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        cat = TemplateCatalog(template_dir=Path("/nonexistent"), http_client=http)
        # First call succeeds and caches
        first = await cat.search_community("q")
        assert len(first) == 1
        # Expire the cache manually
        cat._community_cache["q"] = (0, cat._community_cache["q"][1])
        # Second call fails — must return empty, not stale cached data
        second = await cat.search_community("q")
        assert second == []


# --- get_local_template -----------------------------------------------------

class TestGetLocalTemplate:
    def test_returns_template_by_name(self, catalog):
        tpl = catalog.get_local_template("Weekly Business Report")
        assert tpl is not None
        assert tpl["name"] == "Weekly Business Report"

    def test_returns_none_for_missing(self, catalog):
        assert catalog.get_local_template("Nonexistent") is None
