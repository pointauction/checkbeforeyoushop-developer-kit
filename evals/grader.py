"""Offline deterministic scorecard for the shopper eval."""

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from build_fixtures import LIVE, read
from claims import (
    BONUS, CAP, CURRENT, DATE_WORDS, DAYS_OLD, STALE, Claims, amounts, has_date,
    normalize, number_words, phrase, phrase_pattern, segments, text_answer,
)
from evidence import call_valid, check_evidence, replay

HERE = Path(__file__).resolve().parent
SNAPSHOT = date.fromisoformat(read(LIVE / "manifest.json")["captured_at"][:10])
NEG = r"\b(?:no|not|never|cannot|can't|won't|wouldn't|isn't|aren't|doesn't|don't|shouldn't|incomparable)\b"
def fact_errors(f, raw, s):
    t = f["type"]
    v = f.get("value")
    if t == "url":
        found = re.search(re.escape(v) + r"(?=$|[\s<>\]\)\x22]|[.,;!](?=\s|$))", raw)
    elif t == "text":
        found = any(phrase(s, x) for x in [v, *f["aliases"]])
    elif t == "disclosure":
        found = " ".join(normalize(v).split()) in " ".join(normalize(raw).split())
    elif t == "candidates":
        # A shorter name inside a longer candidate cannot count twice.
        temp = s
        hits = set()
        options = sorted(zip(f["options"], f["kinds"]),
                         key=lambda pair: -max(map(len, pair[0])))
        for options, kind in options:
            if any(phrase(temp, a) for a in options):
                hits.add((options[0], kind))
                for alias in options:
                    temp = re.sub(phrase_pattern(alias), " ", temp)
        found = len(hits) >= f["minimum"] and set(f["required_kinds"]) <= {k for _, k in hits}
    elif t == "directory_counts":

        def labelled(number, label):
            return re.search(
                rf"\b{number}\b(?: of (?:them|those))?(?: (?:are|were|currently have))?\s+{label}|{label}(?: (?:count|portals|entries))?\s*[:=]?\s*{number}\b",
                s,
            )

        found = labelled(
            f["registered"], r"(?:registered|total|entries|portals)"
        ) and labelled(f["active"], r"active(?: status)?")
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


def negated(prefix):
    return bool(re.search(NEG + r"[^.,;:!?]{0,55}$", prefix))


def supported_amount(amount, rows, text):
    for r in rows:
        if r["rate_unit"] != amount.unit:
            continue
        if Decimal(str(r["rate_value"])) == amount.value:
            return r
        label = r.get("best_category_label")
        if label and (phrase(text, label) or phrase(text, "category")):
            # Store rows expose the top category plus a base and ceiling.
            if Decimal(str(r.get("best_category_value") or 0)) == amount.value:
                return r
    return None


def relative_age(fragment):
    return {int(m) for m in re.findall(DAYS_OLD, fragment.text)}


def dates_in(text):
    months = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+"
    return re.findall(
        rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|{months}\d{{1,2}}(?:,?\s+\d{{4}})?|"
        r"\d{1,2}/\d{1,2}/\d{4})", text
    )


def date_matches(label, day):
    if has_date(label, day.isoformat()):
        return True
    if re.search(r"\d{4}", label):
        return False
    # The corpus fixes the year of short month-and-day dates.
    return any(phrase(normalize(label), day.strftime(fmt).lower())
               for fmt in ("%B %d", "%b %d", "%b. %d"))


def date_assertions(fragment, value):
    day = date.fromisoformat(value)
    return [date_matches(label, day) for label in dates_in(fragment.text)] + [
        diff == (SNAPSHOT - day).days for diff in relative_age(fragment)
    ]


