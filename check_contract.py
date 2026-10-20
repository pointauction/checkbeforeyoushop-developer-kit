#!/usr/bin/env python3
"""Validate five bounded live samples against openapi.yaml (dev deps required)."""
import json
import urllib.request
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from openapi_spec_validator import validate_spec

BASE = "https://checkbeforeyoushop.com"
SPEC_PATH = Path(__file__).with_name("openapi.yaml")

def main():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    validate_spec(spec)
    root_uri = "urn:checkbeforeyoushop:openapi"
    registry = Registry().with_resource(root_uri, Resource.from_contents(spec, default_specification=DRAFT202012))
    def absolute_refs(value):
        if isinstance(value, dict):
            return {key: root_uri + val if key == "$ref" and isinstance(val, str) and val.startswith("#") else absolute_refs(val) for key, val in value.items()}
        if isinstance(value, list):
            return [absolute_refs(val) for val in value]
        return value
    samples = [
        ("/api/v1/search.json?q=nike", "/api/v1/search.json"),
        ("/api/v1/merchants/nike.json", "/api/v1/merchants/{slug}.json"),
        ("/api/v1/portals.json", "/api/v1/portals.json"),
    ]
    req = urllib.request.Request(BASE + samples[2][0], headers={"Accept": "application/json", "User-Agent": "cbys-contract-check/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        directory = json.load(r)
    portal_id = directory["data"]["portals"][0]["portal_id"]
    samples += [(f"/api/v1/portals/{portal_id}.json", "/api/v1/portals/{portal}.json"), ("/api/v1/highs.json", "/api/v1/highs.json")]
    # Reuse the one directory response already fetched; four more calls, five total.
    responses = []
    for path, operation in samples:
        if path == "/api/v1/portals.json":
            payload = directory
        else:
            req = urllib.request.Request(BASE + path, headers={"Accept": "application/json", "User-Agent": "cbys-contract-check/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                payload = json.load(r)
        schema = spec["paths"][operation]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        Draft202012Validator(absolute_refs(schema), registry=registry, format_checker=FormatChecker()).validate(payload)
        responses.append((path, payload))
    print(f"OpenAPI parsed and validated; {len(responses)} live responses passed JSON Schema validation (5 serial GET requests).")

if __name__ == "__main__":
    main()
