#!/usr/bin/env python3
"""Generate OpenAPI spec from API definitions."""
import json
import yaml
from pathlib import Path


SPEC_PATH = Path(__file__).parent.parent / "src" / "api" / "docs" / "openapi-spec.yaml"


def validate_spec():
    """Validate the OpenAPI spec file."""
    if not SPEC_PATH.exists():
        print(f"Spec not found at {SPEC_PATH}")
        return False

    with open(SPEC_PATH) as f:
        spec = yaml.safe_load(f)

    required_keys = {"openapi", "info", "paths"}
    missing = required_keys - set(spec.keys())
    if missing:
        print(f"Missing required keys: {missing}")
        return False

    print(f"OpenAPI {spec['openapi']} spec valid: {spec['info'].get('title', 'untitled')}")
    print(f"  Endpoints: {len(spec.get('paths', {}))}")
    return True


if __name__ == "__main__":
    validate_spec()
