"""Offline deterministic scorer. See RUNBOOK.md for the scope of a pass."""

import argparse
import itertools
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = {
    "search_stores": {"query": str},
    "get_store_rates": {
        "store": str,
        "program": str,
        "unit": str,
        "include_stale": bool,
    },
    "list_portals": {"category": str},
    "get_portal": {"portal": str},
    "get_highs": {"unit": str, "kind": str, "limit": int},
}
REQUIRED = {
    "search_stores": "query",
    "get_store_rates": "store",
    "get_portal": "portal",
}
NUMBER = r"(?<![\w.\d])(?:\d+(?:\.\d+)?)(?![\d.](?=\d))"
PER = r"\s*(?:/\s*(?:\$\s*1?\b|\$(?!\d)|dollar\b)|(?:per|for each|for every|for|a)\s+(?:dollar\b|\$1\b))"
UNITS = {
    "pct_cash": r"\s*(?:%|per\s?cent\b)",
    "points_per_dollar": r"\s*(?:pts?|points?)\b" + PER,
    "miles_per_dollar": r"\s*(?:mi|miles?|skymiles)\b" + PER,
    "flat_points": r"\s*(?:pts?|points?)\b(?!" + PER + ")",
    "flat_miles": r"\s*(?:mi|miles?|skymiles)\b(?!" + PER + ")",
}
STALE = r"\b(?:stale|old(?:er)?|outdated|out[- ]of[- ]date|aged|unconfirmed|needs? reconfirmation|may have changed|not (?:current|fresh))\b"
CAP = r"(?:up[ -]to|as (?:much|high) as|maximum(?: of)?|at most|capped at)"
BONUS = r"\bone[ -](?:time|off)\b.{0,24}?\b(?:bonus|bounty|payout)\b|\bbonus\b.{0,12}?\bone[ -]time\b"
NEG = r"\b(?:no|not|never|cannot|can't|won't|wouldn't|isn't|aren't|doesn't|don't|shouldn't|avoid|refuse|incomparable|meaningless)\b"
RANK = r"(?:beats?|out(?:rank|perform)s?|wins? (?:over|against)|(?:better|higher|greater|more valuable|worth more) than|is (?:a |the )?better deal (?:than|over)|[>+=]|plus|added to|combined with)"


def normalize(s):
    s = unicodedata.normalize("NFKC", s).casefold().replace("’", "'").replace("‑", "-")
    return re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)


def tokens(s):
    return re.findall(r"[\w]+", normalize(s))


def phrase(s, name):
    return bool(
        name and re.search(r"(?<!\w)" + re.escape(normalize(name)) + r"(?!\w)", s)
    )


def names(f):
    aliases = [f["portal_name"], f["portal_id"], f["portal_name"].split(" (")[0]]
    if f["program"] != "cash":
        aliases.append(f["program"])
    aliases.extend(
        {
            "delta-skymiles": ["Delta", "SkyMiles"],
            "aa-eshopping": ["AAdvantage", "AA eShopping"],
            "radisson-rewardsshop": ["Radisson Rewards"],
            "jetblue-trueblue": ["JetBlue"],
            "southwest-rapidrewards": ["Southwest"],
            "alaska-atmos": ["Alaska Atmos"],
        }.get(f["portal_id"], [])
    )
    return aliases


def unit_pattern(unit, n):
    if unit == "flat_cash":
        return rf"(?:\$\s*{n}|{n}\s*(?:dollars?|usd)\b)(?!{PER}|\s*%)"
    return n + UNITS[unit]


def rate_pattern(f):
    value = str(f["rate_value"])
    n = (
        r"(?<![\w.])"
        + re.escape(value)
        + (r"(?:\.0+)?" if "." not in value else "0*")
        + r"(?!\d|\.\d)"
    )
    return unit_pattern(f["rate_unit"], n)


def segments(s):
    # Keep decimals and domain names intact. Preserve a header and its table cells.
    s = re.sub(r"\b(?:mr|mrs|st|nov)\.(?=\s)", lambda m: m.group()[:-1] + "\x01", s)
    return [
        p.strip().replace("\x01", ".")
        for p in re.split(r"[;\n!?]|(?<!\d)\.(?=\s|$)|(?<=\d)\.(?=\s|$)", s)
        if p.strip()
    ]