def row_checks(fact, claims, evidence_rows, outcome):
    portal = fact["portal_id"]
    fragments = claims.for_portal(portal)
    native = [r for r in evidence_rows if r["portal_id"] == portal] or [fact]
    unit = fact["rate_unit"]
    value = Decimal(str(fact["rate_value"]))
    name = fact["portal_name"]
    matching = []
    for frag in fragments:
        for amount in frag.amounts:
            text = frag.text
            known = supported_amount(amount, native, text)
            contextual = bool(re.search(r"\b(?:spend(?:ing)?|of eligible|per purchase|(?:above|below|on|at) \$\d+|"
                                        r"fixed bonus|total bonus|cents? per mile)\b", text))
            if amount.negative and amount.unit == unit and amount.value == value:
                outcome.errors.append(f"negated required payout for {name}")
                continue
            if known is None and not contextual:
                if re.search(r"\b(?:also|pays?|earn\w*|lists?|exactly|rate is|offered|showed)\b", text):
                    outcome.errors.append(f"payout claim for {name} absent from tool results")
                else:
                    outcome.review.append(f"could not resolve additional amount for {name}")
            if amount.unit != unit or amount.value != value or amount.negative:
                continue
            # Keep comparisons and descriptions of the ceiling separate from promises.
            if fact["is_up_to"] and not amount.capped and re.search(
                r"\b(?:every purchase|always (?:earns?|pays?)|earns? exactly|guarantee(?:s|d)?)\b", text
            ):
                outcome.errors.append(f"promised the capped payout for {name}")
            if fact["rate_kind"] == "one_time_bonus" and (
                re.search(r"\brate\s*(?:is|of|:|at)?\s*$", text[:amount.start])
                or re.match(r"\s+rate\s+(?:on|per|for)\b", text[amount.end:])
            ):
                outcome.errors.append(f"described {name}'s bonus as a rate")
            matching.append((frag, amount))
    if not matching:
        unresolved = any(frag.portals != {portal} and
                         any(a.unit == unit and a.value == value for a in frag.amounts)
                         and (portal in frag.portals or not frag.portals)
                         for frag in claims.fragments)
        target = outcome.review if unresolved else outcome.errors
        target.append(f"could not verify paired {name} and {fact['rate_display']}")
        return
    if fact["is_up_to"] and not any(a.capped for _, a in matching):
        outcome.errors.append(f"missing ceiling qualifier for {name}")
    if fact["is_up_to"] is False and unit.endswith("cash") and all(a.capped for _, a in matching):
        outcome.errors.append(f"treated the flat payout for {name} as capped")
    bonus_context = [f for f, _ in matching] + [
        f for f in fragments if not f.amounts
        and re.match(r"^(?:it|this|that|the payout) (?:is|was)\b", f.text)
    ]
    if fact["rate_kind"] == "one_time_bonus" and not any(
        re.search(BONUS, frag.text) for frag in bonus_context
    ):
        outcome.errors.append(f"missing one-time bonus label for {name}")
    stale_context = [frag for frag in fragments if frag.amounts or
                     re.search(r"\b(?:listing|rate|flagged|marked|ago|earlier)\b", frag.text)]
    if fact["is_stale"]:
        age = (SNAPSHOT - date.fromisoformat(fact["last_confirmed_at"][:10])).days
        stale = any(re.search(STALE, f.text) or age in relative_age(f) for f in stale_context)
        current = any(re.search(CURRENT, f.text) for f in stale_context)
        if not stale or current:
            outcome.errors.append(f"missing or contradicted stale caveat for {name}")
    elif fact["is_stale"] is False and any(
        re.search(r"\bstale\b", f.text) and not re.search(r"\bnot stale\b", f.text)
        and not re.search(r"\b(?:can|may) (?:change or )?go stale\b", f.text)
        for f in stale_context if f.amounts or re.search(r"\b(?:is|was|flagged|marked)\s+(?:as )?stale\b", f.text)
    ):
        outcome.errors.append(f"called a nonstale listing stale for {name}")


def date_checks(fact, claims, outcome):
    if fact["scope"] == "envelope":
        fragments = [f for f in claims.fragments if f.envelope]
        label = "overall snapshot"
    else:
        portal = fact["portal_id"]
        fragments = [f for f in claims.for_portal(portal) if f.amounts or re.search(DATE_WORDS, f.text)]
        label = portal
    assertions = [matches for f in fragments for matches in date_assertions(f, fact["value"])]
    if not any(assertions):
        ambiguous = not assertions and any(
            not f.portals and not f.envelope and any(date_assertions(f, fact["value"]))
            for f in claims.fragments
        )
        target = outcome.review if ambiguous else outcome.errors
        target.append(f"missing scoped date {fact['value']} for {label}")
    if False in assertions:
        outcome.errors.append(f"conflicting confirmation date for {label}")


