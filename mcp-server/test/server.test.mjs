import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { AjvJsonSchemaValidator } from "@modelcontextprotocol/sdk/validation/ajv";
import { CbysClient } from "../dist/client.js";
import { createMcpServer } from "../dist/server.js";

const fixtures = fileURLToPath(new URL("../../fixtures/live-2026-11-22/", import.meta.url));
const offline = { CBYS_FIXTURES_DIR: fixtures, CBYS_BASE_URL: "invalid in offline mode" };

async function connect(env) {
  const server = createMcpServer(new CbysClient(env));
  const client = new Client({ name: "cbys-test", version: "0.1.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  try {
    await client.connect(clientTransport);
    const { tools } = await client.listTools(); // The SDK compiles and applies the advertised output schemas.
    return { client, tools, close: async () => { await client.close(); await server.close(); } };
  } catch (error) {
    await client.close();
    await server.close();
    throw error;
  }
}

function assertNoOverallWinner(value) {
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    assert.doesNotMatch(key, /best.?overall|overall.?best|overall.?winner|winner.?overall/i);
    assertNoOverallWinner(child);
  }
}

let session;
before(async () => { session = await connect(offline); });
after(async () => { await session?.close(); });

async function success(name, args, { client } = session) {
  const { structuredContent: data, content, isError } = await client.callTool({ name, arguments: args });
  assert.equal(isError, undefined, JSON.stringify(content));
  assert.ok(data);
  assert.equal(data.fixture_mode, true);
  assert.equal(data.source, "CheckBeforeYouShop");
  assert.match(content[0].text, /Historical fixture snapshot/);
  assert.ok(content[0].text.includes(data.attribution));
  assert.ok(content[0].text.includes(data.disclosure));
  assertNoOverallWinner(data);
  return { data, text: content[0].text };
}

async function error(name, args, pattern, { client } = session) {
  const result = await client.callTool({ name, arguments: args });
  assert.equal(result.isError, true);
  assert.equal(result.structuredContent, undefined);
  assert.match(result.content[0].text, pattern);
  assert.doesNotMatch(result.content[0].text, /\n\s+at /);
}

function assertUnitGroups(groups) {
  for (const [unit, group] of Object.entries(groups)) {
    assert.ok(group.unit_label);
    assert.ok(group.rows.length);
    assert.ok(group.rows.every((row) => row.rate_unit === unit && row.rate_kind === group.rate_kind));
  }
}

test("lists all five annotated tools with valid input and output schemas", () => {
  const examples = {
    search_stores: { query: "nike" },
    get_store_rates: { store: "nike" },
    list_portals: {},
    get_portal: { portal: "rakuten" },
    get_highs: {},
  };
  const validator = new AjvJsonSchemaValidator();
  assert.deepEqual(session.tools.map((tool) => tool.name), Object.keys(examples));
  for (const tool of session.tools) {
    assert.ok(tool.description.length);
    assert.equal(tool.annotations.readOnlyHint, true);
    assert.equal(tool.annotations.openWorldHint, true);
    assert.equal(tool.inputSchema.type, "object");
    assert.equal(tool.outputSchema.type, "object");
    assert.equal(validator.getValidator(tool.inputSchema)(examples[tool.name]).valid, true);
    assert.equal(validator.getValidator(tool.outputSchema)({}).valid, false);
  }
  assert.match(session.client.getInstructions(), /Never fetch or activate it/);
  assert.match(session.client.getInstructions(), /historical snapshots/);
});

test("search returns an exact match and separates store and portal candidates", async () => {
  const { data } = await success("search_stores", { query: " Nike " });
  assert.equal(data.query, "nike");
  assert.equal(data.exact_match.slug, "nike");
  assert.equal(data.exact_match.page_url, "https://checkbeforeyoushop.com/m/nike");
  assert.equal(data.needs_disambiguation, undefined);
  assert.ok(data.candidates.stores.length > 1);
  assert.ok(data.candidates.stores.every((row) => row.kind === "merchant"));
});

