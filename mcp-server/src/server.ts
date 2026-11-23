import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { CbysClient, CbysError } from "./client.js";
import {
  candidate, candidates, directoryPortal, high, kind, normalizeIdentity, portalRate, portalStatus,
  query, resultMetadata, storeProfile, storeRate, term, unit, unitGroups,
} from "./schemas.js";

const annotations = { readOnlyHint: true, openWorldHint: true };
const comparisonRules = [
  "Do not compare across units.",
  "One-time bonuses are not earn rates.",
  "Check each row's last_confirmed_at.",
  "Absence of a row is not proof of no offer.",
  "An up to rate is a ceiling. At equal value prefer a flat rate.",
];

const instructions = [
  "Use search_stores or get_store_rates to identify the store. Ask the user to pick a candidate when needs_disambiguation is true.",
  "Compare only within the same rate_unit and rate_kind. Keep rate_display and the program name. Never convert, sum, or pick an overall winner across units. Label flat payouts as one-time bonuses.",
  "Treat is_up_to as a ceiling and prefer flat rates at equal value. Preserve payout_kind, including gift-card-only rewards.",
  "Check each row's is_stale and last_confirmed_at. Never quote stale or unknown freshness as current. data_as_of is an endpoint-level timestamp. The store summary describes the returned rows by unit.",
  "When a program is requested, show its matching rows. If program_match is ambiguous, follow program_hint and ask the user to choose when candidates are returned. A missing row means no tracked listing was returned.",
  "Credit CheckBeforeYouShop, cite the item's page_url, and include the disclosure when re-serving rates. Show go_url as an affiliate link for the user to choose. Never fetch or activate it.",
].join(" ");

const searchFields = {
  query: z.string(),
  candidates,
};
const comparisonFields = {
  ...resultMetadata,
  comparison_rules: z.array(z.string()),
};
const searchOutput = z.object({
  ...resultMetadata,
  ...searchFields,
  exact_match: candidate.optional().describe("The unique exact slug, name, or domain match."),
  needs_disambiguation: z.literal(true).optional().describe("Ask the user to choose from candidates."),
});
const programCandidate = storeRate.pick({ program: true, portal_id: true, portal_name: true });
const ratesOutput = z.object({
  ...comparisonFields,
  query: z.string(),
  candidates: candidates.optional(),
  needs_disambiguation: z.literal(true).optional().describe("Ask the user to choose from candidates."),
  store: storeProfile.optional().describe("The resolved store. Absent if the user must choose a candidate."),
  rates_by_unit: unitGroups(storeRate).optional().describe("Tracked rows keyed by exact native unit."),
  summary: z.string().optional().describe("One statement per returned unit based on its first row."),
  program_match: z.enum(["matched", "none", "ambiguous"]).optional().describe("Match in the full store listing before applying the unit and stale filters."),
  available_programs: z.array(z.string()).optional().describe("Programs in the full store listing when program_match is none."),
  program_candidates: z.array(programCandidate).optional().describe("Matches to choose from when shorthand refers to several programs."),
  program_hint: z.string().optional().describe("How to refine an ambiguous program filter."),
});
const directoryEntry = directoryPortal.extend(portalStatus);

const unitLabels: Readonly<Record<string, string>> = {
  pct_cash: "Percent cashback",
  miles_per_dollar: "Miles per dollar",
  points_per_dollar: "Points per dollar",
  cents_per_gallon: "Cents per gallon",
  flat_cash: "Cash one-time bonus",
  flat_points: "Points one-time bonus",
  flat_miles: "Miles one-time bonus",
};