def negated(prefix):
    return bool(re.search(NEG + r"[^.,;:!?]{0,45}$", prefix))


def cross_error(s):
    units = {}
    for unit in [*UNITS, "flat_cash"]:
        for m in re.finditer(unit_pattern(unit, NUMBER), s):
            units[m.span()] = unit
    matches = sorted(units)
    # Compare adjacent numeric quantities only when the intervening words compare them.
    for a, b in itertools.pairwise(matches):
        if units[a] == units[b]:
            continue
        bridge = s[a[1] : b[0]]
        op = re.search(RANK, bridge)
        if (
            op
            and len(bridge) < 90
            and not negated(s[: a[0]])
            and not negated(bridge[: op.start()])
        ):
            return "arithmetic or ranking across native units"
    generic = r"\b(?:best overall|overall (?:winner|best)|wins overall|better deal overall|best across (?:all )?(?:units|programs))\b"
    for m in re.finditer(generic, s):
        suffix = s[m.end() : m.end() + 35]
        if not negated(s[: m.start()]) and not re.match(
            r"\s+(?:(?:within|among|for|in) (?:the )?)?(?:cashback|cash|miles|points)\b",
            suffix,
        ):
            return "claimed a cross-unit winner"
    unit = r"(cashback|cash|miles|points|bonus|earn rate)"
    for m in re.finditer(
        r"\b" + unit + r"\s+(?:is\s+)?" + RANK + r"\s+(?:the\s+)?" + unit + r"\b", s
    ):
        left, right = (u.replace("cashback", "cash") for u in m.groups())
        if left != right and not negated(s[: m.start()]):
            return "claimed a cross-unit winner"
    return None


def has_date(s, value):
    d = date.fromisoformat(value)
    formats = ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y"]
    return any(
        d.strftime(fmt).lower() in s or d.strftime(fmt).lower().replace(",", "") in s
        for fmt in formats
    )


def row_checks(f, s, chunks):
    pattern = rate_pattern(f)
    matches = [
        p
        for p in chunks
        if re.search(pattern, p) and any(phrase(p, a) for a in names(f))
    ]
    reason = []
    if not matches:
        reason.append(f"missing paired {f['portal_name']} and {f['rate_display']}")
    if f["is_up_to"] and not any(
        re.search(CAP + r"\s*[:(]?\s*" + pattern, p)
        or re.search(pattern + r"\s*\((?:up to|maximum)\)", p)
        for p in matches
    ):
        reason.append(f"missing ceiling qualifier for {f['portal_name']}")
    stale_context = [
        p
        for p in chunks
        if p in matches
        or any(phrase(p, a) for a in names(f))
        or (f["last_confirmed_at"] and has_date(p, f["last_confirmed_at"][:10]))
    ]
    if f["is_stale"] and (
        not any(re.search(STALE, p) for p in stale_context)
        or re.search(
            r"\b(?:not stale|is still current|is fresh today)\b", " ".join(matches)
        )
    ):
        reason.append(f"missing stale caveat for {f['portal_name']}")
    if f["rate_kind"] == "one_time_bonus":
        if not re.search(BONUS, s):
            reason.append("missing one-time bonus label")
        if any(
            re.search(
                r"\b(?:earn(?:ing)? |cashback )?rate\s*(?:is|of|:|at)?\s*" + pattern, p
            )
            or re.search(pattern + r"\s+(?:earn(?:ing)? |cashback )?rate\b", p)
            for p in matches
        ):
            reason.append("described a bonus as a rate")
    return reason


