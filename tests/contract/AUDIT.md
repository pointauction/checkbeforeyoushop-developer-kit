# Public API contract audit

App references below are relative to the private application repository at
`04e7551dba2e8cf3e8f4169482e5a957e26fc890`. The previous kit spec is at
`de81be82dd9a5ce97109dcb44ab54dcf1d933b1a`. Body evidence comes from all 24
requests in the November 22, 2026 fixture manifest and one eight-GET live
check. The fixtures cover 21 successes, one 400, and two 404s.

## Differences resolved in the spec

| Surface | Previous spec and corrected contract | App reference and fixture evidence |
| --- | --- | --- |
| Search input | The old `minLength` and `maxLength` measured JSON Schema characters on the original input. The handler rejects fewer than two UTF-16 code units after trimming and bounds processed text to 256 units. Address-shaped input can produce a canonical HTTPS URL or an empty 200. The request parameter describes the server rule in prose. | `site/src/pages/api/v1/search.json.ts:10`, `site/src/lib/search-results.ts:64`, `site/src/lib/search-results.ts:83`, `site/src/lib/search-address.ts:54`. The short query fixture is a 400. |
| Search output | The old spec omitted `did_you_mean` at both levels, the 25-row cap, the portal-only null domain rule, and the always-null timestamp. A row flag identifies a spelling suggestion. The aggregate flag is true whenever any returned row is a suggestion. Confirm a candidate's kind, exact identity, and market before choosing it. | `site/src/pages/api/v1/search.json.ts:19`, `site/src/lib/search-results.ts:440`, `site/src/lib/search-results.ts:458`, `site/src/lib/data/index.ts:394`. The `american` fixture has 25 rows. The `delta` fixture returns both kinds. The no-match fixture returns an empty 200. The captured flags are all false. |
| Merchant metadata and verdict | `summary` can be null when there is no eligible lead. The merchant success timestamp and `tracked_since` are strings. A successful response has at least one comparison row and one distinct portal. The verdict remains nullable, and its tone is one of the six defined values. The response includes no merchant `category` or structured percentile. | `site/src/pages/api/v1/merchants/[slug].json.ts:43`, `:54`, `:165`, `site/src/lib/verdicts.ts:55`, `:1554`, `:2063`, `site/src/lib/data/index.ts:326`, `supabase/migrations/20260711121000_scraper_core.sql:124`. The fixtures include only non-null summaries and verdicts. |
| Merchant rows | The old spec used one shape with an optional `listing_label`. Every full row includes that nullable field. Unit leaders omit it and match a full row on the shared fields. The label is a distinct listing name and can remain null when names collide. | `site/src/pages/api/v1/merchants/[slug].json.ts:101`, `:139`, `site/src/lib/duplicate-labels.ts:66`, `:77`. All 199 full rows have the key with null in these captures. |
| Merchant ranking and freshness | The old spec lacked the meaning of `best_rates`, the category-demotion fields, and freshness at each level. The app chooses one leader per exact unit, excludes zero rates, and can filter out stale candidates. Equal values favor the row without an up-to qualifier. Category demotion keeps the headline value and separately exposes the effective value and its label. A program may appear only in the full list. Consumers should check each row's freshness, even when the envelope is newer. | `site/src/pages/api/v1/merchants/[slug].json.ts:57`, `:73`, `:101`, `site/src/lib/verdicts.ts:723`, `:889`. The Nike capture has 37 full rows and three leaders. |
| Portal directory | The existing keys were correct. The old spec left the category and label unconstrained and did not distinguish returned rows from coverage. The directory excludes `giftcard`, includes paused comparison portals, and orders rows by name. `active_count` counts active comparison portals, while `count` includes paused rows. The timestamp uses the latest successful check across those directory rows. | `site/src/pages/api/v1/portals.json.ts:17`, `:30`, `:50`, `site/src/lib/portal-count.ts:57`, `:115`, `:141`. The directory fixture contains 46 rows. |
| Portal detail | The old spec documented optional `portal.payout_kind` and had no 25-row limit. The detail projection omits `payout_kind` and `is_active`. It accepts the full category set because its lookup uses unfiltered freshness. Top rows use the server's native-unit order, then descending value within the unit. They carry `is_stale`. The envelope timestamp is the portal's last success and may be null. | `site/src/pages/api/v1/portals/[portal].json.ts:15`, `:23`, `:46`, `site/src/lib/data/index.ts:229`, `site/src/lib/data/live.ts:937`, `site/src/lib/verdicts.ts:374`. Both captured profiles have 25 rows and omit payout kind and row-level confirmation times. |
| Highs | The old row keys and types were correct, but their meaning and the feed cap were missing. Live reads cap candidates at 400 per kind, require at least seven observed days, and retain rows at or above 95% of the recorded 365-day high. Earn rates come before one-time bonuses. `is_all_time_high` comes from the recorded stats with a 30-day minimum. `typical_range` is nullable display text for the middle half of the observed distribution. The response timestamp is the newest among the included rates, or null for an empty feed. | `site/src/pages/api/v1/highs.json.ts:19`, `:36`, `:49`, `site/src/lib/stats.ts:115`, `site/src/lib/data/index.ts:784`, `:1001`, `site/src/lib/data/live.ts:1538`, `:1619`. The fixture contains 800 rows and both values of the high flag. It emits no per-row `is_up_to`, `is_stale`, or `last_confirmed_at`. |
| Shared enums | The old spec allowed arbitrary strings for rate units, rate kinds, unit groups, payout kinds, portal categories and their displayed labels, and verdict tones. It already enumerated the search result kind. The spec now uses implementation enums. It includes the seventh unit `cents_per_gallon` and its `Other` group even though the fixtures cover only the other six. `payout_kind` is `gift_card` or null when emitted. | `site/src/lib/format.ts:7`, `:31`, `:266`, `site/src/lib/types.ts:166`, `:200`, `site/src/lib/verdicts.ts:55`, `supabase/migrations/20260720150000_portal_payout_kind.sql:37`. |
| Success envelope, attribution, and links | The envelope already required all five keys. It now describes which timestamp each endpoint supplies. It preserves the source, attribution, and disclosure and tells clients to link to the item's `page_url`. Merchant row `go_url` is a nullable HTTPS outbound portal link with `plc=api` and an optional merchant ID. Reserve it for user clicks. | `site/src/lib/api.ts:11`, `:15`, `:25`, `:66`, `site/src/pages/go/[link_id].ts:72`, `:233`, `site/src/pages/developers.astro:180`. Captured timestamps include fractional seconds and UTC offsets. |
| Transport and errors | The old shared JSON `default` response implied a JSON body for platform failures. Explicit invalid-query and lookup errors return `{ "error": string }` with CORS and `no-store`. Successful JSON uses CORS and a 300-second client cache lifetime. The origin also sets shared-cache directives, and degraded reads use `no-store`. Each OPTIONS handler returns an empty 204 with CORS. Unhandled 500s go through the framework. The locked Astro dispatcher falls back from HEAD to GET and returns a framework 404 for methods with no handler. The app exports no 405 handler. | `site/src/lib/api.ts:19`, `:36`, `:57`, `:61`, `site/src/middleware.ts:162`, `site/src/lib/mcp/telemetry.ts:155`, all five API routes' `OPTIONS` exports, and the locked Astro 7.0.7 `astro/dist/runtime/server/endpoint.js:8`, `:20`, `:44` (`site/package-lock.json:4945`). The three error bodies are captured, and the live check also verified their content type, CORS, and cache policy. |