type Candidate = z.infer<typeof candidate>;
type Candidates = z.infer<typeof candidates>;
type Metadata = z.infer<z.ZodObject<typeof resultMetadata>>;
type DirectoryPortal = z.infer<typeof directoryPortal>;
type StoreRate = z.infer<typeof storeRate>;
type High = z.infer<typeof high>;
type ProgramFields = Pick<z.infer<typeof ratesOutput>, "program_match" | "program_candidates" | "available_programs" | "program_hint">;
type Rate = Pick<StoreRate, "rate_unit" | "rate_kind" | "unit_group" | "rate_value">;
type RankableRate = Rate & { is_up_to: boolean; is_stale: boolean; best_category_value?: number | null };
type Group<Row> = { unit_label: string; rate_kind: Rate["rate_kind"]; rows: Row[] };

function groupRates<Row extends Rate>(rows: Row[], compare?: (a: Row, b: Row) => number) {
  const groups = new Map<string, Group<Row>>();
  for (const row of rows) {
    const existing = groups.get(row.rate_unit);
    if (existing) {
      // The API derives kind from unit. Refuse to rank mixed kinds if that contract breaks.
      if (existing.rate_kind !== row.rate_kind) {
        throw new CbysError("The CheckBeforeYouShop API returned mixed rate kinds for one unit.");
      }
      existing.rows.push(row);
    } else {
      const fallbackLabel = row.rate_kind === "one_time_bonus" ? `${row.unit_group} one-time bonus` : row.unit_group;
      groups.set(row.rate_unit, {
        unit_label: Object.hasOwn(unitLabels, row.rate_unit) ? unitLabels[row.rate_unit]! : fallbackLabel,
        rate_kind: row.rate_kind,
        rows: [row],
      });
    }
  }
  if (compare) {
    for (const group of groups.values()) group.rows.sort(compare);
  }
  return Object.fromEntries([...groups].sort(([a], [b]) => a.localeCompare(b)));
}

function compareWithinUnit(a: RankableRate, b: RankableRate) {
  return Number(a.is_stale) - Number(b.is_stale) ||
    (b.best_category_value ?? b.rate_value) - (a.best_category_value ?? a.rate_value) ||
    Number(a.is_up_to) - Number(b.is_up_to) ||
    b.rate_value - a.rate_value;
}

function preferUnconditionalHighs(rows: High[]) {
  const ties = new Map<number, { positions: number[]; flat: High[]; upTo: High[] }>();
  for (const [index, row] of rows.entries()) {
    if (row.is_up_to === null) continue;
    const tie = ties.get(row.rate_value) ?? { positions: [], flat: [], upTo: [] };
    tie.positions.push(index);
    (row.is_up_to ? tie.upTo : tie.flat).push(row);
    ties.set(row.rate_value, tie);
  }
  // Move only rows that share a value and have a known up-to status.
  for (const { positions, flat, upTo } of ties.values()) {
    const ordered = [...flat, ...upTo];
    positions.forEach((position, index) => { rows[position] = ordered[index]!; });
  }
}

function limitHighs<Row>(groups: Record<string, Group<Row>>, limit: number) {
  const selected = new Map<string, Group<Row>>();
  const entries = Object.entries(groups);
  // Take one from each unit per round. Never use a value in one unit to
  // decide how many rows of another unit make the limit.
  for (let index = 0; limit > 0; index++) {
    let added = false;
    for (const [key, group] of entries) {
      const row = group.rows[index];
      if (row === undefined) continue;
      const result = selected.get(key) ?? { ...group, rows: [] };
      result.rows.push(row);
      selected.set(key, result);
      added = true;
      if (--limit === 0) break;
    }
    if (!added) break;
  }
  return Object.fromEntries(selected);
}

function exactMatch(rows: Candidate[], value: string) {
  const slugMatches = rows.filter((row) => normalizeIdentity(row.slug) === value);
  const matches = slugMatches.length ? slugMatches : rows.filter((row) =>
    normalizeIdentity(row.name) === value || (row.domain !== null && normalizeIdentity(row.domain) === value)
  );
  return matches.length === 1 ? matches[0] : undefined;
}

function notFoundStore(value: string) {
  return new CbysError(`No store with that slug or name ("${value}"). Try search_stores with the full store name or domain.`, 404);
}

