#!/usr/bin/env python3
"""Dependency-free example: print every current rate row for a merchant."""
import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://checkbeforeyoushop.com"

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json", "User-Agent": "cbys-developer-kit/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def resolve(query):
    found = get("/api/v1/search.json?" + urllib.parse.urlencode({"q": query}))
    merchants = [r for r in found["data"]["results"] if r["kind"] == "merchant"]
    q = query.strip().lower()
    exact = [r for r in merchants if q in {r["slug"].lower(), r["name"].lower(), (r.get("domain") or "").lower()}]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError("Ambiguous exact merchant match: " + ", ".join(r["name"] for r in exact))
    prefix = [r for r in merchants if r["name"].lower().startswith(q) or r["slug"].lower().startswith(q) or (r.get("domain") or "").lower().startswith(q)]
    candidates = prefix or merchants
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise ValueError("Ambiguous merchant search. Use a store slug or full name: " + ", ".join(r["name"] for r in candidates))
    return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", nargs="?", default="nike", help="merchant slug, name, or domain (default: nike)")
    parser.add_argument("--program", help="show only this portal program, case-insensitive")
    args = parser.parse_args()
    try:
        # A slug is a single URL-safe token. Try the direct merchant endpoint
        # first; use search when it is a name/domain or the slug is unknown.
        result = None
        if args.store and all(ch.isalnum() or ch == "-" for ch in args.store):
            try:
                result = get("/api/v1/merchants/" + urllib.parse.quote(args.store, safe="") + ".json")
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
        if result is None:
            match = resolve(args.store)
            if not match:
                print(f"No tracked merchant found for {args.store!r}.")
                return 0
            result = get("/api/v1/merchants/" + urllib.parse.quote(match["slug"], safe="") + ".json")
    except (ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"Could not resolve merchant: {exc}")
        return 2
    data = result["data"]
    merchant = data["merchant"]
    print(f"{merchant['name']} | {merchant['page_url']}")
    print(f"As of: {result.get('data_as_of') or 'not provided'}")
    if data.get("verdict"):
        print(f"Verdict: {data['verdict']['headline']}")
    rows = data.get("rates", [])
    if args.program:
        rows = [r for r in rows if args.program.casefold() in r["program"].casefold()]
    if not rows:
        print("No tracked rate rows match this selection.")
    for row in rows:
        stale = " [STALE]" if row["is_stale"] else ""
        up_to = " (up to)" if row["is_up_to"] else ""
        print(f"- {row['portal_name']} / {row['program']}: {row['rate_display']} ({row['rate_unit']}; {row['rate_kind']}){up_to}{stale}")
        print(f"  confirmed {row['last_confirmed_at']}; {row.get('go_url') or merchant['page_url']}")
    print(result.get("attribution", ""))
    print(result.get("disclosure", ""))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
