"""
Template discovery — local catalog + n8n community search.

Local templates live in a directory as {name}.json + {name}.meta.yaml
pairs. The JSON is the raw n8n workflow; the YAML carries searchable
metadata the EA matches against. JSON-without-sidecar is ignored —
metadata is the contract for "this is discoverable."

Community search hits n8n.io's public template API. Results are cached
to disk keyed by query so repeat lookups don't re-fetch. Cache never
expires — templates don't churn fast enough to matter, and a stale hit
beats a network round-trip in the middle of a WhatsApp conversation.

Search is deliberately dumb: token overlap scoring. No embeddings, no
LLM. The EA's intent extraction happens upstream; by the time a query
lands here it's already "hubspot weekly report" not "can you set
something up so I get my sales numbers regularly."
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)

_COMMUNITY_API = "https://api.n8n.io/api/templates/search"
_STOPWORDS = frozenset({"the", "a", "an", "my", "me", "to", "for", "and", "or",
                        "send", "get", "set", "up", "every"})


@dataclass(frozen=True)
class WorkflowTemplate:
    id: str
    name: str
    description: str
    integrations: List[str]
    category: str
    tags: List[str]
    raw: Dict[str, Any]
    source: str  # "local" | "community"


class WorkflowCatalog:

    def __init__(
        self,
        local_dir: Path | str,
        cache_dir: Path | str | None = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self._local_dir = Path(local_dir)
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._http = http_client
        self._local_cache: Optional[List[WorkflowTemplate]] = None

    # --- Local --------------------------------------------------------------

    def list_local(self) -> List[WorkflowTemplate]:
        if self._local_cache is not None:
            return self._local_cache

        out: List[WorkflowTemplate] = []
        if not self._local_dir.exists():
            self._local_cache = out
            return out

        for json_path in sorted(self._local_dir.glob("*.json")):
            meta_path = json_path.with_suffix(".meta.yaml")
            if not meta_path.exists():
                continue  # no sidecar → not discoverable
            try:
                raw = json.loads(json_path.read_text())
                meta = yaml.safe_load(meta_path.read_text())
            except (json.JSONDecodeError, yaml.YAMLError) as e:
                logger.warning(f"Skipping {json_path.name}: {e}")
                continue

            out.append(WorkflowTemplate(
                id=json_path.stem,
                name=meta.get("name", json_path.stem),
                description=meta.get("description", ""),
                integrations=meta.get("integrations", []),
                category=meta.get("category", "uncategorized"),
                tags=meta.get("tags", []),
                raw=raw,
                source="local",
            ))

        self._local_cache = out
        return out

    def search_local(self, query: str) -> List[WorkflowTemplate]:
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        scored = []
        for t in self.list_local():
            haystack = _tokenize(
                f"{t.name} {t.description} {' '.join(t.tags)} {' '.join(t.integrations)}"
            )
            overlap = len(q_tokens & haystack)
            if overlap > 0:
                scored.append((overlap, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored]

    # --- Community ----------------------------------------------------------

    async def search_community(self, query: str) -> List[WorkflowTemplate]:
        cached = self._cache_read(query)
        if cached is not None:
            return cached

        http = self._http or httpx.AsyncClient(timeout=10.0)
        try:
            resp = await http.get(_COMMUNITY_API, params={"search": query})
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"Community search failed for '{query}': {e}")
            return []

        templates = [
            WorkflowTemplate(
                id=f"community_{w.get('id')}",
                name=w.get("name", ""),
                description=w.get("description", ""),
                integrations=self._extract_integrations(w),
                category="community",
                tags=[],
                raw=w,
                source="community",
            )
            for w in body.get("workflows", [])
        ]

        self._cache_write(query, templates)
        return templates

    @staticmethod
    def _extract_integrations(w: Dict[str, Any]) -> List[str]:
        # n8n community templates list nodes; node names hint at integrations.
        nodes = w.get("nodes", [])
        return [n.get("name", "").lower() for n in nodes if n.get("name")]

    # --- Disk cache ---------------------------------------------------------

    def _cache_path(self, query: str) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        h = hashlib.sha256(query.encode()).hexdigest()[:16]
        return self._cache_dir / f"community_{h}.json"

    def _cache_read(self, query: str) -> Optional[List[WorkflowTemplate]]:
        path = self._cache_path(query)
        if path is None or not path.exists():
            return None
        try:
            items = json.loads(path.read_text())
            return [WorkflowTemplate(**it) for it in items]
        except (json.JSONDecodeError, TypeError):
            return None

    def _cache_write(self, query: str, templates: List[WorkflowTemplate]) -> None:
        path = self._cache_path(query)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [_template_to_dict(t) for t in templates]
        path.write_text(json.dumps(serialized))


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"\b\w+\b", text.lower()))
    return tokens - _STOPWORDS


def _template_to_dict(t: WorkflowTemplate) -> Dict[str, Any]:
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "integrations": t.integrations, "category": t.category,
        "tags": t.tags, "raw": t.raw, "source": t.source,
    }