async function findCandidates(client: CbysClient, value: string) {
  const { data, ...metadata } = await client.search(value);
  return {
    ...metadata,
    query: value,
    candidates: {
      stores: data.results.filter((row) => row.kind === "merchant"),
      portals: data.results.filter((row) => row.kind === "portal"),
    },
  };
}

async function loadStore(client: CbysClient, value: string) {
  // The direct endpoint is authoritative for a literal slug, including slugs
  // that the search API doesn't return. In fixtures, probe only recorded paths.
  if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value) &&
      (!client.fixtureMode || await client.hasMerchantFixture(value))) {
    try {
      const response = await client.merchant(value);
      if (normalizeIdentity(response.data.merchant.slug) === value) return { response };
    } catch (error) {
      if (!(error instanceof CbysError) || error.status !== 404) throw error;
      if (client.fixtureMode && !await client.hasSearchFixture(value)) {
        throw new CbysError(`The store slug "${value}" returned HTTP 404. The name search is not in fixtures.`, 404);
      }
    }
  }

  if (value.length < 2) throw notFoundStore(value);
  const search = await findCandidates(client, value);
  const { stores, portals } = search.candidates;
  if (stores.length === 0 && portals.length === 0) throw notFoundStore(value);
  const match = exactMatch(stores, value);
  if (!match) return { search };
  try {
    return { response: await client.merchant(match.slug) };
  } catch (error) {
    if (error instanceof CbysError && error.status === 404) throw notFoundStore(match.slug);
    throw error;
  }
}

function portalStatusFor(portal: DirectoryPortal) {
  if (!portal.last_success_at) return "never_succeeded" as const;
  return portal.is_active ? "active" as const : "inactive" as const;
}

const programAliases = new Map([
  ["aa", "aa-eshopping"],
  ["american", "aa-eshopping"],
  ["aadvantage", "aa-eshopping"],
  ["delta", "delta-skymiles"],
  ["united", "united-mileageplus"],
]);

const programUnitHints = new Map([
  ["mile", "miles_per_dollar or flat_miles"],
  ["miles", "miles_per_dollar or flat_miles"],
  ["point", "points_per_dollar or flat_points"],
  ["points", "points_per_dollar or flat_points"],
  ["cash", "pct_cash or flat_cash"],
  ["cash back", "pct_cash or flat_cash"],
  ["cashback", "pct_cash or flat_cash"],
]);

function programTokens(value: string) {
  return value.match(/[\p{L}\p{M}\p{N}]+/gu)?.join(" ") ?? "";
}

function filterProgram(rows: StoreRate[], program: string): { rows: StoreRate[]; fields: ProgramFields } {
  const needle = normalizeIdentity(program);
  const tokens = programTokens(needle);
  const units = programUnitHints.get(tokens);
  if (units) {
    return {
      rows: [],
      fields: {
        program_match: "ambiguous",
        program_hint: `Use the unit filter with ${units}.`,
      },
    };
  }

  const identities = rows.map((row) => ({
    row,
    names: [row.program, row.portal_id, row.portal_name].map(normalizeIdentity),
  }));
  const exact = identities.filter(({ names }) => names.includes(needle)).map(({ row }) => row);
  if (exact.length) return { rows: exact, fields: { program_match: "matched" } };

  const alias = programAliases.get(needle);
  const matches = identities.filter(({ row, names }) =>
    (alias && normalizeIdentity(row.portal_id) === alias) ||
    (tokens && names.some((name) => ` ${programTokens(name)} `.includes(` ${tokens} `)))
  ).map(({ row }) => row);
  const distinctPrograms = new Set(matches.map((row) => normalizeIdentity(row.program)));
  if (distinctPrograms.size > 1) {
    const portals = new Map(matches.map(({ program, portal_id, portal_name }) =>
      [normalizeIdentity(portal_id), { program, portal_id, portal_name }]
    ));
    return {
      rows: [],
      fields: {
        program_match: "ambiguous",
        program_candidates: [...portals.values()],
        program_hint: "Choose an exact program or portal from the candidates.",
      },
    };
  }
  if (matches.length) return { rows: matches, fields: { program_match: "matched" } };
  return {
    rows: [],
    fields: {
      program_match: "none",
      available_programs: [...new Set(rows.map((row) => row.program))].sort((a, b) => a.localeCompare(b)),
    },
  };
}

