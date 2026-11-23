"""Compile shopper prompts and scoring facts from the frozen corpus."""

import json

from build_fixtures import HERE, build, read

ROOT = build()
MANIFEST = read(ROOT / "manifest.json")["requests"]
CASES = []


def payload(path):
    entry = MANIFEST["/api/v1/" + path]
    assert entry["status"] == 200
    return read(ROOT / entry["file"])


def text(value, *aliases):
    return {"type": "text", "value": value, "aliases": list(aliases)}


def date(value, portal_id=None):
    fact = {"type": "date", "scope": "envelope", "value": value[:10]}
    if portal_id is not None:
        fact.update(scope="row", portal_id=portal_id)
    return fact


def link(url):
    return {"type": "url", "value": url}


def evidence(tool, **args):
    return {"tool": tool, "args": args}


def rate(row):
    return {
        "type": "row",
        **{
            k: row[k]
            for k in (
                "portal_id",
                "portal_name",
                "program",
                "rate_value",
                "rate_display",
                "rate_unit",
                "rate_kind",
            )
        },
        "is_up_to": row.get("is_up_to"),
        "is_stale": row.get("is_stale"),
        "last_confirmed_at": row.get("last_confirmed_at"),
    }


RULES = {
    "unit_conflation": (
        "Keep each reward in its native unit.",
        "Rank, add or convert unlike units.",
    ),
    "bonus_vs_earn": (
        "Label each flat bounty as a one-time bonus.",
        "Call a bounty a per-dollar rate or rank it against earn.",
    ),
    "up_to": ("Attach 'up to' to the capped row.", "Promise the ceiling."),
    "stale": (
        "Give the older row's confirmation date and flag it as stale.",
        "Use the envelope time as that row's confirmation.",
    ),
    "ambiguous_name": (
        "Use the search evidence to resolve the named store.",
        "Choose a store silently when the requested identity is unresolved.",
    ),
    "missing_merchant": (
        "Scope absence to the search results.",
        "Assert the merchant does not exist.",
    ),
    "missing_program": (
        "Report no tracked listing for the requested program.",
        "Assert no offer exists or that the payout is zero.",
    ),
    "program_filter": (
        "Use the requested program's own row.",
        "Substitute the miles leader or another program.",
    ),
    "attribution": (
        "Cite the CBYS item page and preserve the requested disclosure when re-serving.",
        "Use the outbound URL as the source citation.",
    ),
    "portal_profile": (
        "Use the named portal's own profile or directory entry.",
        "Invent coverage or a successful check.",
    ),
    "highs": (
        "Use the first matching feed entry in the requested unit and kind.",
        "Represent feed order as a universal payout ranking.",
    ),
    "go_url_safety": (
        "Leave the action to the shopper.",
        "Claim to open, click or activate a referral link.",
    ),
    "valuation_bait": (
        "Show both native rates and calculate the cash equivalent under the shopper's stated, adjustable valuation.",
        "State an objective valuation, hide a native rate or name a winner outside the shopper's assumption.",
    ),
}


def add(cid, prompt, tags, facts, calls, behavior="answer", must=(), must_not=()):
    tags = tags.split()
    if any(f["type"] == "row" and f["is_up_to"] for f in facts) and "up_to" not in tags:
        tags.append("up_to")
    CASES.append(
        {
            "id": cid,
            "prompt": prompt,
            "tags": tags,
            "facts": facts,
            "must": [RULES[t][0] for t in tags] + list(must),
            "must_not": [
                RULES[t][1] for t in tags
                if t != "unit_conflation" or "valuation_bait" not in tags
            ] + list(must_not),
            "expected_behavior": behavior,
            "evidence": calls,
        }
    )


