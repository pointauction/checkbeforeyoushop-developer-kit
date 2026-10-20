# CheckBeforeYouShop developer kit

OpenAPI description, sample clients, and low-volume contract check for the public CheckBeforeYouShop API. This kit does not host the service or its MCP server.

## Quick start

```sh
python3 example.py
python3 example.py nike --program cash
python3 example.py Nike --program delta
```

The example defaults to the Nike store and prints all tracked rate rows unless `--program` is given. It resolves exact slug, name, or domain first; ambiguous matches are reported for you to disambiguate. It preserves each row's program, native unit, rate kind, stale state, last confirmation, and linked store page. It does not rank across programs or currencies. A missing matching row is reported cleanly. The example uses only the Python standard library.

To validate the API description and five live samples:

```sh
python3 -m pip install -r requirements-check.txt
python3 check_contract.py
```

## Public JSON API

Base URL: `https://checkbeforeyoushop.com`

| GET path | Purpose |
| --- | --- |
| `/api/v1/search.json?q={query}` | Resolve a store or portal name. |
| `/api/v1/merchants/{slug}.json` | Store verdict, best rates by native unit, full portal rate rows, outbound links. |
| `/api/v1/portals.json` | Portal directory and coverage/freshness metadata. |
| `/api/v1/portals/{portal}.json` | Portal profile and top rates. |
| `/api/v1/highs.json` | Rates currently at or near observed highs. |

Successful responses wrap endpoint data in `data`, alongside `data_as_of`, `source`, `attribution`, and `disclosure`. `data_as_of` can be null. Rate values retain their original `rate_unit`; do not compare points, miles, percentages, or flat bonuses as if they share a scale. Store rows include `program`, `rate_kind`, `is_stale`, `last_confirmed_at`, and `go_url`. For a page link use the merchant's `page_url`.

Store detail includes the current verdict, but does not promise a structured percentile or all-time-high metric. The API does not expose the MCP-only raw 21-day history. Any store can lack a listing in a given portal.

## MCP server

Hosted MCP endpoint: `https://checkbeforeyoushop.com/mcp`. It is a stateless Streamable HTTP endpoint; direct JSON-RPC clients send `POST` with `Accept: application/json, text/event-stream`. The endpoint currently advertises seven tools. Access was observed without authentication on 2026-10-20; future access terms may change.

### Cursor

Project config template: [`mcp/cursor.json`](mcp/cursor.json). Or use Cursor Settings → Tools & MCP. The config format is based on [Cursor's MCP documentation](https://cursor.com/docs/mcp).

### VS Code

Project config template: [`mcp/vscode.json`](mcp/vscode.json). VS Code also supports MCP: Add Server. The config format is based on [VS Code MCP setup](https://code.visualstudio.com/docs/agent-customization/mcp-servers) and its [configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

### Claude Code

```sh
claude mcp add --transport http cbys https://checkbeforeyoushop.com/mcp
```

Command format follows [Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

These are source-derived config examples; the clients were not independently installed and tested as part of this kit validation.

## Data and license

The API data is free to use with attribution and a link to each item's `page_url`; carry the response disclosure when re-serving rates. The MIT license applies to this kit's code and specification only. It does not license service data or scraped source material.

## Contract checks

`check_contract.py` validates the OpenAPI document using `openapi-spec-validator`, then validates five serial, bounded live GET responses against the corresponding JSON Schemas using `jsonschema`. It checks no counts, names, values, or timestamps beyond the declared schema. It sends no outbound go clicks and uses no credentials. The included workflow runs manually or weekly.

## Validation and limits

The specification and five live GET samples were validated on October 20, 2026. Configuration examples follow the linked official client documentation; they are not a guarantee that every client plan or device supports custom connectors.

For Delta SkyMiles, read the matching row in the full `rates` list. Delta may be absent from `best_rates` because another miles program leads that unit. The store-wide `data_as_of` is the newest confirmation in the response; check Delta's own `last_confirmed_at` and stale flag before quoting it. No Delta row means no tracked listing was returned, not proof that no offer exists.