function formatStoreRate(row: StoreRate) {
  const display = `${row.is_up_to ? "Up to " : ""}${row.rate_display}`;
  const stale = row.is_stale ? " (stale)" : "";
  const payout = row.payout_kind === "gift_card" ? " (gift card only)" : "";
  return `${display} via ${row.portal_name} (${row.program})${payout}, last confirmed ${row.last_confirmed_at}${stale}.`;
}

function groupSummary(groups: Record<string, Group<Rate>>) {
  return Object.values(groups).map((group) => `${group.unit_label} (${group.rows.length})`).join(", ");
}

function disambiguationText(matches: Candidates) {
  const sections = ([["Stores", matches.stores], ["Portals", matches.portals]] as const)
    .filter(([, rows]) => rows.length > 0)
    .map(([label, rows]) => {
      const listed = rows.slice(0, 5).map((row) => `${row.name} (${row.slug}) ${row.page_url}`);
      if (rows.length > listed.length) listed.push(`and ${rows.length - listed.length} more in candidates`);
      return `${label} - ${listed.join(", ")}.`;
    });
  return ["Ask the user which listing they mean.", ...sections].join("\n");
}

function result<T extends Metadata>(data: T, text: string): CallToolResult {
  const note = data.fixture_mode ? "Historical fixture snapshot.\n" : "";
  return {
    structuredContent: data,
    content: [{ type: "text", text: `${note}${text}\n${data.attribution}\n${data.disclosure}` }],
  };
}

async function runTool(run: () => Promise<CallToolResult>): Promise<CallToolResult> {
  try {
    return await run();
  } catch (error) {
    const text = error instanceof CbysError
      ? error.message
      : "Could not complete the CheckBeforeYouShop lookup.";
    return { isError: true, content: [{ type: "text", text }] };
  }
}

