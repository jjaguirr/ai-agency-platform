"""Template registry for discovering and loading workflow templates."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional


TEMPLATE_DIR = Path(__file__).parent


def list_templates() -> List[Dict]:
    """List all available workflow templates."""
    templates = []
    for f in TEMPLATE_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
            data["_file"] = f.name
            templates.append(data)
    return sorted(templates, key=lambda t: t.get("name", ""))


def get_template(name: str) -> Optional[Dict]:
    """Get a template by name."""
    for t in list_templates():
        if t["name"] == name:
            return t
    return None


def get_templates_by_category(category: str) -> List[Dict]:
    """Get all templates in a category."""
    return [t for t in list_templates() if t.get("category") == category]


def get_categories() -> List[str]:
    """Get all unique template categories."""
    return sorted(set(t.get("category", "uncategorized") for t in list_templates()))