for (const [query, slug] of [
  ["american", "american-eagle-outfitters"],
  ["macys", "macy-s-us"],
  ["delta", "delta-air-lines"],
  ["home depot", "the-home-depot"],
]) {
  test(`search and rates ask which listing the user means for "${query}"`, async () => {
    const search = await success("search_stores", { query });
    const rates = await success("get_store_rates", { store: query });
    assert.equal(search.data.exact_match, undefined);
    assert.equal(search.data.needs_disambiguation, true);
    assert.equal(rates.data.needs_disambiguation, true);
    assert.equal(rates.data.rates_by_unit, undefined);
    assert.deepEqual(rates.data.candidates, search.data.candidates);
    assert.ok(rates.data.candidates.stores.some((row) => row.slug === slug));
    assert.ok(rates.data.candidates.portals.every((row) => row.kind === "portal"));
    assert.match(rates.text, /Ask the user/);
    if (query === "delta") assert.equal(rates.data.candidates.portals[0].slug, "delta-skymiles");
    if (query === "macys") assert.ok(rates.data.candidates.stores.some((row) => row.slug === "macys-com"));
  });
}

test("not-found searches and 404s report actionable tool errors", async () => {
  await error("search_stores", { query: "zzqxnotastore" }, /No tracked stores or portals/);
  await error("get_store_rates", { store: "zzqxnotastore" }, /Try search_stores/);
  await error("get_store_rates", { store: "does-not-exist-zzq" }, /No store with that slug.+Try search_stores/);
  await error("get_portal", { portal: "does-not-exist-zzq" }, /Try list_portals/);
});

test("fixture misses fail loudly without falling through to the network", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new Error("unexpected network call"); });
  await error("search_stores", { query: "unrecorded input" }, /q=unrecorded input not in fixtures/);
  await error("get_store_rates", { store: "unrecorded-slug" }, /not in fixtures/);
  await error("get_portal", { portal: "TopCashback" }, /\/portals\/topcashback\.json not in fixtures/);
  assert.equal(fetch.mock.callCount(), 0);
});

test("Square has three distinct one-time bonus units and no earn rates", async () => {
  const { data, text } = await success("get_store_rates", { store: "square" });
  assert.equal(data.store.slug, "square");
  assert.deepEqual(Object.keys(data.rates_by_unit).sort(), ["flat_cash", "flat_miles", "flat_points"]);
  assertUnitGroups(data.rates_by_unit);
  assert.ok(Object.values(data.rates_by_unit).every((group) => group.rate_kind === "one_time_bonus"));
  assert.match(text, /one-time bonus/);
  assert.match(data.summary, /one-time bonus/);
  assert.match(data.verdict.headline, /one-time bonus/);
});

test("Macys.com orders flat rates above up-to ceilings at the same value", async () => {
  const { data } = await success("get_store_rates", { store: "macys-com" });
  assertUnitGroups(data.rates_by_unit);
  const rows = data.rates_by_unit.pct_cash.rows;
  assert.ok(rows.some((row) => row.is_up_to));
  assert.deepEqual(rows.filter((row) => row.rate_value === 10).map((row) => row.is_up_to), [false, true, true]);
  assert.ok(rows.every((row, index) => index === 0 || row.rate_value <= rows[index - 1].rate_value));
});

test("Nike program filter is case insensitive and retains confirmed row details", async () => {
  for (const program of ["DeLTa", "Delta SkyMiles", "DELTA-SKYMILES", "Delta SkyMiles Shopping"]) {
    const { data, text } = await success("get_store_rates", { store: " Nike ", program });
    assert.equal(data.program_match, "matched");
    assert.equal(data.verdict_scope, "store_wide");
    assert.deepEqual(Object.keys(data.rates_by_unit), ["miles_per_dollar"]);
    const [row, ...extra] = data.rates_by_unit.miles_per_dollar.rows;
    assert.equal(extra.length, 0);
    assert.equal(row.portal_id, "delta-skymiles");
    assert.equal(row.rate_display, "1 mi/$");
    assert.equal(row.is_stale, false);
    assert.notEqual(row.last_confirmed_at, data.data_as_of);
    assert.equal(new URL(row.go_url).searchParams.get("plc"), "api");
    assert.match(text, /1 mi\/\$ via Delta SkyMiles Shopping/);
    assert.ok(text.includes(row.last_confirmed_at));
  }
});