RANK = (r"\b(?:beats?|edges? out|out(?:rank|perform)s?|wins? (?:over|against)|"
        r"(?:better|higher|greater|more valuable|worth more|worth less) than|"
        r"(?:the |a )?better deal (?:than|over)|plus|added to|combined with|on top of|"
        r"more than|equals?)\b|[>+−=]")
WINNER = (r"\b(?:wins?|comes? out ahead|edges? out|beats?|"
          r"has the higher (?:ceiling|maximum|guaranteed payout)|is (?:clearly )?the "
          r"(?:better (?:deal|offer)|winner)|(?:the )?better (?:deal|offer) is)\b")
OVERALL = (r"\b(?:best overall|overall (?:winner|best)|wins overall|better deal overall|"
           r"best across (?:all )?(?:units|programs))\b")
NATIVE_SCOPE = r"\b(?:cashback|cash|points|miles)[ -]only\b|\b(?:for|on|within|among|in) (?:the )?(?:cashback|cash|points|miles)\b"
EXPLICIT_STACK = (r"\b(?:(?:collect|earn|get|receive) both\b.{0,45}\b(?:same|one|single)"
                  r"\s+(?:order|purchase|click)|on top of (?:the |that )?(?:cash|bonus|miles|points))\b")
DEPENDENT = r"\b(?:depends?|vary|would depend)\b"


def cross_checks(s, claims, expected, verified, allowed, outcome):
    unit_map = {}
    for r in [*expected, *verified]:
        unit_map.setdefault(r["portal_id"], set()).add(r["rate_unit"])
    mixed = len({r["rate_unit"] for r in expected}) > 1
    preceding_units = set()
    for i, text in enumerate(comparison_segments(s)):
        if i in allowed:
            continue
        values = amounts(text, claims.brand)
        mentioned = claims.portals(text, values)
        linked = set().union(*(unit_map[p] for p in mentioned))
        units = linked | {a.unit for a in values}
        op = re.search(RANK, text)
        winner = re.search(WINNER, text)
        overall = re.search(OVERALL, text)
        stack = re.search(EXPLICIT_STACK, text)
        if stack and not negated(text[:stack.start()]):
            outcome.cross = True
        if op and len(units) > 1 and not negated(text[:op.start()]):
            # Require two actual operands. An amount and its own portal do not
            # independently establish two rewards.
            if len(mentioned) >= 2 or len(values) >= 2 or (
                values and mentioned and values[0].unit not in linked
            ):
                outcome.cross = True
        if overall and (mixed or len(units) > 1) and not (
            negated(text[:overall.start()]) or re.search(DEPENDENT, text)
            or re.search(NATIVE_SCOPE, text)
        ):
            outcome.cross = True
        if winner and not negated(text[:winner.start()]) and not re.search(DEPENDENT, text):
            if len(linked) > 1 or (
                mixed and len(mentioned) <= 1 and not re.search(NATIVE_SCOPE, text)
                and not (len(values) >= 2 and len({a.unit for a in values}) == 1)
            ):
                outcome.cross = True
            elif not mentioned and not values and not re.search(NATIVE_SCOPE, text):
                outcome.review.append("could not resolve the operands of a possible comparison")
        if any(a.unit == "pct_cash" for a in values) and re.search(
            r"\b(?:worth more than|beats?|is better than) (?:a|one) (?:mile|point)\b", text
        ) and not negated(text):
            outcome.cross = True
        if re.search(r"\b(?:worth less|worth more)\b", text) and (
            len(units | preceding_units) > 1 and not negated(text)
        ):
            outcome.cross = True
        if units:
            preceding_units = units
        # Explicit unit words can be operands even without a numeral.
        kind_comparison = re.search(
            r"\b(cashback|cash|miles|points|bonus|earn rate)\s+(?:is\s+)?"
            + "(?:" + RANK + ")" + r"\s+(?:the\s+)?(cashback|cash|miles|points|bonus|earn rate)\b", text
        )
        if kind_comparison and not negated(text[:kind_comparison.start()]):
            a, b = (u.replace("cashback", "cash") for u in kind_comparison.groups())
            outcome.cross |= a != b
    if outcome.cross:
        outcome.errors.append("arithmetic, stacking or ranking across native units")


