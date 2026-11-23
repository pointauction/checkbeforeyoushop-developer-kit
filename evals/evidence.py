"""Replay the eval harness's read-only selection rules against frozen fixtures."""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from build_fixtures import LIVE, SYNTHETIC, read

TOOLS = {
    "search_stores": {"query": str},
    "get_store_rates": {"store": str, "program": str, "unit": str, "include_stale": bool},
    "list_portals": {"category": str},
    "get_portal": {"portal": str},
    "get_highs": {"unit": str, "kind": str, "limit": int},
}
REQUIRED = {"search_stores": "query", "get_store_rates": "store", "get_portal": "portal"}


def call_valid(call):
    if not isinstance(call, dict) or not isinstance(call.get("tool"), str):
        return False
    tool, args = call["tool"], call.get("args")
    if tool not in TOOLS or not isinstance(args, dict):
        return False
    if tool in REQUIRED and REQUIRED[tool] not in args:
        return False
    return all(k in TOOLS[tool] and type(v) is TOOLS[tool][k] for k, v in args.items())


@lru_cache(maxsize=1)
def manifest():
    # Same last-layer-wins manifest as build_fixtures.py, without writing files.
    return {
        key: (root, entry)
        for root in (LIVE, SYNTHETIC)
        for key, entry in read(root / "manifest.json")["requests"].items()
    }


class FixtureError(Exception):
    pass


@lru_cache(maxsize=128)
def fixture(key):
    request = manifest().get("/api/v1/" + key)
    if request is None:
        raise FixtureError(f"{key} not in fixtures")
    root, entry = request
    if not 200 <= entry["status"] < 300:
        raise FixtureError(f"{key} returned HTTP {entry['status']}")
    return read(root / entry["file"])


@dataclass
class Result:
    tool: str
    args: dict
    data: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    error: str = ""
    no_match: bool = False


def search(query):
    return fixture("search.json?q=" + query)["data"]["results"]


def identities(row):
    return [row[key].lower() for key in ("program", "portal_id", "portal_name")]


def exact_candidate(rows, value):
    matches = [row for row in rows if row["slug"].lower() == value] or [
        row for row in rows if value in (row["name"].lower(), (row["domain"] or "").lower())
    ]
    return matches[0] if len(matches) == 1 else None


def store_result(result):
    args = result.args
    value = args["store"]
    key = f"merchants/{value}.json"
    env = None
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        entry = manifest().get("/api/v1/" + key)
        if entry and entry[1]["status"] != 404:
            direct = fixture(key)
            if direct["data"]["merchant"]["slug"] == value:
                env = direct
        elif entry and "/api/v1/search.json?q=" + value not in manifest():
            result.no_match = True
            return
    if env is None:
        candidates = search(value) if len(value) >= 2 else []
        match = exact_candidate([row for row in candidates if row["kind"] == "merchant"], value)
        if match is None:
            result.no_match = not candidates
            result.data["candidates"] = candidates
            return
        env = fixture(f"merchants/{match['slug']}.json")

    data = env["data"]
    result.data = {k: env[k] for k in ("data_as_of", "disclosure")}
    result.data["store"] = data["merchant"]
    rows = data["rates"]
    if program := args.get("program"):
        rows = [r for r in rows if program in identities(r)] or [
            r for r in rows if any(program in name for name in identities(r))
        ]
        result.data["program_match"] = "matched" if rows else "none"
    result.rows = [
        r for r in rows
        if (args.get("include_stale", True) or not r["is_stale"])
        and ("unit" not in args or r["rate_unit"] == args["unit"])
    ]


def highs_rows(args):
    groups = {}
    for row in fixture("highs.json")["data"]["highs"]:
        if all(row[field] == args[arg] for arg, field in (
            ("unit", "rate_unit"), ("kind", "rate_kind")
        ) if arg in args):
            groups.setdefault(row["rate_unit"], []).append(row)
    # The harness takes one row per sorted unit per round, keeping feed order.
    grouped = [groups[unit] for unit in sorted(groups)]
    rows = [
        group[i] for i in range(max(map(len, grouped), default=0))
        for group in grouped if i < len(group)
    ]
    return rows[:args.get("limit", 20)]


