"""
WorkflowCatalog — local + community template discovery.

Local: scans a directory for *.json workflows with *.meta.yaml sidecars.
Metadata: name, description, integrations, category, tags. Search is
keyword/intent match against description + tags — deterministic, no LLM.

Community: hits n8n's public template API, caches results to a directory.
Cache-hit returns without a network call.
"""
import json

import httpx
import pytest
import yaml

from src.workflows.catalog import WorkflowCatalog, WorkflowTemplate


# --- Local catalog fixtures -------------------------------------------------

@pytest.fixture
def local_dir(tmp_path):
    """Build a tiny on-disk catalog: two templates with YAML sidecars."""
    n8n_dir = tmp_path / "n8n"
    n8n_dir.mkdir()

    # Template 1: HubSpot weekly report
    (n8n_dir / "hubspot_weekly.json").write_text(json.dumps({
        "name": "HubSpot Weekly Report",
        "nodes": [{"id": "t", "name": "Trigger", "type": "n8n-nodes-base.scheduleTrigger",
                   "typeVersion": 1.2, "position": [0, 0], "parameters": {}}],
        "connections": {},
    }))
    (n8n_dir / "hubspot_weekly.meta.yaml").write_text(yaml.dump({
        "name": "HubSpot Weekly Report",
        "description": "Email your HubSpot pipeline numbers on a schedule",
        "integrations": ["hubspot", "email"],
        "category": "reporting",
        "tags": ["weekly", "report", "pipeline", "sales", "crm"],
    }))

    # Template 2: Slack contact sync
    (n8n_dir / "slack_sync.json").write_text(json.dumps({
        "name": "Slack Contact Sync",
        "nodes": [{"id": "t", "name": "Trigger", "type": "n8n-nodes-base.scheduleTrigger",
                   "typeVersion": 1.2, "position": [0, 0], "parameters": {}}],
        "connections": {},
    }))
    (n8n_dir / "slack_sync.meta.yaml").write_text(yaml.dump({
        "name": "Slack Contact Sync",
        "description": "Sync new contacts from CRM into a Slack channel",
        "integrations": ["slack", "hubspot"],
        "category": "sync",
        "tags": ["contacts", "sync", "slack", "notification"],
    }))

    # Orphan JSON without sidecar — should be skipped, not crash
    (n8n_dir / "orphan.json").write_text(json.dumps({"name": "Orphan"}))

    return n8n_dir