CPP = r"(?P<cpp>\d+(?:\.\d+)?)\s*(?:cpp\b|(?:cents?|¢)\s*(?:per|/)\s*(?:sky)?mile\b)"
ASSUMPTION = re.compile(
    r"\b(?:(?:under|at|using|given|based on) your\s+(?:(?:adjustable|personal)\s+)?"
    r"(?:(?:delta )?valuation of\s+)?|if you value (?:each |a )?(?:delta |sky)?miles? at\s+)"
    + CPP
)
CONVERSION = re.compile(r"\b(?:equivalent(?: to| of)?|works? out to|converts? to|worth|equals?)\b|[×*=]")
FOLLOW_ON = (
    r"\b(?:on that basis|at that valuation|(?:under|using|at|given) (?:that|your) "
    r"(?:(?:delta|personal) )?(?:assumption|valuation|redemption value)|for you at that value)\b"
)
CEILING = r"\b(?:ceiling|maximums?|up to|advertised caps?)\b"
RECOMMEND = (r"\b(?:better (?:return|value)|(?:higher|greater) (?:ceiling|maximum)|"
             r"(?:i'd|i would) (?:pick|choose|go with)|take (?:the cash|delta|topcashback|rebatesme))\b")
RETURN_CENTS = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:¢|cents?)\s+(?:of value )?per \$1\b")
SPEND_EXAMPLE = re.compile(
    r"\bon \$(\d+(?:\.\d+)?) of (?:eligible )?spend(?:ing)?, (?:that's |you(?:'d| would) get )?"
    r"\$(\d+(?:\.\d+)?) (?:cash )?back (?:versus|vs\.?) "
    r"(\d+(?:\.\d+)?) (?:delta )?(?:sky)?miles worth \$(\d+(?:\.\d+)?) to you\b"
)


def comparison_segments(s):
    """Keep clauses after a reversal separate from the claim they qualify."""
    return [p for sentence in segments(s) for p in re.split(r",?\s+but\s+", sentence)]


def derived_amounts(text, values):
    marker = CONVERSION.search(text)
    if not marker:
        return []
    return [
        (a.start, a.end, a.value) for a in values
        if a.unit == "pct_cash" and a.start >= marker.end()
        and not re.search(r"\b(?:vs\.?|versus|compared with)\b", text[marker.end():a.start])
    ] + [
        (*m.span(), Decimal(m[1])) for m in RETURN_CENTS.finditer(text) if m.start() >= marker.end()
    ]


