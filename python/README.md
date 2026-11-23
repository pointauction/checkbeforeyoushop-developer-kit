# CheckBeforeYouShop Python SDK

Use the public JSON API from Python 3.10 or later. The installed SDK and CLI use
the Python standard library.

## Install

```sh
pip install "git+https://github.com/pointauction/checkbeforeyoushop-developer-kit#subdirectory=python"
```

## Quick start

```python
from cbys import Client, filter_program, format_rate, freshness

client = Client()
match = client.resolve_store("Nike")
response = client.get_store(match.slug)

for row in filter_program(response.data.rates, "delta"):
    print(format_rate(row), row.program, freshness(row).last_confirmed_at)

print(response.attribution, response.data.merchant.page_url)
print(response.disclosure)
```

`resolve_store` checks for an exact slug, then a case-insensitive exact name,
then an exact domain. `Ambiguous.candidates` lists the stores to choose from.
`NotFound.suggestions` can contain possible matches. Use `get_store` directly
when you already know the slug.

`search`, `get_store`, `list_portals`, `get_portal`, and `get_highs` return
frozen dataclasses inside an `Envelope`. Read additional API fields from each
model's `extra` dict and the original JSON object from `Envelope.raw`. Timestamps
remain ISO strings as supplied by the API. The client retries network failures,
HTTP 429 and HTTP 5xx responses and honors `Retry-After` when present.
If the final response is a 429, `HTTPError.retry_after_seconds` contains the
remaining delay in seconds or `None` if the header is missing or invalid.

## CLI

```sh
cbys search "home depot"
cbys store Nike --program delta
cbys store nike --unit pct_cash --hide-stale
cbys store square --include-stale
cbys portals
cbys portal delta-skymiles
cbys highs --kind earn_rate --unit miles_per_dollar --limit 10
python -m cbys store Nike --json
```

`--json` emits the full API envelope. Filters and limits apply to the human
display. Run `cbys store --help` or `cbys highs --help` for the supported units.
Without `--unit`, `highs --limit N` takes turns drawing from the independently
ranked unit and kind groups, up to N rows total. N must be nonnegative.
Store output shows the store-wide verdict and its caveats when available.
It includes and marks stale rows by default. Gift card payouts are labeled
even when the API calls the program `cash`.

Exit codes

- 0 for success
- 1 for other SDK errors
- 2 for network errors or invalid CLI arguments
- 3 for ambiguous stores
- 4 when no exact store or portal can be resolved
- 5 when search matched a store but its detail endpoint returned no listings (HTTP 404)

From a checkout, use the captured responses with `--fixtures` or
`CBYS_FIXTURES_DIR`. Missing request keys raise `FixtureMissing`.
Fixture values reflect the capture date.

```sh
cbys --fixtures fixtures/live-2026-11-22 store macys-com
CBYS_FIXTURES_DIR=fixtures/live-2026-11-22 python3 example.py Nike --program delta
python -m unittest discover -s python/tests
```

## Units and freshness

`group_by_unit` groups rows by `rate_unit`. Use `best_per_unit` for one leader
per unit within the same kind. For example, 2% cashback and 1 Delta SkyMile
per dollar belong to separate groups. A flat signup bonus belongs in its own
group. `compare_rates` raises `MixedUnitError` if the units or kinds differ.

Within a group, fresher rows come before stale rows, higher values come first
at the same freshness status, and a fixed rate comes before an equally
valued “up to” rate. If a group's only rows are stale, its leader is
stale too. `format_rate` includes the unit and marks “up to”, one-time bonus,
and stale rows. When the API supplies a confirmed category rate for an “up to”
store row, `format_rate` shows the category alongside the advertised ceiling.
Check `freshness(row)` for the row's own `last_confirmed_at` and `is_stale`.
An omitted row field is unknown. The envelope's `data_as_of` is the newest
confirmation supplied for the response. If your program is missing from the
full rate table, the API returned no tracked listing for it.

The upstream `StoreData.summary` can name a leader in a different unit than the
rates you display. Avoid showing it verbatim. Use the structured verdict and
grouped rates as the CLI does. `StoreData.summary_is_single_unit` tells you
whether the unfiltered response has rates in exactly one native unit and kind.
Check your display filters separately.

## Attribution

When you display the data, credit CheckBeforeYouShop and link each item's
`page_url`. Store rates use the merchant's `page_url`. Include the envelope's
`disclosure` when you re-serve rates. The SDK preserves outbound `go_url` links
as data. The API data and the SDK code have separate terms. [Data terms](https://checkbeforeyoushop.com/developers)