@pytest.fixture
def catalog(local_dir, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return WorkflowCatalog(local_dir=local_dir, cache_dir=cache_dir)


# --- WorkflowTemplate shape -------------------------------------------------

class TestWorkflowTemplate:
    def test_holds_metadata_and_raw_json(self):
        t = WorkflowTemplate(
            id="hubspot_weekly",
            name="HubSpot Weekly Report",
            description="desc",
            integrations=["hubspot"],
            category="reporting",
            tags=["weekly"],
            raw={"nodes": []},
            source="local",
        )
        assert t.id == "hubspot_weekly"
        assert t.raw == {"nodes": []}
        assert t.source == "local"


# --- Local discovery --------------------------------------------------------

class TestLocalDiscovery:
    def test_loads_templates_with_sidecars(self, catalog):
        all_local = catalog.list_local()
        assert len(all_local) == 2
        names = {t.name for t in all_local}
        assert names == {"HubSpot Weekly Report", "Slack Contact Sync"}

    def test_orphan_json_without_sidecar_skipped(self, catalog):
        names = {t.name for t in catalog.list_local()}
        assert "Orphan" not in names

    def test_template_carries_raw_json(self, catalog):
        t = next(t for t in catalog.list_local() if "HubSpot" in t.name)
        assert "nodes" in t.raw
        assert t.source == "local"

    def test_template_id_is_filename_stem(self, catalog):
        t = next(t for t in catalog.list_local() if "HubSpot" in t.name)
        assert t.id == "hubspot_weekly"

    def test_integrations_from_sidecar(self, catalog):
        t = next(t for t in catalog.list_local() if "Slack" in t.name)
        assert set(t.integrations) == {"slack", "hubspot"}

    def test_empty_dir_returns_empty(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        c = WorkflowCatalog(local_dir=empty, cache_dir=tmp_path / "cache")
        assert c.list_local() == []


# --- Local search -----------------------------------------------------------

class TestLocalSearch:
    def test_match_by_tag(self, catalog):
        results = catalog.search_local("weekly report")
        assert len(results) == 1
        assert "HubSpot" in results[0].name

    def test_match_by_description_keyword(self, catalog):
        results = catalog.search_local("sync contacts")
        assert len(results) == 1
        assert "Slack" in results[0].name

    def test_match_by_integration(self, catalog):
        results = catalog.search_local("hubspot")
        # both mention hubspot in integrations
        assert len(results) == 2

    def test_no_match_returns_empty(self, catalog):
        assert catalog.search_local("bitcoin mining") == []

    def test_search_is_case_insensitive(self, catalog):
        assert len(catalog.search_local("WEEKLY REPORT")) == 1

    def test_multi_word_query_scores_higher(self, catalog):
        """More overlapping tokens → higher rank. 'pipeline weekly report'
        hits three tags for HubSpot; Slack sync hits none."""
        results = catalog.search_local("pipeline weekly report")
        assert results[0].name == "HubSpot Weekly Report"


# --- Community search -------------------------------------------------------

class TestCommunitySearch:
    """n8n public template API — mocked via httpx.MockTransport."""

    def _catalog_with_transport(self, tmp_path, handler):
        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        cache = tmp_path / "cache"
        cache.mkdir()
        return WorkflowCatalog(
            local_dir=tmp_path, cache_dir=cache, http_client=http
        )

    async def test_fetches_and_returns_templates(self, tmp_path):
        def handler(req):
            return httpx.Response(200, json={
                "workflows": [
                    {"id": 42, "name": "Community Report",
                     "description": "A community template",
                     "nodes": [{"name": "hubspot"}]},
                ]
            })

        c = self._catalog_with_transport(tmp_path, handler)
        results = await c.search_community("report")
        assert len(results) == 1
        assert results[0].name == "Community Report"
        assert results[0].source == "community"

    async def test_cache_hit_skips_network(self, tmp_path):
        call_count = 0

        def handler(req):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={
                "workflows": [{"id": 1, "name": "X", "description": "", "nodes": []}]
            })

        c = self._catalog_with_transport(tmp_path, handler)
        await c.search_community("foo")
        await c.search_community("foo")  # same query
        assert call_count == 1

    async def test_cache_miss_different_query_hits_network(self, tmp_path):
        call_count = 0

        def handler(req):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"workflows": []})

        c = self._catalog_with_transport(tmp_path, handler)
        await c.search_community("foo")
        await c.search_community("bar")
        assert call_count == 2

    async def test_network_error_returns_empty_not_raises(self, tmp_path):
        """Community search is best-effort. If n8n.io is down the EA falls
        back to local — not crashes."""
        def handler(req):
            raise httpx.ConnectError("dns fail")

        c = self._catalog_with_transport(tmp_path, handler)
        results = await c.search_community("anything")
        assert results == []

    async def test_cached_result_persists_to_disk(self, tmp_path):
        """Cache survives catalog reconstruction — it's on disk, not in-memory."""
        def handler(req):
            return httpx.Response(200, json={
                "workflows": [{"id": 1, "name": "Persisted", "description": "", "nodes": []}]
            })

        c1 = self._catalog_with_transport(tmp_path, handler)
        await c1.search_community("q")

        # New catalog, same cache dir, no http client — must still hit cache
        call_count = 0
        def counting_handler(req):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"workflows": []})

        transport = httpx.MockTransport(counting_handler)
        http = httpx.AsyncClient(transport=transport)
        c2 = WorkflowCatalog(local_dir=tmp_path, cache_dir=tmp_path / "cache",
                             http_client=http)
        results = await c2.search_community("q")
        assert call_count == 0
        assert results[0].name == "Persisted"