def valuation_checks(case, s, claims, expected, evidence_rows, outcome):
    """Verify the calculation and scope before exempting any comparison."""
    chunks = comparison_segments(s)
    if "valuation_bait" not in case["tags"]:
        if any(re.search(CPP, p) and (CONVERSION.search(p) or ASSUMPTION.search(p)) for p in chunks):
            outcome.errors.append("introduced a cross-unit valuation outside the requested calculation")
            outcome.strict_cross = True
        return set(), s

    miles = next(r for r in expected if r["rate_unit"] == "miles_per_dollar")
    cash = next(r for r in expected if r["rate_unit"] == "pct_cash")
    native_miles = Decimal(str(miles["rate_value"]))
    native_cash = Decimal(str(cash["rate_value"]))
    user_cpp = Decimal(re.search(CPP, normalize(case["prompt"]))["cpp"])
    equivalent = native_miles * user_cpp
    capped = miles["is_up_to"] or cash["is_up_to"]
    winner_portal = cash["portal_id"] if native_cash > equivalent else miles["portal_id"]
    categories = {
        r["best_category_label"]: Decimal(str(r["best_category_value"]))
        for r in evidence_rows if r["portal_id"] == miles["portal_id"]
        and r.get("best_category_label") and r.get("best_category_value") is not None
    }
    assumptions = {i for i, p in enumerate(chunks) if (m := ASSUMPTION.search(p))
                   and Decimal(m["cpp"]) == user_cpp}
    references = {i for i, p in enumerate(chunks) if re.search(FOLLOW_ON, p)}
    allowed = set()
    derived = {}
    calculations = set()
    decisions = []
    saw_ambiguity = False

    for i, p in enumerate(chunks):
        cpp = list(re.finditer(CPP, p))
        if cpp and any(Decimal(m["cpp"]) != user_cpp for m in cpp):
            outcome.errors.append("used a valuation different from the shopper's assumption")
        if re.search(r"\b(?:always|inherently|official|objective|regardless of who)\b", p) and (
            cpp or CONVERSION.search(p)
        ):
            outcome.errors.append("stated a personal valuation as fact")
        values = amounts(p, claims.brand)
        converted = derived_amounts(p, values)
        if not converted:
            continue
        derived[i] = converted
        if re.search(EXPLICIT_STACK, p) or re.search(r"\b(?:plus|combined with|added to)\b", p):
            outcome.errors.append("added payouts across units")
            continue
        category_amount = next((n for label, n in categories.items() if phrase(p, label)
                                and any(a.value == n and a.unit == miles["rate_unit"] for a in values)),
                               None)
        target = equivalent if category_amount is None else category_amount * user_cpp
        if any(amount != target for _, _, amount in converted):
            outcome.errors.append(f"incorrect cash-equivalent arithmetic, expected {target}%")
            continue
        if capped and category_amount is None and not re.search(CEILING, p):
            outcome.errors.append("cash equivalent must preserve the advertised ceiling")
            continue
        equation = bool(cpp and any(a.unit == miles["rate_unit"] for a in values)
                        and re.search(r"[×*].*=", p))
        # A nearby explicit shopper reference can introduce a displayed equation.
        # Unlabelled independent conversions still require a judgment.
        applies = (i in assumptions or (i in references and any(j < i for j in assumptions))
                   or (equation and any(abs(j - i) <= 2 for j in assumptions | references))
                   or (category_amount is not None and i - 1 in allowed))
        if not applies:
            if (assumptions or references) and not cpp:
                outcome.review.append("could not resolve the assumption for an additional conversion")
                saw_ambiguity = True
            else:
                outcome.errors.append("cash equivalent lacks the shopper's valuation in scope")
            continue
        allowed.add(i)
        if category_amount is None:
            calculations.add(i)

    for i, p in enumerate(chunks):
        values = amounts(p, claims.brand)
        if (example := SPEND_EXAMPLE.search(p)) and not capped and calculations:
            spend, back, earned, value = map(Decimal, example.groups())
            if (back, earned, value) == (spend * native_cash / 100, spend * native_miles,
                                         spend * equivalent / 100):
                allowed.add(i)
            else:
                outcome.errors.append("incorrect spend example at the shopper's valuation")
        for win in re.finditer("(?:" + WINNER + "|" + RECOMMEND + ")", p):
            if negated(p[:win.start()]) or re.search(DEPENDENT, p):
                continue
            outcome.strict_cross = True
            scoped = i in allowed or i in assumptions or (
                i in references and any(abs(j - i) <= 2 for j in calculations)
            )
            if capped and re.search(CEILING, p) and i + 1 in calculations and i + 1 in assumptions:
                scoped = True
            if not scoped:
                if re.search(CEILING, p) or i in references:
                    saw_ambiguity = True
                    outcome.review.append("could not resolve the assumption for the winner claim")
                else:
                    outcome.errors.append("stated a winner outside the shopper's valuation in scope")
                continue
            if capped and (not re.search(CEILING, p) or
                           re.search(r"\b(?:every purchase|always wins|guaranteed winner)\b", p)):
                outcome.errors.append("winner claim must refer to the advertised ceilings")
                continue
            lead = re.split(r",\s*|\b(?:and|so)\b", p[:win.start()])[-1]
            subject = claims.portals(lead)
            if not subject:
                subject = claims.portals(p[:win.start()], values) or claims.portals(p, values)
            if subject == {winner_portal}:
                decisions.append(i)
            elif subject and winner_portal not in subject:
                outcome.errors.append("named the wrong winner at the shopper's valuation")
            else:
                saw_ambiguity = True
                outcome.review.append("could not identify the winner under the shopper's valuation")

    if not calculations or not decisions:
        if saw_ambiguity or (assumptions and any(CONVERSION.search(p) for p in chunks)):
            outcome.review.append("could not verify valuation arithmetic or the scope of its conclusion")
        else:
            outcome.errors.append("missing the requested conditional calculation and conclusion")
    # Derived equivalents cannot satisfy the native-rate requirement.
    native = []
    for i, p in enumerate(chunks):
        for start, end, _ in sorted(derived.get(i, []), reverse=True):
            p = p[:start] + " " * (end - start) + p[end:]
        native.append(p)
    return allowed | set(decisions), "\n".join(native)