test("an unknown program returns available programs and no rates", async () => {
  const { data, text } = await success("get_store_rates", { store: "nike", program: "unknown-zzq" });
  assert.equal(data.program_match, "none");
  assert.deepEqual(data.rates_by_unit, {});
  assert.ok(data.available_programs.includes("Delta SkyMiles"));
  assert.match(text, /No tracked rate rows match/);
  const { data: otherUnit } = await success("get_store_rates", {
    store: "nike", program: "Delta", unit: "pct_cash",
  });
  assert.equal(otherUnit.program_match, "matched");
  assert.deepEqual(otherUnit.rates_by_unit, {});
});

test("lists portal categories and flags inactive and never-succeeded profiles", async () => {
  const { data: all } = await success("list_portals", {});
  assert.equal(all.count, all.portals.length);
  assert.equal(all.active_count, all.portals.filter((row) => row.is_active && row.last_success_at).length);
  const inactive = all.portals.find((row) => row.portal_id === "inboxdollars");
  assert.equal(inactive.is_active, false);
  assert.equal(inactive.last_success_at, null);
  assert.equal(inactive.data_status, "never_succeeded");
  const { data: filtered } = await success("list_portals", { category: " Airline Miles " });
  assert.ok(filtered.count > 0 && filtered.count < all.count);
  assert.ok(filtered.portals.every((row) => row.category === "airline"));
});

test("get_portal matches name and ID and groups top rates with freshness limits", async () => {
  for (const [input, id] of [["Delta SkyMiles Shopping", "delta-skymiles"], ["rakuten", "rakuten"]]) {
    const { data } = await success("get_portal", { portal: input });
    assert.equal(data.portal.portal_id, id);
    assert.equal(data.portal.is_active, true);
    assert.equal(data.portal.data_status, "active");
    assert.equal(data.portal.last_success_at, data.data_as_of);
    assertUnitGroups(data.top_rates_by_unit);
    assert.ok(Object.values(data.top_rates_by_unit).flatMap((group) => group.rows)
      .every((row) => row.last_confirmed_at === null && typeof row.is_stale === "boolean"));
  }
});

test("highs applies filters and caps the total without omitting bonuses from the default sample", async () => {
  const { data } = await success("get_highs", {});
  assert.equal(data.count, 20);
  assert.equal(Object.values(data.highs_by_unit).flatMap((group) => group.rows).length, 20);
  assert.ok(data.matching_count > data.count);
  assertUnitGroups(data.highs_by_unit);
  assert.equal(data.highs_by_unit.pct_cash.rate_kind, "earn_rate");
  assert.equal(data.highs_by_unit.flat_points.rate_kind, "one_time_bonus");
  const { data: filtered } = await success("get_highs", { unit: "flat_miles", kind: "one_time_bonus", limit: 2 });
  assert.deepEqual(Object.keys(filtered.highs_by_unit), ["flat_miles"]);
  assert.equal(filtered.count, 2);
  assert.ok(filtered.highs_by_unit.flat_miles.rows.every(
    (row) => row.is_stale === null && row.is_up_to === null && row.last_confirmed_at === null,
  ));
});