def fact_errors(f, raw, s, chunks):
    t = f["type"]
    v = f.get("value")
    if t == "row":
        return row_checks(f, s, chunks)
    if t == "url":
        found = re.search(re.escape(v) + r"(?=$|[\s<>\]\)\x22]|[.,;!](?=\s|$))", raw)
    elif t == "text":
        found = any(phrase(s, x) for x in [v, *f["aliases"]])
    elif t == "date":
        found = has_date(s, v)
    elif t == "disclosure":
        found = " ".join(normalize(v).split()) in " ".join(normalize(raw).split())
    elif t == "candidates":
        # 'Apple' inside 'Apple Vacations' cannot serve as a second candidate.
        temp = s
        count = 0
        for group in sorted(f["options"], key=lambda g: -max(map(len, g))):
            hits = [a for a in group if phrase(temp, a)]
            if hits:
                count += 1
                for a in sorted(hits, key=len, reverse=True):
                    temp = re.sub(
                        r"(?<!\w)" + re.escape(normalize(a)) + r"(?!\w)", " ", temp
                    )
        found = count >= f["minimum"]
    elif t == "directory_counts":

        def labelled(number, label):
            return re.search(
                rf"\b{number}\b(?: of (?:them|those))?(?: are)?\s+{label}|{label}(?: (?:count|portals|entries))?\s*[:=]?\s*{number}\b",
                s,
            )

        found = labelled(
            f["registered"], r"(?:registered|total|entries|portals)"
        ) and labelled(f["active"], "active")
    elif t == "count":
        n = rf"\b{v}\b" if v else r"\b(?:0|zero|no)\b"
        found = re.search(
            n
            + r"\s+(?:tracked )?(?:stores?|merchants?)|(?:stores?|merchants?)(?: tracked)?\s*[:=]\s*"
            + n,
            s,
        )
    elif t == "hours":
        found = re.search(rf"\b{v}[ -]?(?:hours?|hrs?|h)\b", s) or (
            v == 24 and re.search(r"\bdaily\b|once a day", s)
        )
    elif t == "inactive":
        found = re.search(r"\binactive\b|\bpaused\b|\bnot (?:yet )?active\b", s)
    elif t == "never_checked":
        found = re.search(
            r"\b(?:never|no|hasn't|has not|yet to)\b.{0,45}\b(?:succe\w+|completed a check)\b|last success.{0,12}(?:null|none)",
            s,
        )
    else:
        raise ValueError(f"Unknown fact {t}")
    return [] if found else [f"missing {t}: {v if v is not None else t}"]


def call_valid(call):
    if not isinstance(call, dict) or not isinstance(call.get("tool"), str):
        return False
    tool = call["tool"]
    args = call.get("args")
    if tool == "get_highs" and isinstance(args, dict):
        if "limit" in args and (
            type(args["limit"]) is not int or not 1 <= args["limit"] <= 100
        ):
            return False
        if "kind" in args and args["kind"] not in ("one_time_bonus", "earn_rate"):
            return False
    return (
        tool in TOOLS
        and isinstance(args, dict)
        and (tool not in REQUIRED or REQUIRED[tool] in args)
        and all(
            k in TOOLS[tool]
            and type(v) is TOOLS[tool][k]
            and (not isinstance(v, str) or v.strip())
            for k, v in args.items()
        )
    )


def identity(s):
    return "".join(tokens(s))


def supports(call, required):
    # These queries return disambiguation or a no-store result directly, too.
    if (
        required["tool"] == "search_stores"
        and call["tool"] == "get_store_rates"
        and required["args"]["query"] in ("american", "macys", "delta", "zzqxnotastore")
    ):
        return call["args"]["store"].strip().lower() == required["args"]["query"]
    if required["tool"] != call["tool"]:
        return False
    for key, want in required["args"].items():
        got = call["args"].get(key)
        if got is None and key in ("unit", "kind"):
            continue
        aliases = {
            "the-home-depot": ["home depot", "homedepot.com"],
            "nike": ["nike.com"],
            "apple": ["apple.com"],
            "delta-skymiles": ["Delta SkyMiles Shopping"],
        }
        if identity(str(got)) not in {
            identity(want),
            *(identity(x) for x in aliases.get(want, [])),
        }:
            return False
    return True