def replay(call):
    args = {k: v.strip().lower() if isinstance(v, str) and k not in ("unit", "kind") else v
            for k, v in call["args"].items()}
    tool = call["tool"]
    result = Result(tool, args)
    try:
        for key in ("query", "store", "portal", "program", "category"):
            if key in args and not (2 if key == "query" else 1) <= len(args[key]) <= 256:
                raise FixtureError(f"invalid {key}")
        if "unit" in args and not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", args["unit"]):
            raise FixtureError("invalid unit")
        if "kind" in args and args["kind"] not in ("one_time_bonus", "earn_rate"):
            raise FixtureError("invalid kind")
        if "limit" in args and not 1 <= args["limit"] <= 100:
            raise FixtureError("invalid limit")
        if tool == "get_store_rates":
            store_result(result)
        elif tool == "search_stores":
            result.data["candidates"] = search(args["query"])
            result.no_match = not result.data["candidates"]
        elif tool == "get_highs":
            result.rows = highs_rows(args)
        else:
            portals = fixture("portals.json")["data"]["portals"]
            if tool == "list_portals":
                category = args.get("category")
                entries = [p for p in portals if not category or category in
                           (p["category"], p["category_label"].lower())]
                result.data["count"] = len(entries)
                result.data["active_count"] = sum(
                    bool(p["is_active"] and p["last_success_at"]) for p in entries
                )
            else:
                value = args["portal"]
                matches = [p for p in portals if p["portal_id"].lower() == value] or [
                    p for p in portals if p["name"].lower() == value
                ]
                if len(matches) != 1:
                    raise FixtureError(f"no unique portal for {value}")
                entry = matches[0]
                profile = fixture(f"portals/{entry['portal_id']}.json")["data"]["portal"]
                result.data["portal"] = dict(profile, is_active=entry["is_active"])
    except FixtureError as exc:
        result.error = str(exc)
    return result


DELTA = {"delta", "delta skymiles", "delta-skymiles", "delta skymiles shopping", "skymiles"}


def relevant(result, required):
    args = required["args"]
    if required["tool"] == "search_stores":
        return (
            (result.tool == "search_stores" and result.args["query"] == args["query"])
            or (result.tool == "get_store_rates" and result.args["store"] == args["query"]
                and (result.no_match or result.data.get("candidates")))
        )
    if result.tool != required["tool"]:
        return False
    if "store" in args:
        return result.data.get("store", {}).get("slug") == args["store"]
    if "portal" in args:
        return result.data.get("portal", {}).get("portal_id") == args["portal"]
    return True


def matches_row(row, fact):
    return all(row.get(k) == v for k, v in fact.items() if k != "type")


def check_evidence(case, results):
    errors = []
    rows = []
    for required in case["evidence"]:
        suitable = [r for r in results if not r.error and relevant(r, required)]
        if not suitable:
            errors.append("no fixture-backed result for " + required["tool"])
            continue
        for r in suitable:
            rows.extend(r.rows)
        for f in case["facts"]:
            kind = f["type"]
            if kind == "row":
                if required["tool"] == "get_highs":
                    candidate_rows = [
                        next((row for row in r.rows if row["rate_unit"] == f["rate_unit"]
                              and row["rate_kind"] == f["rate_kind"]), {})
                        for r in suitable
                    ]
                else:
                    candidate_rows = rows
                if not any(matches_row(row, f) for row in candidate_rows):
                    errors.append("tool results did not return the required " + f["portal_name"] + " row")
            elif kind == "directory_counts" and not any(
                not r.args.get("category")
                and (r.data["count"], r.data["active_count"]) == (f["registered"], f["active"])
                for r in suitable
            ):
                errors.append("tool results did not return the full directory counts")
            elif kind == "date" and f["scope"] == "envelope" and not any(
                (r.data.get("data_as_of") or "")[:10] == f["value"] for r in suitable
            ):
                errors.append("tool results did not return the snapshot date")
            elif kind in ("count", "hours", "inactive", "never_checked"):
                key, expected = {
                    "count": ("merchants_tracked", f.get("value")),
                    "hours": ("cadence_hours", f.get("value")),
                    "inactive": ("is_active", False),
                    "never_checked": ("last_success_at", None),
                }[kind]
                if not any(key in r.data.get("portal", {}) and r.data["portal"][key] == expected
                           for r in suitable):
                    errors.append("tool results did not return the required portal " + kind)
        if "missing_program" in case["tags"] and not any(
            (r.args.get("program") in DELTA and r.data.get("program_match") == "none")
            or ("program" not in r.args and "unit" not in r.args
                and r.args.get("include_stale", True)
                and not any(set(identities(row)) & DELTA for row in r.rows))
            for r in suitable
        ):
            errors.append("tool results do not establish absence of a Delta listing")
        if "missing_merchant" in case["tags"] and not any(r.no_match for r in suitable):
            errors.append("tool results do not establish a recorded no-match search")
        if case["expected_behavior"] == "ask_disambiguation" and not any(
            r.data.get("candidates") for r in suitable
        ):
            errors.append("tool results did not return disambiguation candidates")
    return errors, rows
