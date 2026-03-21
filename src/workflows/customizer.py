"""
Template → deployable workflow.

Templates carry {{CONFIGURE: label}} placeholders wherever the customer
needs to supply a value. The customizer walks the template tree, finds
every placeholder, and swaps in the provided value. It refuses to emit
a workflow with any placeholder still present — that's the "validate
completeness" guarantee.

The placeholder format matches what's already in
templates/n8n/report_generation.json so existing templates work
unchanged.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional


_PLACEHOLDER_RE = re.compile(r"\{\{CONFIGURE:\s*([^}]+?)\s*\}\}")


class IncompleteCustomizationError(Exception):
    """apply() called before every required placeholder was filled."""


class WorkflowCustomizer:

    def __init__(self, template: Dict[str, Any]):
        self._template = template
        self._placeholders = self._scan(template)

    def identify_missing(self, provided: Dict[str, str]) -> List[str]:
        return [p for p in self._placeholders if p not in provided]

    def apply(
        self,
        values: Dict[str, str],
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        missing = self.identify_missing(values)
        if missing:
            raise IncompleteCustomizationError(
                f"missing required parameters: {', '.join(missing)}"
            )

        out = copy.deepcopy(self._template)
        self._substitute(out, values)
        if name:
            out["name"] = name
        return out

    # --- Walkers ------------------------------------------------------------

    @classmethod
    def _scan(cls, obj: Any) -> List[str]:
        """Collect every unique placeholder label, in first-seen order."""
        found: List[str] = []
        seen: set[str] = set()

        def walk(o: Any) -> None:
            if isinstance(o, str):
                for m in _PLACEHOLDER_RE.finditer(o):
                    label = m.group(1)
                    if label not in seen:
                        seen.add(label)
                        found.append(label)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(obj)
        return found

    @classmethod
    def _substitute(cls, obj: Any, values: Dict[str, str]) -> None:
        """In-place replacement. Call on a deep copy."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    obj[k] = cls._replace(v, values)
                else:
                    cls._substitute(v, values)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str):
                    obj[i] = cls._replace(v, values)
                else:
                    cls._substitute(v, values)

    @staticmethod
    def _replace(s: str, values: Dict[str, str]) -> str:
        def sub(m: re.Match) -> str:
            return values.get(m.group(1), m.group(0))
        return _PLACEHOLDER_RE.sub(sub, s)