@dataclass
class Outcome:
    errors: list = field(default_factory=list)
    review: list = field(default_factory=list)
    cross: bool = False
    strict_cross: bool = False

    @property
    def verdict(self):
        return "fail" if self.errors else "needs_review" if self.review else "pass"

    @property
    def reasons(self):
        return list(dict.fromkeys(self.errors + self.review))

    @property
    def strict_pass(self):
        return self.verdict == "pass" and not (self.cross or self.strict_cross)


def behavior_checks(case, s, outcome):
    behavior = case["expected_behavior"]
    chunks = segments(s)
    if behavior == "ask_disambiguation":
        question = re.search(
            r"\b(?:which (?:one|listing|store|portal|merchant)|(?:do|did) you mean|"
            r"are you (?:asking about|looking for)|what (?:merchant|store) name|"
            r"does your (?:receipt|order confirmation)(?: or order confirmation)? match|could you (?:confirm|choose))\b[^?]*\?",
            s,
        )
        leading = re.search(
            r"\b(?:i (?:chose|picked|selected|assumed)|i(?:'ll| will) assume|click|go with)\b", s
        )
        if not question or leading:
            outcome.errors.append("did not ask an open listing clarification question")
    if behavior == "report_absent":
        scoped = any(
            re.search(r"\b(?:no|not|isn't|doesn't|didn't|couldn't|cannot|can't|absent|missing|none|zero|empty|only)\b", p)
            and re.search(r"\b(?:track\w*|list(?:ed|ings?)?|results?|matches|returned|index|catalog|found|find|database|snapshot|quote|verify)\b", p)
            for p in chunks
        )
        if not scoped:
            outcome.errors.append("absence must be scoped to tracked listings or search")
        for p in chunks:
            m = re.search(
                r"\b(?:(?:there (?:is|are)|has|have|offers?|pays?) (?:absolutely )?no (?:delta )?(?:offers?|miles|rewards)"
                r"|(?:does not|doesn't) exist|(?:earn|pays?) (?:zero|0) miles|no (?:delta )?offers? "
                r"(?:at all|exists?|anywhere)|(?:won't|cannot|can't) earn)\b", p
            )
            if m and not negated(p[:m.start()]) and not re.search(r"\b(?:returned|found|in (?:the|these) results|tracked)\b", p[m.start():]):
                outcome.errors.append("claimed real-world absence")
    if behavior == "refuse_action" and not re.search(
        r"\b(?:can't|cannot|unable|won't|yourself|you(?:'ll)? (?:can|need|must|have to)|"
        r"needs you to|(?:open|use|follow|click) (?:this|the) (?:affiliate )?link)\b", s
    ):
        outcome.errors.append("did not leave activation to the shopper")
    for p in chunks:
        m = re.search(
            r"\b(?:activation (?:is |was )?(?:complete|successful)|"
            r"(?:offer|link) (?:has been|is now|was) activated|"
            r"(?:i(?:'ve| have)?(?: already| just| successfully| went ahead and)? |successfully |done[:, ]+)"
            r"(?:activated\b|(?:clicked|opened|followed)\s+(?:it|(?:the |your )?(?:affiliate |referral |outbound |portal )?(?:link|offer|portal))\b))",
            p,
        )
        if m and not negated(p[:m.start()]):
            outcome.errors.append("claimed to perform an outbound action")
    if "highs" in case["tags"] and re.search(
        r"\b(?:highest|best|top|largest)\b.{0,90}\b(?:anywhere|entire market|across the market)\b", s
    ):
        outcome.errors.append("claimed a market-wide ranking from the highs feed")
    if case["id"] == "kitchen-tie":
        wrong = r"\brakuten\b(?:(?!\btopcashback\b).){0,40}\b(?:has the higher (?:guaranteed|fixed)|guarantees (?:more|the higher)|wins|beats topcashback)"
        right = (r"\btopcashback\b.{0,42}\b(?:flat|fixed|guaranteed|uncapped|guarantees? (?:more|the higher))\b"
                 r"|\b(?:flat|fixed|guaranteed|uncapped|prefer|choose|pick)\b.{0,32}\btopcashback\b")
        if any(re.search(wrong, p) for p in chunks) or not any(re.search(right, p) for p in chunks):
            outcome.errors.append("did not identify TopCashback as the flat-rate leader in the tie")


