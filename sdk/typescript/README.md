# CheckBeforeYouShop TypeScript SDK

Read the public CheckBeforeYouShop API with native `fetch`. The SDK has zero
runtime dependencies. The core works in Node 18+, browsers, Deno, and Workers.
The fixture reader uses Node's filesystem.

## Install from Git

Clone the developer kit's `main` branch, then build the SDK from its folder.

```sh
git clone https://github.com/pointauction/checkbeforeyoushop-developer-kit.git
cd checkbeforeyoushop-developer-kit/sdk/typescript
npm ci
npm run build
```

From your application, install a copy of the built package using its local path.

```sh
npm install --install-links /absolute/path/to/checkbeforeyoushop-developer-kit/sdk/typescript
```

Use `npm ci --install-links` when reinstalling the application from its lockfile.

## Quick start

Use an ESM project. If you use TypeScript, use version 5.4 or later and a module
resolution mode that supports package exports, such as `NodeNext` or `Bundler`.

```ts
import {
  CbysClient,
  attributionFor,
  filterByProgram,
  formatRate,
  freshness,
} from '@checkbeforeyoushop/sdk';

const client = new CbysClient();
const result = await client.getStore('nike');
const { merchant, rates } = result.data;
const credit = attributionFor(result, merchant);

for (const row of filterByProgram(rates, 'delta')) {
  const { lastConfirmedAt } = freshness(row);
  console.log(row.program, formatRate(row), lastConfirmedAt);
}

console.log(credit.attribution, credit.page_url, credit.disclosure);
```

`search(q)`, `getStore(slug)`, `listPortals()`, `getPortal(id)`, and
`getHighs()` return the API's `data`, `data_as_of`, `source`,
`attribution`, and `disclosure`. Additional response fields pass through.
The SDK checks the envelope and types the endpoint data from the API contract.
Rows preserve their original `rate_display` and any supplied `go_url` for
callers to display. The client only requests the JSON endpoints.

Use `resolveStore(query)` when you have a name or domain. It checks for an
exact slug first, followed by an exact name and an exact domain. It ignores
case and normalizes both sides to Unicode NFC. When search omits a possible
exact slug, it checks the merchant endpoint.
A `found` result includes `store` and `matchedBy`. An `ambiguous` result
includes `candidates`, even when there's only one fuzzy candidate.
A `not_found` result includes any spelling `suggestions`. Each result has a
separate `portalHits` array.

Configure the client with `baseUrl`, `fetch`, `timeoutMs`, `userAgent`, or
`retries`. The default timeout is 10 seconds per attempt, including the body.
Network failures, HTTP 429, and HTTP 5xx can trigger up to two retries by
default. Retries use backoff with jitter and honor `Retry-After` when the
header is available. Set `retries: 0` for a single attempt. If HTTP 429 is
the final response, `CbysHttpError.retryAfterSeconds` carries the delay when
the server supplies a valid header. Browsers can manage the User-Agent header.

Use `CbysBadRequestError` for invalid input and HTTP 400, `CbysNotFoundError`
for HTTP 404, and `CbysHttpError` for other HTTP responses and malformed
response envelopes. `CbysNetworkError` and `CbysTimeoutError` distinguish
transport failures from deadline expiry.

## How rates are compared

The store's `summary` and `verdict` are upstream prose. Either can single out
one program across units. For comparisons, use the per-unit rows in
`best_rates` or group the full `rates` list. If you display the verdict,
preserve all `verdict.caveats`.

- Cashback percentages, miles per dollar, points per dollar, and flat payouts
  measure different things. `groupRatesByUnit(rates)` returns a map keyed by
  `rate_unit` in the order the units first appear. `compareRates` requires
  matching units and kinds. TypeScript catches mismatched literals. At runtime
  the comparator throws `CbysMixedUnitError` or `CbysMixedKindError` for
  mismatched rows.
- Stale rows sort last. Within a unit and kind, rows sort by confirmed category
  value when supplied, or by the reported value otherwise. At equal values,
  fixed rates come first, then higher advertised ceilings break remaining ties.
  An “up to” value is an advertised maximum.
- `bestPerUnit(rates)` takes the first row in each group and skips units with
  only stale rows. The API's `best_rates` also reflects site ranking rules.
- `formatRate(row)` includes the native unit and labels “up to”, one-time
  bonus, gift card payout, and stale rows when those fields apply. When an
  “up to” row has a confirmed category, the formatter shows both values
  (for example, `up to 3.5 mi/$ · All Other Categories: 2.5 mi/$`).
- `freshness(row, now?)` reports the row's stale flag, confirmation timestamp,
  and age in hours when available. The flag comes from the API. `data_as_of`
  describes the response as a whole. A missing per-row flag or timestamp
  yields `null` in the helper. The highs feed omits per-row freshness and
  “up to” flags.
- `filterByProgram(rates, 'delta')` checks exact program, portal ID, and
  portal name in that order, ignoring case and normalizing to Unicode NFC.
  It then tries known aliases (such as `aa` or `united`) and whole words.
  Generic currency queries such as `miles`, `points`, and `cash` throw
  `CbysAmbiguousProgramError`. For those, filter the rows by `rate_unit`.
  Use the full `rates` list for a program check. An empty result means the
  response contained no tracked listing for that program.

## Offline mode and examples

Use the Node entry point with a directory that contains `manifest.json`.
`createFixtureFetch()` reads `CBYS_FIXTURES_DIR` by default. Pass a directory
to use a different snapshot.
The reader serves captured responses, including captured HTTP errors. An
uncaptured request raises `CbysFixtureMissingError` and stays offline.

```ts
import { CbysClient } from '@checkbeforeyoushop/sdk';
import { createFixtureFetch } from '@checkbeforeyoushop/sdk/node';

const client = new CbysClient({ fetch: createFixtureFetch() });
const snapshot = await client.getStore('nike');
```

After building, run the examples from `sdk/typescript`. They default to the
repository's November 22, 2026 snapshot and accept a `--live` flag. The
snapshot shows what the API captured that day.

```sh
node examples/store-lookup.mjs nike
node examples/delta-check.mjs nike
node examples/highs-by-unit.mjs
```

## Attribution

Credit CheckBeforeYouShop and link each item to its `page_url` wherever you
use the data. Include the disclosure when re-serving rates.
`attributionFor(envelope, item)` returns the source, attribution text, page
link, and disclosure for a store, portal, or linked rate item.
