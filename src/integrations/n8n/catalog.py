"""
Template catalog: local keyword search + n8n community API.

Discovery is deterministic — no LLM, no embeddings. Tokenize the query,
score templates by keyword hit count against metadata sidecars.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_COMMUNITY_API = "https://api.n8n.io/templates/search"
_CACHE_TTL_SECONDS = 300  # 5 minutes
_MAX_RESULTS = 10


@dataclass
class TemplateMatch:
    name: str
    description: str
    category: str
    tags: list[str]
    relevance_score: float


@dataclass
class CommunityTemplate:
    id: int
    name: str
    description: str
    nodes: list[dict[str, Any]]


class TemplateCatalog:
    def __init__(
        self,
        template_dir: Path,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._dir = template_dir
        self._http = http_client
        self._community_cache: dict[str, tuple[float, list[CommunityTemplate]]] = {}

    def _load_sidecars(self) -> list[dict[str, Any]]:
        sidecars = []
        for f in self._dir.glob("*_meta.json"):
            try:
                data = json.loads(f.read_text())
                sidecars.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load sidecar %s: %s", f, exc)
        return sidecars

    def search_local(
        self, query: str, tags: list[str] | None = None,
    ) -> list[TemplateMatch]:
        sidecars = self._load_sidecars()
        tokens = query.lower().split()
        if not tokens:
            return []

        scored: list[tuple[float, dict]] = []
        for meta in sidecars:
            # Filter by tag if specified
            if tags:
                meta_tags = [t.lower() for t in meta.get("tags", [])]
                if not any(t.lower() in meta_tags for t in tags):
                    continue

            searchable = " ".join([
                meta.get("name", ""),
                meta.get("description", ""),
                " ".join(meta.get("tags", [])),
            ]).lower()

            hits = sum(1 for t in tokens if t in searchable)
            if hits > 0:
                scored.append((hits / len(tokens), meta))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            TemplateMatch(
                name=m.get("name", ""),
                description=m.get("description", ""),
                category=m.get("category", ""),
                tags=m.get("tags", []),
                relevance_score=score,
            )
            for score, m in scored[:_MAX_RESULTS]
        ]

    async def search_community(self, query: str) -> list[CommunityTemplate]:
        # Check cache
        cached = self._community_cache.get(query)
        if cached is not None:
            ts, results = cached
            if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                return results

        http = self._http or httpx.AsyncClient(timeout=10.0)
        try:
            resp = await http.get(_COMMUNITY_API, params={"search": query})
            if resp.status_code >= 400:
                logger.warning("Community API returned %d for query %r", resp.status_code, query)
                self._community_cache.pop(query, None)
                return []
            data = resp.json()
            results = [
                CommunityTemplate(
                    id=w.get("id", 0),
                    name=w.get("name", ""),
                    description=w.get("description", ""),
                    nodes=w.get("nodes", []),
                )
                for w in data.get("workflows", [])
            ]
            self._community_cache[query] = (time.monotonic(), results)
            return results
        except Exception as exc:
            logger.warning("Community search failed for query %r: %s", query, exc)
            self._community_cache.pop(query, None)
            return []

    def get_local_template(self, name: str) -> dict[str, Any] | None:
        for f in self._dir.glob("*.json"):
            if f.name.endswith("_meta.json"):
                continue
            try:
                data = json.loads(f.read_text())
                if data.get("name") == name:
                    return data
            except (json.JSONDecodeError, OSError):
                continue
        return None