## App bugs and documentation gaps

- **Unknown method and unhandled error responses have a different contract.**
  The app handles the expected 400 and 404 errors through the JSON/CORS helper.
  The Astro method fallback and rethrown handler exceptions bypass that helper.
  Browser clients can lose the JSON body and CORS headers in those cases.
  The current runtime supplies a 404 for an unsupported method reaching the
  dispatcher. The framework response is distinct from a missing-entity 404.
  Evidence is source-derived. `site/src/lib/api.ts:57`,
  `site/src/lib/mcp/telemetry.ts:161`, Astro 7.0.7
  `astro/dist/runtime/server/endpoint.js:20`.
- **The declared API click placement is discarded.** The link producer emits
  `plc=api` and the click recorder recognizes only its placement allowlist,
  which omits `api`. Click placement is recorded as null. The redirect still
  uses the resolved destination. This is a source-confirmed attribution
  defect already described in the app's adoption notes.
  `site/src/lib/api.ts:66`, `site/src/lib/clicks-util.ts:12`,
  `site/src/pages/go/[link_id].ts:104`, `:217`, `:233`,
  `docs/mcp-adoption-and-access.md:162`.
- **The highs feed can report a stale all-time-high flag after a rate change.**
  If the current rate no longer matches the stats value, the join can take a
  different value in the same unit and keep it when it clears the 95% gate.
  The JSON response still uses the stats snapshot's high flag. A same-priced
  sibling listing can also supply the wrong history because the stats view
  omits the alias ID. These are source-derived risks and the fixture cannot
  establish which, if any, captured rows were affected.
  `site/src/lib/data/index.ts:1001`, `:1044`,
  `site/src/pages/api/v1/highs.json.ts:26`.
- **REST freshness copy needs the endpoint distinctions.** The developer
  page's envelope example shows a timestamp and says every endpoint uses the
  same shape. Search always supplies null, the explicit errors use a separate
  body, and the highs and portal lists have no per-row confirmation timestamp.
  The page describes the merchant response as “every portal’s live rate” even
  though it can include stale or zero-rate rows and omits gift-card marketplace
  rows. The program example uses the MCP names `all_rates` and
  `best_per_unit`. REST readers need the `rates` and `best_rates` names.
  `site/src/pages/developers.astro:33`, `:75`, `:159`,
  `site/src/pages/api/v1/search.json.ts:30`,
  `site/src/pages/api/v1/merchants/[slug].json.ts:73`, `:139`, `:181`,
  `site/src/lib/data/index.ts:184`.
- **Payout and qualifier context is uneven across endpoints.** A gift-card-only
  payout is explicit in the directory and merchant and high rows, but absent
  from the portal detail profile. Highs also drops `is_up_to` while formatting
  the value without the qualifier. Consumers need the merchant response to
  determine whether the listed value is an upper bound.
  `site/src/pages/api/v1/portals.json.ts:35`,
  `site/src/pages/api/v1/portals/[portal].json.ts:49`,
  `site/src/pages/api/v1/highs.json.ts:25`, `site/src/lib/format.ts:91`.

## Verification and limits

- Strict offline validation found 24 matching response bodies and zero extra
  fields. The fixtures contain no headers. Nullable summary, non-null listing
  labels, positive suggestion flags, and some enum values are represented
  via source rules and tests rather than fixture observations.
- The serial live check passed eight GETs with no undocumented fields. It
  covered all five successful route shapes, a short-query 400, and both
  unknown-ID 404s. OPTIONS, HEAD, unsupported methods, and thrown 500s were
  examined in source. The checker never followed any outbound URL.
- The kit's root README and `pyproject.toml` are outside this change. The
  README still describes the old five-request checker. The optional
  `check` extra needs to match `requirements-check.txt` to install the
  checker's URI-format validator through that packaging entry point.