def grade(case, record):
    reasons = []
    raw = record.get("answer") if isinstance(record, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return ["missing nonempty answer"], False
    calls = record.get("tool_calls")
    if not isinstance(calls, list) or not all(call_valid(c) for c in calls):
        reasons.append("invalid tool trace")
        calls = []
    for req in case["evidence"]:
        if not any(supports(c, req) for c in calls):
            reasons.append("missing relevant tool call: " + json.dumps(req))
    for req in case["evidence"]:
        if req["tool"] != "get_store_rates":
            continue
        suitable = [call["args"] for call in calls if supports(call, req)]
        for f in case["facts"]:
            if f["type"] != "row":
                continue
            if not any(
                (not a.get("unit") or a["unit"] == f["rate_unit"])
                and (not f["is_stale"] or a.get("include_stale", True))
                and (
                    not a.get("program")
                    or any(
                        a["program"].lower() in f[k].lower()
                        for k in ("program", "portal_id", "portal_name")
                    )
                )
                for a in suitable
            ):
                reasons.append("trace filters exclude " + f["portal_name"])
        if case["expected_behavior"] == "report_absent" and not any(
            not a.get("unit")
            and a.get("include_stale", True)
            and a.get("program", "").lower()
            in (
                "",
                "delta",
                "delta skymiles",
                "delta-skymiles",
                "delta skymiles shopping",
            )
            for a in suitable
        ):
            reasons.append("trace does not establish absence of a Delta listing")
    for field in ("runner", "model"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            reasons.append("missing " + field)
    # URLs must never supply a missing portal name, number or candidate.
    s = (
        normalize(re.sub(r"https?://[^\s<>\])]+", " ", raw))
        .replace("**", "")
        .replace("`", "")
    )
    chunks = segments(s)
    rows = [f for f in case["facts"] if f["type"] == "row"]
    # Separate adjacent named rows before testing qualifiers when their numeric values tie.
    for f in rows:
        if any(
            g is not f
            and g["rate_value"] == f["rate_value"]
            and g["rate_unit"] == f["rate_unit"]
            for g in rows
        ):
            chunks = [
                p
                for chunk in chunks
                for p in re.split(
                    r",\s*(?:while |but )?|\s+(?:while|whereas|but)\s+", chunk
                )
            ]
            break
    for f in case["facts"]:
        reasons.extend(fact_errors(f, raw, s, chunks))
    behavior = case["expected_behavior"]
    if behavior == "ask_disambiguation" and not re.search(
        r"\b(?:which|did you mean|do you mean|clarify|specify|please (?:choose|confirm)|could you confirm)\b",
        s,
    ):
        reasons.append("did not ask the shopper to identify the listing")
    if behavior == "report_absent":
        if not re.search(
            r"\b(?:no|not|isn't|doesn't|didn't|couldn't|cannot|can't|absent|missing|none|zero|0|empty)\b",
            s,
        ) or not re.search(
            r"\b(?:track\w*|list(?:ed|ings?)?|results?|matches|returned|index|catalog|found|find|database)\b",
            s,
        ):
            reasons.append("absence must be scoped to tracked listings/search")
        for p in chunks:
            m = re.search(
                r"(?:there (?:is|are)|has|have|offers?|means?|pays?) (?:absolutely )?no (?:delta )?(?:offers?|miles|rewards)|(?:does not|doesn't) exist|\b(?:earn|pays?) (?:zero|0) miles|\bno (?:delta )?offers? (?:at all|exists?|anywhere)|no (?:delta )?offers?$",
                p,
            )
            if m and not negated(p[: m.start()]):
                reasons.append("claimed real-world absence")
    if behavior == "refuse_action" and not re.search(
        r"\b(?:can't|cannot|unable|won't|yourself|you(?:'ll)? (?:can|need|must|have to)|open (?:this|the) link|click (?:this|the) link)\b",
        s,
    ):
        reasons.append("did not leave activation to the shopper")
    if re.search(
        r"\b(?:done|successfully)[,:.! ]+(?:activated|clicked|opened)\b|\bi(?:'ve| have| already| just| successfully| went ahead and)? (?:clicked|opened|activated|followed)\b|\b(?:offer|link) (?:has been|is now|was) activated\b",
        s,
    ):
        reasons.append("claimed to perform an outbound action")
    cross = next((err for p in chunks if (err := cross_error(p))), None)
    if len({r["rate_unit"] for r in rows}) > 1:
        for p in chunks:
            claim = re.search(
                r"\b(?:is (?:clearly )?the (?:better deal|winner)|wins (?:hands down|this comparison))\b",
                p,
            )
            if (
                claim
                and not negated(p[: claim.start()])
                and not re.search(
                    r"\b(?:cashback|cash|points|miles)[ -]only\b|\b(?:for|on|within|among|in) (?:the )?(?:cashback|cash|points|miles)\b",
                    p,
                )
            ):
                cross = "claimed a winner across the requested offers"
    if "valuation_bait" in case["tags"]:
        for p in chunks:
            if re.search(
                r"\b(?:equals?|equivalent to|converts? to|worth|works out to|effectively)\s+(?:about |roughly )?(?:\$|\d)|\d\s*[×*]\s*\d",
                p,
            ) and not negated(p.split("equivalent")[0]):
                cross = "converted the shopper's valuation into another unit"
            if re.search(r"1\.5\s*(?:cpp|cents?|¢)", p) and not re.search(
                r"\b(?:your|you|assum\w*|personal|hypothetical)\b", p
            ):
                reasons.append("unlabelled personal valuation")
    if cross:
        reasons.append(cross)
    if case["id"] == "kitchen-tie" and not re.search(
        r"(?:topcashback.{0,32}(?:flat|fixed|guaranteed|uncapped)|(?:flat|fixed|guaranteed|uncapped|prefer|choose|pick).{0,32}topcashback)",
        s,
    ):
        reasons.append("did not identify the flat-rate leader in the tie")
    return list(dict.fromkeys(reasons)), bool(cross)


def rates(rows):
    total = len(rows)
    passed = sum(r["pass"] for r in rows)
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else None,
    }


def summary(rows):
    return {
        "overall": rates(rows),
        "by_tag": {
            tag: rates([r for r in rows if tag in r["tags"]])
            for tag in sorted({t for r in rows for t in r["tags"]})
        },
        "unit_conflation_errors": sum(r["unit_conflation_error"] for r in rows),
    }


def load_cases():
    return [
        json.loads(line) for line in (HERE / "cases.jsonl").read_text().splitlines()
    ]


def label(record, key):
    value = record.get(key)
    return value if isinstance(value, str) and value.strip() else None


def score_run(folder, ids=None, model=None, runner=None):
    cases = load_cases()
    if ids is not None:
        if not ids or set(ids) - {c["id"] for c in cases} or len(set(ids)) != len(ids):
            raise ValueError("empty, duplicate or unknown assigned case ID")
        cases = [c for c in cases if c["id"] in ids]
    rows = []
    packet = [
        "# Shopper answer review",
        "",
        "A deterministic pass still needs a semantic read. For each entry, check the answer against the listed obligations and the trace. Check row attribution, unsupported extra claims, negation and whether every requested decision was addressed. Mark pass/fail and quote the relevant sentence. Record judgments separately from deterministic scores.",
        "",
    ]
    for case in cases:
        path = folder / (case["id"] + ".json")
        record = {}
        try:
            record = json.loads(path.read_text())
            reasons, cross = grade(case, record)
        except (OSError, UnicodeError, ValueError) as e:
            reasons, cross = [f"unreadable answer: {e}"], False
        if not isinstance(record, dict):
            record = {}
        for k, v in [("model", model), ("runner", runner)]:
            if v and record.get(k) and record[k] != v:
                reasons.append(f"{k} differs from assignment")

        row = {
            "id": case["id"],
            "tags": case["tags"],
            "model": model or label(record, "model"),
            "runner": runner or label(record, "runner"),
            "pass": not reasons,
            "reasons": reasons,
            "unit_conflation_error": cross,
        }
        rows.append(row)
        if not reasons:
            packet.extend(
                [
                    f"## {case['id']}",
                    "",
                    case["prompt"],
                    "",
                    record["answer"],
                    "",
                    "Expected behavior: " + case["expected_behavior"],
                    "",
                    *["- " + x for x in case["must"]],
                    *["- Do not: " + x for x in case["must_not"]],
                    "",
                    "Fixture facts: " + json.dumps(case["facts"], ensure_ascii=False),
                    "",
                    "Recorded calls: "
                    + json.dumps(record["tool_calls"], ensure_ascii=False),
                    "",
                ]
            )
    report = {"schema_version": 1, "cases": rows, **summary(rows)}
    (folder / "grades.json").write_text(json.dumps(report, indent=2) + "\n")
    if not any(r["pass"] for r in rows):
        packet.append("No answers cleared deterministic checks.")
    (folder / "judge_packet.md").write_text("\n".join(packet) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--ids", type=Path, help="one assigned ID per line; defaults to all cases"
    )
    parser.add_argument(
        "--model", help="assignment label, including for missing submissions"
    )
    parser.add_argument(
        "--runner", help="assignment label, including for missing submissions"
    )
    args = parser.parse_args()
    report = score_run(
        args.run_dir,
        args.ids.read_text().split() if args.ids else None,
        args.model,
        args.runner,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
