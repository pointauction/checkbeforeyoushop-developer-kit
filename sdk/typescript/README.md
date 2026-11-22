# CheckBeforeYouShop TypeScript SDK

Read the public CheckBeforeYouShop API with native `fetch`. The SDK has zero
runtime dependencies. The core works in Node 18+, browsers, Deno, and Workers.
The fixture reader uses Node's filesystem.

## Install from Git

Clone a revision of the developer kit that contains `sdk/typescript`, then
build the package inside the checkout.

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

Use an ESM project. In TypeScript, use a module resolution mode that supports
package exports, such as `NodeNext` or `Bundler`.

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
exact slug first, followed by an exact name and an exact domain, ignoring
case. When search omits a possible exact slug, it checks the merchant endpoint.
A `found` result includes `store` and `matchedBy`. An `ambiguous` result
includes `candidates`, even when there's only one fuzzy candidate.
A `not_found` result includes any spelling `suggestions`. Each result has a
separate `portalHits` array.

Configure the client with `baseUrl`, `fetch`, `timeoutMs`, `userAgent`, or
`retries`. The default timeout is 10 seconds per attempt, including the body.
Network failures, HTTP 429, and HTTP 5xx can trigger up to two retries by
default. Retries use backoff with jitter and honor `Retry-After` when the
header is available. Set `retries: 0` for a single attempt. Browsers can
manage the User-Agent header.

Use `CbysBadRequestError` for invalid input and HTTP 400, `CbysNotFoundError`
for HTTP 404, and `CbysHttpError` for other HTTP responses and malformed
response envelopes. `CbysNetworkError` and `CbysTimeoutError` distinguish
transport failures from deadline expiry.

## How rates are compared

- Cashback percentages, miles per dollar, points per dollar, and flat payouts
  measure different things. `groupRatesByUnit(rates)` returns a map keyed by
  `rate_unit` in the order the units first appear. `compareRates` throws
  `CbysMixedUnitError` if the units differ. Earn rates and one-time bonuses
  also must match in kind before comparison.
- Within each unit, higher values come first. At the same value, a fixed rate
  comes before an advertised “up to” rate. Stale rows retain their flag and sort
  after other rows.
- `bestPerUnit(rates)` returns the first row per unit after applying these rules
  and skips units with only stale rows. It ranks the values reported in the
  supplied rows. The API's `best_rates` can account for supported category
  ceilings and other site rules.
- `formatRate(row)` includes the native unit and labels “up to”, one-time bonus,
  and stale rows when those fields apply. Check `payout_kind` to distinguish
  gift card payouts when displaying a rate.
- `freshness(row, now?)` reports the row's stale flag, confirmation timestamp,
  and age in hours when available. The flag comes from the API. `data_as_of`
  describes the response as a whole. A missing per-row flag or timestamp
  yields `null` in the helper. The highs feed omits per-row freshness and
  “up to” flags.
- `filterByProgram(rates, 'delta')` searches program, portal ID, and portal
  name, ignoring case. Use the full `rates` list for a program check. An empty
  result means the response contained no tracked listing for that program.

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