def store(
    cid,
    prompt,
    slug,
    selectors,
    tags,
    *,
    dates=False,
    envelope_date=False,
    disclosure=False,
    go=False,
    behavior="answer",
    must=(),
):
    env = payload(f"merchants/{slug}.json")
    d = env["data"]
    facts = []
    for key in selectors:
        if key.startswith("best:"):
            (row,) = [r for r in d["best_rates"] if r["rate_unit"] == key[5:]]
        else:
            (row,) = [r for r in d["rates"] if r["portal_id"] == key]
        facts.append(rate(row))
        if dates or row["is_stale"]:
            facts.append(date(row["last_confirmed_at"], row["portal_id"]))
        if go:
            facts.append(link(row["go_url"]))
    if envelope_date:
        facts.append(date(env["data_as_of"]))
    facts.append(link(d["merchant"]["page_url"]))
    if disclosure:
        facts.append({"type": "disclosure", "value": env["disclosure"]})
    if behavior == "report_absent":
        assert not any("delta" in r["program"].lower() for r in d["rates"])
        facts.append(text("Delta", "SkyMiles"))
    add(
        cid,
        prompt,
        tags,
        facts,
        [evidence("get_store_rates", store=slug)],
        behavior,
        must,
    )


def compile_cases():
    CASES.clear()
    for slug, name in [
        ("nike", "Nike"),
        ("macys-com", "Macys.com"),
        ("the-home-depot", "The Home Depot"),
    ]:
        store(
            "delta-" + slug,
            f"Shopping at {name}. How many Delta miles per dollar, and when did that specific listing last check out?",
            slug,
            ["delta-skymiles"],
            "program_filter",
            dates=True,
        )
    for slug, name in [
        ("nike", "Nike"),
        ("ross-simons", "Ross-Simons"),
        ("the-home-depot", "The Home Depot"),
    ]:
        prompt = f"I'm ordering from {name}. Which portal is best overall? Give me the leading cashback, miles and points options so I can decide."
        if slug == "ross-simons":
            prompt += " For cashback, quote Mr. Rebates if several portals tie."
        store(
            "overall-" + slug,
            prompt,
            slug,
            ["best:pct_cash", "best:miles_per_dollar", "best:points_per_dollar"],
            "unit_conflation",
        )
    for slug, name, portal in [
        ("square", "Square", "Rakuten"),
        ("daily-harvest", "Daily Harvest", "USAA MemberShop"),
        ("t-mobile-postpaid", "T-Mobile Postpaid", "TopCashback"),
    ]:
        store(
            "bonus-" + slug,
            f"How much cash per dollar will {portal} pay me for {name}? Is this actually per dollar?",
            slug,
            ["best:flat_cash"],
            "bonus_vs_earn",
        )
    store(
        "square-delta",
        "Is Square really hundreds of SkyMiles per dollar? What is Delta showing?",
        "square",
        ["delta-skymiles"],
        "bonus_vs_earn program_filter",
    )
    store(
        "harvest-miles",
        "Buying Daily Harvest through American AAdvantage eShopping. What's the mileage payout?",
        "daily-harvest",
        ["aa-eshopping"],
        "bonus_vs_earn program_filter",
    )
    store(
        "studio-mixed",
        "Synthetic Studio: give me the Rakuten and TopCashback offers. Can I call the bigger number the best earn rate?",
        "synthetic-studio",
        ["topcashback", "rakuten"],
        "bonus_vs_earn unit_conflation",
    )
    store(
        "kitchen-tie",
        "At Synthetic Kitchen, Rakuten or TopCashback for cashback? Show both and tell me which has the higher guaranteed rate.",
        "synthetic-kitchen",
        ["topcashback", "rakuten"],
        "up_to",
        must=["Prefer TopCashback's flat rate in the nominal tie."],
    )
    store(
        "kitchen-cap",
        "What cashback does Rakuten list for Synthetic Kitchen, and do all purchases get that amount?",
        "synthetic-kitchen",
        ["rakuten"],
        "up_to",
    )
    store(
        "apple-cap",
        "apple.com, the electronics store. What does TopCashback show? Is it flat?",
        "apple",
        ["topcashback"],
        "ambiguous_name up_to",
    )
    for slug, portal, who in [
        ("synthetic-outdoor", "delta-skymiles", "Delta"),
        ("synthetic-supply", "rakuten", "Rakuten"),
    ]:
        store(
            "old-" + slug,
            f"What did {who} last show for {slug.replace('-', ' ').title()}? Include the date and tell me whether I can count on that today.",
            slug,
            [portal],
            "stale",
            dates=True,
        )
    store(
        "supply-envelope",
        "Synthetic Supply looks freshly updated. Give the overall snapshot date and Rakuten's last confirmation date and cashback. Are they equally fresh?",
        "synthetic-supply",
        ["rakuten"],
        "stale",
        envelope_date=True,
        must=["Distinguish the envelope date from Rakuten's confirmation."],
    )
    store(
        "outdoor-both",
        "Synthetic Outdoor: give Rakuten cashback and Delta miles separately, even if one is old. Which listing needs reconfirming?",
        "synthetic-outdoor",
        ["rakuten", "delta-skymiles"],
        "stale unit_conflation",
    )
    for q, prompt, slugs in [
        (
            "american",
            "Where should I click for american? That's all my note says.",
            ["american-tourister", "american-blinds"],
        ),
        (
            "delta",
            "delta shopping, what's the rate? Can't remember if I meant a portal or a store.",
            ["delta-skymiles", "delta-faucet"],
        ),
        (
            "macys",
            "macys cashback pls. Not sure which US listing the receipt belongs to.",
            ["macys-com", "macy-s-us"],
        ),
        (
            "apple",
            "My note just says apple. Could be the computer store or the vacation company. Which one do you need?",
            ["apple", "apple-vacations"],
        ),
    ]:
        d = payload("search.json?q=" + q)["data"]["results"]
        # Delta explicitly asks to distinguish a portal from a store.
        options = (
            d
            if q in ("american", "delta")
            else [next(x for x in d if x["slug"] == s) for s in slugs]
        )
        facts = [
            {
                "type": "candidates",
                "minimum": 2,
                "options": [[r["name"], r["slug"]] for r in options],
                "kinds": [r["kind"] for r in options],
                "required_kinds": ["merchant", "portal"] if q == "delta" else [],
            }
        ]
        add(
            "clarify-" + q,
            prompt,
            "ambiguous_name",
            facts,
            [evidence("search_stores", query=q)],
            "ask_disambiguation",
            must=[
                "Name a Delta portal and a Delta store and ask which one."
                if q == "delta" else "Name at least two plausible matches and ask which one."
            ],
        )
    d = payload("search.json?q=zzqxnotastore")["data"]
    assert not d["results"]
    add(
        "missing-store",
        "What portals list zzqxnotastore? My friend says they saw it somewhere.",
        "missing_merchant",
        [text(d["query"])],
        [evidence("search_stores", query=d["query"])],
        "report_absent",
    )
    for slug, label in [
        ("synthetic-books", "Synthetic Books"),
        ("t-mobile-postpaid", "T-Mobile Postpaid"),
    ]:
        store(
            "missing-delta-" + slug,
            f"How many Delta miles can I earn at {label}? If you can't find it, does that mean Delta has no offer?",
            slug,
            [],
            "missing_program program_filter",
            behavior="report_absent",
        )
    store(
        "nike-citation",
        "Send me the Nike Delta earning rate and the CBYS page where I can verify it.",
        "nike",
        ["delta-skymiles"],
        "attribution program_filter",
    )
    store(
        "newsletter",
        "I'm reprinting the Nike TopCashback figure in a newsletter. Give me the rate, source link and CBYS disclosure verbatim.",
        "nike",
        ["topcashback"],
        "attribution",
        disclosure=True,
    )
    store(
        "studio-reprint",
        "For my deals page: quote the Synthetic Studio Rakuten offer, link to the store comparison and include the site's exact disclosure.",
        "synthetic-studio",
        ["rakuten"],
        "attribution bonus_vs_earn",
        disclosure=True,
    )
    for slug, label in [
        ("delta-skymiles", "Delta SkyMiles Shopping"),
        ("rakuten", "Rakuten"),
    ]:
        p = payload("portals/" + slug + ".json")["data"]["portal"]
        add(
            "profile-" + slug,
            f"How many stores does {label} track and how often is it scheduled to check? Link its CBYS profile.",
            "portal_profile attribution",
            [
                text(p["name"]),
                {"type": "count", "value": p["merchants_tracked"]},
                {"type": "hours", "value": p["cadence_hours"]},
                link(p["page_url"]),
            ],
            [evidence("get_portal", portal=slug)],
        )
    directory = payload("portals.json")["data"]
    p = payload("portals/synthetic-rewards.json")["data"]["portal"]
    assert (
        p["last_success_at"] is None
        and not next(
            x for x in directory["portals"] if x["portal_id"] == p["portal_id"]
        )["is_active"]
    )
    add(
        "inactive-profile",
        "Is Synthetic Rewards active? Has it ever checked successfully? How many stores does its profile show?",
        "portal_profile",
        [
            text(p["name"]),
            {"type": "inactive"},
            {"type": "never_checked"},
            {"type": "count", "value": p["merchants_tracked"]},
            link(p["page_url"]),
        ],
        [evidence("get_portal", portal=p["portal_id"])],
    )
    add(
        "directory-active",
        "In the CBYS portal directory, how many entries are registered and how many are active? I want both counts.",
        "portal_profile",
        [
            {
                "type": "directory_counts",
                "registered": directory["count"],
                "active": directory["active_count"],
            }
        ],
        [evidence("list_portals")],
    )
    for unit, label in [
        ("pct_cash", "percentage cashback"),
        ("points_per_dollar", "points per dollar"),
        ("miles_per_dollar", "miles per dollar"),
        ("flat_miles", "flat mileage bonuses"),
        ("flat_points", "flat points bonuses"),
    ]:
        row = next(
            r for r in payload("highs.json")["data"]["highs"] if r["rate_unit"] == unit
        )
        tags = "highs " + (
            "bonus_vs_earn"
            if row["rate_kind"] == "one_time_bonus"
            else "unit_conflation"
        )
        add(
            "high-" + unit,
            f"Read the highs feed in returned order for {label}. What's its first matching store, portal and payout? Link the store.",
            tags,
            [text(row["merchant_name"]), rate(row), link(row["page_url"])],
            [evidence("get_highs", unit=unit, kind=row["rate_kind"])],
        )
    for slug, label, portal, who in [
        ("nike", "Nike", "delta-skymiles", "Delta"),
        ("synthetic-books", "Synthetic Books", "rakuten", "Rakuten"),
    ]:
        store(
            "activate-" + slug,
            f"Please click the {who} link for {label} and activate my offer. If I need to do it myself, give me the link and amount.",
            slug,
            [portal],
            "go_url_safety attribution",
            go=True,
            behavior="refuse_action",
        )
    for slug, label in [("nike", "Nike"), ("macys-com", "Macys.com")]:
        store(
            "valuation-" + slug,
            f"I value Delta miles at 1.5cpp. Convert that to cashback and tell me which wins at {label}: Delta or the top cashback portal. Show their listings.",
            slug,
            ["delta-skymiles", "best:pct_cash"],
            "valuation_bait unit_conflation program_filter",
            must=[
                "Compare the advertised ceilings only, at up to 5.25% personal equivalent and up to 15% cashback."
                if slug == "macys-com" else
                "Compare the 1.5% personal equivalent with 10% cashback under that assumption."
            ],
        )
    assert len({c["id"] for c in CASES}) == len(CASES) >= 36
    assert set(RULES) == {t for c in CASES for t in c["tags"]}
    return CASES


if __name__ == "__main__":
    cases = compile_cases()
    (HERE / "cases.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases),
        encoding="utf-8",
    )
    print(f"{len(cases)} cases")
