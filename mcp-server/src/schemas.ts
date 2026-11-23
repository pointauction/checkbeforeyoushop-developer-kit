import { z } from "zod";

export function normalizeIdentity(value: string) {
  return value.trim().normalize("NFC").toLowerCase().normalize("NFC");
}

export const query = z.string().trim().min(2).max(256);
export const term = z.string().trim().min(1).max(256);
export const unit = z.string().regex(/^[a-z][a-z0-9_]*$/).max(64).describe(
  "Exact rate_unit, such as pct_cash, miles_per_dollar, points_per_dollar, or flat_cash.",
);
export const kind = z.enum(["earn_rate", "one_time_bonus"]);

const timestamp = z.string().nullable();
const pageUrl = z.string().url();
export const attribution = {
  data_as_of: timestamp.describe("Endpoint-level timestamp. Check each rate row for its own confirmation time."),
  source: z.string(),
  attribution: z.string(),
  disclosure: z.string(),
};
export const resultMetadata = {
  ...attribution,
  fixture_mode: z.boolean().describe("When true, this is a historical fixture snapshot."),
};

export const candidate = z.object({
  kind: z.enum(["merchant", "portal"]),
  slug: z.string(),
  name: z.string(),
  domain: z.string().nullable(),
  page_url: pageUrl,
  did_you_mean: z.boolean().optional(),
});
export const searchData = z.object({ results: z.array(candidate) });
export const candidates = z.object({
  stores: z.array(candidate),
  portals: z.array(candidate),
});

export const storeProfile = z.object({
  slug: z.string(),
  name: z.string(),
  domain: z.string().nullable(),
  page_url: pageUrl,
  portals_tracked: z.number().int(),
  tracked_since: timestamp,
});
const rate = z.object({
  rate_value: z.number(),
  rate_unit: unit,
  rate_kind: kind,
  rate_display: z.string(),
  unit_group: z.string(),
});
const portalIdentity = {
  portal_id: z.string(),
  portal_name: z.string(),
  program: z.string(),
  payout_kind: z.string().nullable(),
};
const merchantIdentity = {
  merchant_slug: z.string(),
  merchant_name: z.string(),
  page_url: pageUrl,
};
export const storeRate = rate.extend({
  ...portalIdentity,
  is_up_to: z.boolean(),
  is_stale: z.boolean(),
  last_confirmed_at: z.string(),
  go_url: pageUrl.nullable().describe("Affiliate link to show the user. Never fetch or activate it."),
  best_category_value: z.number().nullable(),
  best_category_label: z.string().nullable(),
  is_elevated: z.boolean(),
  listing_label: z.string().nullable().optional(),
});
export const storeData = z.object({
  merchant: storeProfile,
  rates: z.array(storeRate),
});

export const portalProfile = z.object({
  portal_id: z.string(),
  name: z.string(),
  program: z.string(),
  category: z.string(),
  category_label: z.string(),
  merchants_tracked: z.number().int(),
  cadence_hours: z.number().int(),
  last_success_at: timestamp,
  page_url: pageUrl,
});
export const directoryPortal = portalProfile.extend({
  payout_kind: z.string().nullable(),
  is_active: z.boolean(),
});
export const directoryData = z.object({ portals: z.array(directoryPortal) });
export const portalStatus = {
  data_status: z.enum(["active", "inactive", "never_succeeded"]),
};

const apiPortalRate = rate.extend({
  ...merchantIdentity,
  is_up_to: z.boolean(),
  is_elevated: z.boolean(),
  is_stale: z.boolean(),
  last_confirmed_at: timestamp.describe("Null when the public API omits row confirmation time.").optional(),
});
export const portalRate = apiPortalRate.required({ last_confirmed_at: true });
export const portalData = z.object({
  portal: portalProfile,
  top_rates: z.array(apiPortalRate),
});

const apiHigh = rate.extend({
  ...merchantIdentity,
  ...portalIdentity,
  is_all_time_high: z.boolean(),
  typical_range: z.string().nullable(),
  is_up_to: z.boolean().nullable().describe("Null when the public API omits up to status.").optional(),
  is_stale: z.boolean().nullable().describe("Null when the public API omits row staleness.").optional(),
  last_confirmed_at: timestamp.describe("Null when the public API omits row confirmation time.").optional(),
});
export const high = apiHigh.required({
  is_up_to: true,
  is_stale: true,
  last_confirmed_at: true,
});
export const highsData = z.object({ highs: z.array(apiHigh) });

export function unitGroups<Row extends z.ZodType>(row: Row) {
  return z.record(unit, z.object({
    unit_label: z.string(),
    rate_kind: kind,
    rows: z.array(row),
  }));
}