test("resolves exact names and domains, and asks about shared domains or lone fuzzy hits", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "cbys-mcp-resolve-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const search = JSON.parse(await readFile(join(fixtures, "search/nike.json"), "utf8"));
  const [nike, regional] = search.data.results;
  const renamed = { ...nike, name: "Nike Shop" };
  const requests = {
    "/api/v1/merchants/nike.json": { status: 200, file: "nike.json" },
  };
  for (const [query, results] of [
    ["nike shop", [renamed, regional]],
    ["nike.com", [nike]],
    ["shared.example", [nike, regional].map((row) => ({ ...row, domain: "shared.example" }))],
    ["nik", [nike]],
  ]) {
    const file = `search-${query}.json`;
    requests[`/api/v1/search.json?q=${query}`] = { status: 200, file };
    await writeFile(join(dir, file), JSON.stringify({
      ...search,
      _synthetic_note: "Search candidates assembled to test exact identity handling.",
      data: { query, count: results.length, results },
    }));
  }
  const store = await readFile(join(fixtures, "merchants/nike.json"), "utf8");
  await Promise.all([
    writeFile(join(dir, "manifest.json"), JSON.stringify({ requests })),
    writeFile(join(dir, "nike.json"), store),
  ]);
  const synthetic = await connect({ CBYS_FIXTURES_DIR: dir });
  t.after(synthetic.close);
  const { data: byDomain } = await success("get_store_rates", { store: " NIKE.COM " }, synthetic);
  assert.equal(byDomain.store.slug, "nike");
  const { data: byName } = await success("get_store_rates", { store: " Nike Shop " }, synthetic);
  assert.equal(byName.store.slug, "nike");
  for (const query of ["shared.example", "nik"]) {
    const { data } = await success("get_store_rates", { store: query }, synthetic);
    assert.equal(data.needs_disambiguation, true);
    assert.equal(data.store, undefined);
  }
});

test("stale rows stay labeled, sort behind fresh rows, and are optional", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "cbys-mcp-test-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const body = JSON.parse(await readFile(join(fixtures, "merchants/nike.json"), "utf8"));
  const fresh = body.data.rates.find((row) => row.portal_id === "delta-skymiles");
  const stale = {
    ...fresh,
    rate_value: 99,
    rate_display: "99 mi/$",
    is_stale: true,
    last_confirmed_at: "2025-01-01T00:00:00Z",
  };
  body._synthetic_note = "Injected stale Delta row for this test only.";
  body.data.rates = [stale, fresh];
  const requests = { "/api/v1/merchants/nike.json": { status: 200, file: "nike.json" } };
  await Promise.all([
    writeFile(join(dir, "manifest.json"), JSON.stringify({ requests })),
    writeFile(join(dir, "nike.json"), JSON.stringify(body)),
  ]);
  const synthetic = await connect({ CBYS_FIXTURES_DIR: dir });
  t.after(synthetic.close);
  const { data, text } = await success("get_store_rates", { store: "nike", program: "delta" }, synthetic);
  assert.deepEqual(data.rates_by_unit.miles_per_dollar.rows.map((row) => row.is_stale), [false, true]);
  assert.match(text, /99 mi\/\$.+2025-01-01T00:00:00Z \(stale\)/);
  const { data: current } = await success("get_store_rates", { store: "nike", include_stale: false }, synthetic);
  assert.deepEqual(current.rates_by_unit.miles_per_dollar.rows, [fresh]);
});

test("network failure returns a friendly tool error and uses a read-only JSON request", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new Error("network failed"); });
  const live = await connect({ CBYS_BASE_URL: "https://example.invalid" });
  t.after(live.close);
  await error("search_stores", { query: "Home Depot" }, /Could not reach or read the CheckBeforeYouShop API/, live);
  assert.equal(fetch.mock.callCount(), 1);
  const [url, options] = fetch.mock.calls[0].arguments;
  assert.equal(url.href, "https://example.invalid/api/v1/search.json?q=home+depot");
  assert.equal(options.method, "GET");
  assert.equal(options.redirect, "error");
  assert.match(options.headers["User-Agent"], /^cbys-developer-kit-/);
});

test("invalid tool arguments return tool errors without reading API data", async () => {
  await error("search_stores", { query: "a" }, /Invalid arguments/);
  await error("get_highs", { limit: 0 }, /Invalid arguments/);
});
