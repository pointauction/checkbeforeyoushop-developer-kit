# Fixtures

`live-2026-11-22/` holds real public API responses captured once on 2026-11-22 with
serial, throttled GETs (about 30 requests, at least 1.2 s apart). `manifest.json` maps each
request (`/api/v1/...` path plus `?q=` for search) to its file and HTTP status, including
the 400 (short query) and 404 (unknown store/portal) error shapes.

Use them for offline tests and reproducible agent evals. Rates change constantly: never
present a fixture value as a current rate.

Anything hand-made or modified for a test (for example a stale-row trap) lives under
`synthetic/` and must say so in its own `_synthetic_note` field.