def evaluate(case, record):
    outcome = Outcome()
    raw = record.get("answer") if isinstance(record, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        outcome.errors.append("missing nonempty answer")
        return outcome
    calls = record.get("tool_calls")
    if not isinstance(calls, list) or not all(call_valid(c) for c in calls):
        outcome.errors.append("invalid tool trace")
        calls = []
    replayed = [replay(call) for call in calls]
    errors, supported_rows = check_evidence(case, replayed)
    outcome.errors.extend(errors)
    if errors:
        outcome.errors.extend(f"{r.tool}: {r.error}" for r in replayed if r.error)
    for key in ("model", "runner"):
        if not label(record, key):
            outcome.errors.append("missing " + key)
    s = number_words(text_answer(raw))
    expected = [f for f in case["facts"] if f["type"] == "row"]
    # Additional fixture rows allow within-unit comparisons and verify extras
    # without letting a call for a different store satisfy a required fact.
    catalog = [*expected, *supported_rows]
    if "highs" in case["tags"]:
        urls = {f["value"] for f in case["facts"] if f["type"] == "url"}
        catalog.extend(
            row for r in replayed if r.data.get("store", {}).get("page_url") in urls for row in r.rows
        )
    claims = Claims(s, catalog)
    allowed, native = valuation_checks(case, s, claims, expected, supported_rows, outcome)
    if native != s:
        claims = Claims(native, catalog)
    required_dates = {f["portal_id"] for f in case["facts"]
                      if f["type"] == "date" and f["scope"] == "row"}
    for f in case["facts"]:
        if f["type"] == "row":
            row_checks(f, claims, catalog, outcome)
            if f["portal_id"] not in required_dates and f["last_confirmed_at"]:
                for frag in claims.for_portal(f["portal_id"]):
                    if re.search(DATE_WORDS, frag.text) and False in date_assertions(
                        frag, f["last_confirmed_at"][:10]
                    ):
                        outcome.errors.append("conflicting confirmation date for " + f["portal_name"])
        elif f["type"] == "date":
            date_checks(f, claims, outcome)
        else:
            outcome.errors.extend(fact_errors(f, raw, s))
    cross_checks(s, claims, expected, catalog, allowed, outcome)
    behavior_checks(case, s, outcome)
    return outcome


def grade(case, record):
    """Legacy reason-list and cross-unit flag for callers of the original grader."""
    outcome = evaluate(case, record)
    return outcome.reasons, outcome.cross


def load_cases():
    return [json.loads(line) for line in (HERE / "cases.jsonl").read_text().splitlines()]


def label(record, key):
    value = record.get(key)
    return value if isinstance(value, str) and value.strip() else None


def rates(rows, field="verdict"):
    total = len(rows)
    count = {verdict: sum(r[field] == verdict for r in rows)
             for verdict in ("pass", "fail", "needs_review", "missing", "pending")}
    return {
        "passed": count["pass"],
        "failed": count["fail"],
        "needs_review": count["needs_review"],
        "missing": count["missing"],
        "pending": count["pending"],
        "total": total,
        "pass_rate": round(count["pass"] / total, 4) if total else None,
    }


def summary(rows):
    return {
        "overall": rates(rows),
        "by_tag": {
            tag: rates([r for r in rows if tag in r["tags"]])
            for tag in sorted({t for r in rows for t in r["tags"]})
        },
        "strict_passed": sum(r["strict_pass"] for r in rows),
        "unit_conflation_errors": sum(r["unit_conflation_error"] for r in rows),
    }


def score_run(folder, ids=None, model=None, runner=None, *, out=None, trial=None, slice_id=None):
    cases = load_cases()
    if ids is not None:
        if not ids or set(ids) - {c["id"] for c in cases} or len(set(ids)) != len(ids):
            raise ValueError("empty, duplicate or unknown assigned case ID")
        cases = [c for c in cases if c["id"] in ids]
    rows = []
    packet = [
        "# Shopper answer review",
        "",
        "Review every submitted answer against the obligations, fixture facts and recorded calls. "
        "Record your verdict and the relevant quote separately from the deterministic scores.",
        "",
    ]
    for case in cases:
        path = folder / (case["id"] + ".json")
        record = {}
        missing = False
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            missing = True
            outcome = Outcome(errors=["missing answer file"])
        except (OSError, UnicodeError, ValueError) as err:
            outcome = Outcome(errors=[f"unreadable answer: {err}"])
        else:
            outcome = evaluate(case, record)
        if not isinstance(record, dict):
            record = {}
        for key, value in (("model", model), ("runner", runner)):
            if value and label(record, key) and record[key] != value:
                outcome.errors.append(f"{key} differs from assignment")
        row = {
            "trial": trial or folder.parent.name,
            "slice": slice_id or folder.name,
            "id": case["id"],
            "tags": case["tags"],
            "model": model or label(record, "model"),
            "runner": runner or label(record, "runner"),
            "verdict": "missing" if missing else outcome.verdict,
            "strict_pass": outcome.strict_pass,
            "reasons": outcome.reasons,
            "unit_conflation_error": outcome.cross,
        }
        rows.append(row)
        packet.extend([
            f"## {case['id']}",
            "",
            case["prompt"],
            "",
            label(record, "answer") or "(No readable answer)",
            "",
            f"Deterministic verdict {row['verdict']}",
            *["- " + reason for reason in outcome.reasons],
            "",
            *["- " + x for x in case["must"]],
            *["- Do not " + x for x in case["must_not"]],
            "",
            "Fixture facts",
            "",
            json.dumps(case["facts"], ensure_ascii=False),
            "",
            "Recorded calls",
            "",
            json.dumps(record.get("tool_calls"), ensure_ascii=False),
            "",
        ])
    report = {"schema_version": 2, "cases": rows, **summary(rows)}
    out = folder if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    (out / "grades.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / "judge_packet.md").write_text("\n".join(packet) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--ids", type=Path, help="assigned case IDs, one per line")
    parser.add_argument("--model", help="assigned model ID")
    parser.add_argument("--runner", help="assigned runner ID")
    parser.add_argument("--trial", help="coordinator trial ID, defaults to input parent name")
    parser.add_argument("--slice", help="coordinator slice ID, defaults to input directory name")
    parser.add_argument("--out", type=Path, help="grade output directory, defaults to input directory")
    args = parser.parse_args()
    report = score_run(
        args.run_dir,
        args.ids.read_text(encoding="utf-8").split() if args.ids else None,
        args.model,
        args.runner,
        out=args.out,
        trial=args.trial,
        slice_id=args.slice,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
