# CheckBeforeYouShop local MCP server

`@checkbeforeyoushop/mcp-server` runs over stdio and calls the public CheckBeforeYouShop JSON API. Use it for local integration and repeatable fixture-based evaluations. The [hosted MCP server](https://checkbeforeyoushop.com/mcp) runs over Streamable HTTP and also exposes tools for rate history, sign-up promos, and stacking. This package is private and is built from the developer kit checkout.

## Build and run

Use Node.js 22 or later. Run these commands from the developer kit root.

```sh
cd mcp-server
npm ci && npm run build
node dist/index.js
```

The last command starts a stdio server and waits for an MCP client. For a command that prints a result and exits, use the evaluator scripts below.

## Client configuration

These four client configurations are untested. The SDK's stdio client was tested. Substitute the absolute path to your built `dist/index.js`.

### Claude Code

```sh
claude mcp add cbys-local -- node /abs/path/mcp-server/dist/index.js
```

### Cursor

Add this entry to `.cursor/mcp.json`.

```json
{
  "mcpServers": {
    "cbys-local": {
      "command": "node",
      "args": ["/abs/path/mcp-server/dist/index.js"]
    }
  }
}
```

### VS Code

Add this entry to `.vscode/mcp.json`.

```json
{
  "servers": {
    "cbys-local": {
      "type": "stdio",
      "command": "node",
      "args": ["/abs/path/mcp-server/dist/index.js"]
    }
  }
}
```

### Codex

Add this section to `~/.codex/config.toml`.

```toml
[mcp_servers.cbys]
command = "node"
args = ["/abs/path/mcp-server/dist/index.js"]
```

## Tools

| Tool | Result |
| --- | --- |
| `search_stores {query}` | Store and portal candidates in separate arrays. A unique exact slug, name, or domain resolves. Ask the user to choose when `needs_disambiguation` is true. |
| `get_store_rates {store, program?, unit?, include_stale?}` | Exact-store lookup with rates grouped by native unit and a summary of the first returned row in each unit. Stale rows are included by default and sorted after fresh rows within their unit. |
| `list_portals {category?}` | Portal directory, with the category ID or label as an optional filter. Use `is_active`, `last_success_at` and `data_status` to distinguish active coverage from inactive or never-succeeded entries. |
| `get_portal {portal}` | Comparison portal profile by exact ID or name, with the API's top rate sample grouped by native unit. Individual confirmation times are `null` when the API omits them. |
| `get_highs {unit?, kind?, limit?}` | At or near tracked highs, grouped by native unit and kind. The total limit defaults to 20. Rows are taken one per unit per round in alphabetical unit order. Within each unit, unconditional rows precede up to rows of the same value. The feed order determines other positions. Unknown freshness and up to status are `null`. |

Each tool rejects unknown argument names. Identity matching is case-insensitive and uses Unicode NFC. `get_store_rates` tries exact program, portal ID, or portal name matches first, then whole words and aliases such as `aa`, `delta`, and `united`. When shorthand matches multiple programs, `program_match` is `ambiguous` and `program_candidates` lists exact choices. A generic term such as `miles`, `points`, or `cash` returns `program_hint` with the relevant `unit` values. When `program_match` is `none`, `available_programs` lists the programs in the full store response.

Compare only within the same `rate_unit` and `rate_kind`. Keep the program and `rate_display`. A one-time bonus is a fixed payout for qualifying activity. An up to rate is an advertised ceiling, and a flat rate ranks ahead at equal value. Store ordering uses `best_category_value` when the API supplies it, while `rate_display` keeps the advertised value. Keep gift-card-only payout restrictions with the rate.

Check each row's `is_stale` and `last_confirmed_at` before quoting it as current. For store rates, `data_as_of` is the newest confirmation in the full store response. The local tool generates `summary` after applying all filters. Responses with rate rows include a separate summary line for each returned unit. Missing rows mean no tracked listing was returned for the selection.

Credit CheckBeforeYouShop, link to the returned item's `page_url`, and carry the `disclosure` when re-serving rates. Show `go_url` only as an affiliate link the user can choose. Fetching it can trigger an outbound click.

## Offline mode and evaluation

Set `CBYS_FIXTURES_DIR` to a directory containing `manifest.json`, such as `../fixtures/live-2026-11-22` from this package. Set the same variable in the client configuration to run its server offline. Use an absolute path for client configs. Search keys use the trimmed, lowercased, NFC-normalized query. An exact store slug can use its recorded merchant endpoint directly. A request key missing from the manifest returns `not in fixtures`. If a recorded slug lookup returned 404, the tool also reports whether the name search is missing from the fixtures. The server stays offline and labels results as historical snapshots.

For live calls, `CBYS_BASE_URL` can override the API origin. The default is `https://checkbeforeyoushop.com`. On HTTP 429, the tool reports the API's `Retry-After` value when provided and delays queued API requests accordingly.

Run these commands from `mcp-server/` to call the built stdio server.

```sh
npm ci && npm run build
export CBYS_FIXTURES_DIR=../fixtures/live-2026-11-22

node scripts/list-tools.mjs
node scripts/call-tool.mjs search_stores '{"query":"macys"}'
node scripts/call-tool.mjs get_store_rates '{"store":"nike","program":"Delta"}'
node scripts/call-tool.mjs list_portals '{"category":"airline"}'
node scripts/call-tool.mjs get_portal '{"portal":"Delta SkyMiles Shopping"}'
node scripts/call-tool.mjs get_highs '{"kind":"one_time_bonus","limit":5}'
```

`list-tools.mjs` prints the JSON tool array with descriptions and schemas. `call-tool.mjs` prints one JSON object with `structuredContent`, `text`, and `isError`. Tool errors return `isError: true` in JSON. Invocation and transport failures exit nonzero.

```sh
npm run typecheck
npm test
```

The tests use the SDK's in-memory transport and the dated fixtures. The MIT license covers the server code. API data use follows the attribution and disclosure terms in the response.