export function createMcpServer(client = new CbysClient()) {
  const server = new McpServer({ name: "checkbeforeyoushop-local", version: "0.1.0" }, {
    instructions: client.fixtureMode
      ? `${instructions} This server is in offline fixture mode. All rates are historical snapshots.`
      : instructions,
  });

  server.registerTool("search_stores", {
    description: "Find tracked stores and portals by slug, name, or domain. Candidates are separated by type. When needs_disambiguation is true, ask the user to choose a listing and use its slug. Cite page_url.",
    inputSchema: z.strictObject({ query }),
    outputSchema: searchOutput,
    annotations,
  }, ({ query }) => runTool(async () => {
    const value = normalizeIdentity(query);
    const search = await findCandidates(client, value);
    const rows = [...search.candidates.stores, ...search.candidates.portals];
    if (rows.length === 0) throw new CbysError(`No tracked stores or portals match "${value}". Try a full store name or domain.`);
    const match = exactMatch(rows, value);
    return match
      ? result({ ...search, exact_match: match }, `Exact ${match.kind === "merchant" ? "store" : "portal"} match for ${match.name} (${match.slug}) ${match.page_url}`)
      : result({ ...search, needs_disambiguation: true }, disambiguationText(search.candidates));
  }));

  server.registerTool("get_store_rates", {
    description: "Compare tracked rates for one exact store. Ask the user when needs_disambiguation is true. Each summary line describes one unit in the filtered rows. If program_match is ambiguous, follow program_hint. Treat up to as a ceiling and check each row's freshness. Cite store.page_url and include disclosure. Show go_url as an affiliate link without fetching or activating it.",
    inputSchema: z.strictObject({
      store: term.describe("Exact store slug, name, or domain."),
      program: term.optional().describe("Program, portal ID or name. Exact matches come first, then whole words or aliases like Delta. Use unit for cash, points, or miles."),
      unit: unit.optional(),
      include_stale: z.boolean().default(true).describe("Include stale rows labeled as stale."),
    }),
    outputSchema: ratesOutput,
    annotations,
  }, ({ store, program, unit, include_stale }) => runTool(async () => {
    const value = normalizeIdentity(store);
    const lookup = await loadStore(client, value);
    if (lookup.search) {
      return result(
        { ...lookup.search, needs_disambiguation: true, comparison_rules: comparisonRules },
        disambiguationText(lookup.search.candidates),
      );
    }

    const { data, ...metadata } = lookup.response;
    const match = program ? filterProgram(data.rates, program) : { rows: data.rates, fields: {} };
    const rows = match.rows.filter((row) => (include_stale || !row.is_stale) && (!unit || row.rate_unit === unit));
    const groups = groupRates(rows, compareWithinUnit);
    const details = [
      `${data.merchant.name} ${data.merchant.page_url}`,
      rows.length ? `Tracked listings by unit - ${groupSummary(groups)}.`
        : "No tracked rate rows match this selection.",
    ];
    if (match.fields.program_match === "none") details.push("See available_programs for programs tracked at this store.");
    if (match.fields.program_hint) details.push(match.fields.program_hint);
    if (match.fields.program_candidates) {
      details.push(...match.fields.program_candidates.map((row) => `${row.portal_name} (${row.program}, ${row.portal_id})`));
    }
    const summaries: string[] = [];
    for (const group of Object.values(groups)) {
      const entries = group.rows.slice(0, program ? 3 : 1).map((row) =>
        `${group.unit_label} - ${formatStoreRate(row)}`
      );
      summaries.push(entries[0]!);
      details.push(...entries);
    }

    return result({
      ...metadata,
      ...match.fields,
      query: value,
      store: data.merchant,
      ...(summaries.length ? { summary: summaries.join("\n") } : {}),
      rates_by_unit: groups,
      comparison_rules: comparisonRules,
    }, details.join("\n"));
  }));

  server.registerTool("list_portals", {
    description: "List tracked shopping portals by category with their program, last_success_at and data_status. Inactive or never-succeeded portals should not count as active coverage. Cite each portal's page_url.",
    inputSchema: z.strictObject({ category: term.optional().describe("Category ID or label, such as airline or Cashback.") }),
    outputSchema: z.object({
      ...resultMetadata,
      portals: z.array(directoryEntry),
      count: z.number().int(),
      active_count: z.number().int(),
    }),
    annotations,
  }, ({ category }) => runTool(async () => {
    const { data, ...metadata } = await client.portals();
    const value = category && normalizeIdentity(category);
    const portals = data.portals
      .filter((row) => !value || [row.category, row.category_label].some((label) => normalizeIdentity(label) === value))
      .map((row) => ({ ...row, data_status: portalStatusFor(row) }));
    const count = portals.length;
    const active_count = portals.filter((row) => row.data_status === "active").length;
    return result({ ...metadata, portals, count, active_count },
      `${count} tracked portals${category ? ` in ${category}` : ""}, ${active_count} active with a recorded check.`);
  }));

  server.registerTool("get_portal", {
    description: "Look up a shopping portal by exact ID or name and show its top tracked rows grouped by native unit and kind. last_success_at describes the portal, not individual rows. Check is_stale, keep up to rates as ceilings, and cite page_url with the disclosure.",
    inputSchema: z.strictObject({ portal: term }),
    outputSchema: z.object({
      ...comparisonFields,
      portal: directoryEntry,
      top_rates_by_unit: unitGroups(portalRate),
    }),
    annotations,
  }, ({ portal }) => runTool(async () => {
    const value = normalizeIdentity(portal);
    const directory = (await client.portals()).data.portals;
    const names = directory.filter((row) => normalizeIdentity(row.name) === value);
    const entry = directory.find((row) => normalizeIdentity(row.portal_id) === value) ??
      (names.length === 1 ? names[0] : undefined);
    if (!entry) {
      if (names.length > 1) throw new CbysError("Several portals share that name. Use a portal ID from list_portals.");
      throw new CbysError(`No tracked portal with that ID or name ("${portal}"). Try list_portals.`, 404);
    }
    let response;
    try {
      response = await client.portal(entry.portal_id);
    } catch (error) {
      if (error instanceof CbysError && error.status === 404) {
        throw new CbysError(`No portal profile found for "${entry.portal_id}". Try list_portals.`, 404);
      }
      throw error;
    }
    const { data, ...metadata } = response;
    const profile = {
      ...data.portal,
      is_active: entry.is_active,
      payout_kind: entry.payout_kind,
      data_status: portalStatusFor({ ...entry, last_success_at: data.portal.last_success_at }),
    };
    const rows = data.top_rates.filter((row) => row.rate_value !== 0).map((row) => ({
      ...row, last_confirmed_at: row.last_confirmed_at ?? null,
    }));
    const groups = groupRates(rows, compareWithinUnit);
    return result({
      ...metadata, portal: profile, top_rates_by_unit: groups, comparison_rules: comparisonRules,
    }, [
      `${profile.name} (${profile.program}) ${profile.page_url}`,
      profile.last_success_at ? `Last successful check for this portal ${profile.last_success_at}.` : "No successful check recorded.",
      !profile.is_active ? "This portal is inactive." : "",
      rows.length ? `Top tracked listings by unit - ${groupSummary(groups)}.` : "No top rate rows were returned.",
      rows.some((row) => row.last_confirmed_at === null) ? "Some rows have no individual confirmation timestamp." : "",
    ].filter(Boolean).join("\n"));
  }));

  server.registerTool("get_highs", {
    description: "Find listings at or near tracked highs, grouped by native unit. Keep one-time bonuses separate from earn rates. At equal values within a unit, unconditional rows precede up to rows before the limit is applied. The feed may omit row freshness or up to status. Use get_store_rates to check before quoting a rate as current. Cite each page_url and include disclosure.",
    inputSchema: z.strictObject({
      unit: unit.optional(),
      kind: kind.optional(),
      limit: z.number().int().min(1).max(100).default(20).describe(
        "Maximum total rows, sampled across units without ranking units (default 20).",
      ),
    }),
    outputSchema: z.object({
      ...comparisonFields,
      count: z.number().int(),
      matching_count: z.number().int(),
      highs_by_unit: unitGroups(high),
    }),
    annotations,
  }, ({ unit, kind, limit }) => runTool(async () => {
    const { data, ...metadata } = await client.highs();
    const rows = data.highs.filter((row) =>
      (!unit || row.rate_unit === unit) && (!kind || row.rate_kind === kind)
    ).map((row) => ({
      ...row,
      is_up_to: row.is_up_to ?? null,
      is_stale: row.is_stale ?? null,
      last_confirmed_at: row.last_confirmed_at ?? null,
    }));
    const grouped = groupRates(rows);
    for (const group of Object.values(grouped)) preferUnconditionalHighs(group.rows);
    const groups = limitHighs(grouped, limit);
    const count = Object.values(groups).reduce((total, group) => total + group.rows.length, 0);
    return result({
      ...metadata,
      count,
      matching_count: rows.length,
      highs_by_unit: groups,
      comparison_rules: comparisonRules,
    }, count ? `${count} of ${rows.length} matching tracked highs by unit - ${groupSummary(groups)}. Check store rows for freshness and up to status.`
      : "No tracked highs match this selection.");
  }));

  return server;
}
