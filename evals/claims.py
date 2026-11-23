"""Recognize explicit, local payout claims in prose and Markdown tables."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

NUMBER = r"(?<![\w.$])\d+(?:\.\d+)?(?!\d|\.\d)"
PER = r"\s*(?:/\s*(?:\$1\b|\$(?!\d)|dollar\b)|(?:per|for each|for every|for|a)\s+(?:dollars?\b|\$1\b))"
CAP = r"(?:up[ -]to|as (?:much|high) as|maximum(?: of)?|at most|capped at|ceiling(?: of)?)"
BONUS = r"\bone[ -](?:time|off)\b.{0,24}?\b(?:bonus|bounty|payout)\b|\bbonus\b.{0,12}?\bone[ -]time\b"
STALE = r"\b(?:stale|outdated|out[- ]of[- ]date|aged|needs? reconfirm\w*|not (?:current|fresh)|last showed|verify before relying|check again before|reconfirm (?:it|the rate)|old(?:er)? (?:rate|listing))\b"
CURRENT = r"\b(?:currently pays|current rate is|not stale|still current|fresh today|is current|is fresh)\b"
NEG_RATE = r"\b(?:did not|didn't|does not|doesn't|do not|don't|never|won't|cannot|can't|not)\s+(?:\w+\s+){0,3}$"
ENVELOPE = r"\b(?:overall (?:snapshot|date)|snapshot (?:was updated|is dated|date|as of|dated)|data_as_of|envelope)\b"
DATE_WORDS = r"\b(?:last (?:confirmed|checked|seen)|was confirmed|confirmation|confirmed|\d+ days? (?:ago|earlier|older))\b"
CONTINUATION = r"^(?:and |but )?(?:last (?:confirmed|checked|seen)|confirmed\b|(?:that|this|the) (?:specific )?(?:listing|rate|offer|bonus|payout)\b|that (?:was|is|'s)\b|every purchase\b|you earn\b|it (?:lists?|pays?|shows?)\b|its\b|checkbeforeyoushop\b)"
DAYS_OLD = r"\b(\d+) days? (?:ago|earlier|older)\b"


def normalize(s):
    s = unicodedata.normalize("NFKC", s).casefold().replace("’", "'").replace("‑", "-")
    return re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)


def phrase_pattern(s):
    return r"(?<!\w)" + re.escape(normalize(s)) + r"(?!\w)"


def phrase(s, name):
    return bool(name and re.search(phrase_pattern(name), s))


def text_answer(raw):
    # Keep link labels in the answer, but URLs never supply facts or candidates.
    raw = re.sub(
        r"\.[ \t]+(?=\[[^\]\n]*(?:offer|portal) \(affiliate link\)\]\(https?://)", " ", raw
    )
    s = re.sub(r"\[([^\]\n]+)\]\(https?://[^\s)]+\)", r"\1", raw)
    s = re.sub(r"https?://[^\s<>\])]+", " ", s)
    return normalize(s).replace("**", "").replace("__", "").replace("`", "")


def segments(s):
    s = re.sub(r"\b(?:mr|mrs|st|nov|oct|dec|jan|feb|mar|apr|jun|jul|aug|sep)\.(?=\s)",
               lambda m: m.group()[:-1] + "\x01", s)
    return [
        p.strip().replace("\x01", ".")
        for p in re.split(r"[;\n!?]|\.(?=\s|$)", s)
        if p.strip()
    ]


def number_words(s):
    words = ("zero one two three four five six seven eight nine ten eleven twelve").split()
    return re.sub(r"\b(?:" + "|".join(words) + r")\b(?=\s+(?:days?|hours?|hrs?)\b)",
                  lambda m: str(words.index(m[0])), s)


def has_date(s, value):
    d = date.fromisoformat(value)
    formats = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y")
    s = re.sub(r"\b([a-z]{3})\.(?=\s+\d)", r"\1", s)
    return any(phrase(s, d.strftime(fmt).replace(",", "")) or phrase(s, d.strftime(fmt))
               or (fmt == "%Y-%m-%d" and d.isoformat() + "t" in s) for fmt in formats)


def aliases(row):
    result = [row["portal_name"], row["portal_id"], row["portal_name"].split(" (")[0]]
    if row["program"] != "cash":
        result.append(row["program"])
    result.extend({
        "delta-skymiles": ["Delta", "Delta SkyMiles", "SkyMiles", "SkyMiles Shopping"],
        "aa-eshopping": ["American AAdvantage", "AAdvantage", "AA eShopping", "AA"],
        "radisson-rewardsshop": ["Radisson Rewards"],
        "jetblue-trueblue": ["JetBlue"],
        "southwest-rapidrewards": ["Southwest", "Rapid Rewards"],
        "alaska-atmos": ["Alaska Atmos", "Atmos"],
    }.get(row["portal_id"], []))
    return result


def brand_pattern(rows):
    brands = {"delta(?: skymiles)?", "aa", "aa(?:dvantage)?", "american aadvantage",
              "asia", "rapid rewards", "radisson rewards", "atmos"}
    brands.update(re.escape(normalize(row["program"])) for row in rows
                  if row["program"] != "cash")
    brands.update(re.escape(normalize(row["program"].rsplit(" ", 1)[0]))
                  for row in rows if row["program"].lower().endswith((" points", " miles")))
    return "(?:(?:" + "|".join(sorted(brands, key=lambda p: (-len(p), p))) + r")\s+)?"


@dataclass
class Amount:
    start: int
    end: int
    unit: str
    value: Decimal
    capped: bool
    negative: bool


def amounts(s, brand):
    mile = rf"\s*{brand}(?:mi|miles?|skymiles?)\b"
    point = rf"\s*{brand}(?:pts?|points?)\b"
    patterns = {
        "pct_cash": NUMBER + r"\s*(?:%|per\s?cent\b)",
        "miles_per_dollar": NUMBER + mile + PER,
        "points_per_dollar": NUMBER + point + PER,
        "flat_miles": NUMBER + mile + "(?!" + PER + r"|\s+valu(?:e|ation))",
        "flat_points": NUMBER + point + "(?!" + PER + r"|\s+valu(?:e|ation))",
        "flat_cash": rf"(?:\$\s*\d+(?:\.\d+)?(?!\d|\.\d)|{NUMBER}\s*(?:dollars?|usd)\b)(?!{PER}|\s*(?:%|of (?:eligible )?spend))",
    }
    found = []
    for unit, pattern in patterns.items():
        for match in re.finditer(pattern, s):
            if any(m.start < match.end() and match.start() < m.end for m in found):
                continue
            value = Decimal(re.search(r"\d+(?:\.\d+)?", match[0])[0])
            before = s[:match.start()]
            if unit == "flat_cash" and re.search(r"\bper\s*$", before):
                continue
            after = s[match.end():]
            capped = bool(
                re.search(CAP + r"\s*[:(]?\s*$", before)
                or re.match(r"\s*(?:cash\s*back\s*)?(?:[,|(]\s*)?(?:is (?:the )?)?" + CAP + r"\b", after)
            )
            found.append(Amount(match.start(), match.end(), unit, value, capped,
                                bool(re.search(NEG_RATE, before))))
    return sorted(found, key=lambda m: m.start)


def table_rows(s):
    """Expand unit and qualifier columns inside each row, including blank cells."""
    headers = None
    previous_cells = None
    for line in s.splitlines():
        if "|" not in line:
            headers = previous_cells = None
            yield line
            continue
        cells = [c.strip() for c in line.strip().removeprefix("|").removesuffix("|").split("|")]
        if len(cells) > 1 and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            headers, previous_cells = previous_cells, None
            continue
        if previous_cells is not None:
            yield " | ".join(previous_cells)
        if headers is None:
            previous_cells = cells
            continue
        if len(cells) != len(headers):
            yield line
            continue
        row = []
        envelope_fields = []
        for header, cell in zip(headers, cells):
            if not cell:
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?", cell):
                if re.search(r"cash\s*back|percent|%", header):
                    cell += "%"
                elif re.search(r"miles? (?:per|/) (?:dollar|\$)|mi/\$", header):
                    cell += " mi/$"
                elif re.search(r"points? (?:per|/) (?:dollar|\$)|pts/\$", header):
                    cell += " pts/$"
                if phrase(header, "up to"):
                    cell = "up to " + cell
            if re.search(ENVELOPE, header):
                envelope_fields.append("overall snapshot " + cell)
                continue
            if re.search(r"\bstale\b", header) and cell in {"yes", "no", "true", "false"}:
                cell = "stale" if cell in {"yes", "true"} else "not stale"
            row.append(cell)
        yield " | ".join(row)
        yield from envelope_fields
    if previous_cells is not None:
        yield " | ".join(previous_cells)


@dataclass
class Fragment:
    text: str
    portals: set
    amounts: list
    envelope: bool


def portal_mentions(s, portal_patterns, values):
    found = []
    for pattern, portal in portal_patterns:
        for m in re.finditer(pattern, s):
            if (any(a < m.end() and m.start() < b for a, b, _ in found)
                or any(a.start <= m.start() and m.end() <= a.end for a in values)):
                continue
            found.append((*m.span(), portal))
    return sorted(found)


class Claims:
    def __init__(self, s, rows):
        self.brand = brand_pattern(rows)
        lookup = {}
        for row in rows:
            for name in aliases(row):
                lookup.setdefault(name, set()).add(row["portal_id"])
        self.patterns = [(phrase_pattern(name), next(iter(lookup[name])))
                         for name in sorted(lookup, key=lambda n: (-len(n), n))
                         if len(lookup[name]) == 1]
        self.fragments = []
        previous = set()
        for part in segments("\n".join(table_rows(number_words(s)))):
            for text in self.split(part):
                values = amounts(text, self.brand)
                explicit = self.portals(text, values)
                envelope = bool(re.search(ENVELOPE, text) and not explicit and not values)
                portals = explicit
                if not portals and not envelope and (
                    re.search(CONTINUATION, text.lstrip("- *"))
                    or re.match(r"^(?:it|this|that) (?:is|was) a one-time\b", text)
                    or (values and re.match(r"^[-*•]\s+", text) and len(previous) == 1)
                    or (re.search(DAYS_OLD, text) and len(previous) == 1)
                    or (re.search(r"\bboth (?:on|were)\b", text) and re.search(DATE_WORDS, text))
                ):
                    portals = previous
                self.fragments.append(Fragment(text, portals, values, envelope))
                if explicit and (values or len(explicit) == 1):
                    previous = explicit
                if envelope:
                    previous = set()

    def portals(self, text, values=()):
        return {p for _, _, p in portal_mentions(text, self.patterns, values)}

    def split(self, text):
        # Split independent clauses only when each has a payout and a different portal.
        # Leave explicit comparisons and grouped references together for review.
        remaining = text
        for m in list(re.finditer(r",?\s+(?:and|while|whereas|but|so)\s+|\s+(?:beats?|edges? out|tied with)\s+|,\s+(?=[a-z])", text)):
            left = text[len(text) - len(remaining):m.start()]
            right = text[m.end():]
            a, b = amounts(left, self.brand), amounts(right, self.brand)
            left_portals, right_portals = self.portals(left, a), self.portals(right, b)
            if right_portals and not left_portals and (
                (a and re.match(r"^it lists?\b", left))
                or (not a and re.search(ENVELOPE, left))
            ):
                yield left.strip()
                remaining = right
                continue
            if a and left_portals and right_portals - left_portals and (
                b or re.search(r"\b(?:so|tied with)\b", m[0]) or right.startswith("tied with ")
            ):
                yield left.strip()
                remaining = right
        yield remaining.strip()

    def for_portal(self, portal):
        return [f for f in self.fragments if f.portals == {portal}]
