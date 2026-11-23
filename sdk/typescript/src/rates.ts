import { CbysAmbiguousProgramError, CbysMixedKindError, CbysMixedUnitError } from './errors.js';
import { normalizeLookupKey } from './normalize.js';
import type { Envelope, PayoutKind, RateKind, RateUnit } from './types.js';

export interface ComparableRate<Unit extends string = string, Kind extends RateKind = RateKind> {
  rate_unit: Unit;
  rate_kind: Kind;
  rate_value: number;
  best_category_value?: number | null;
  is_up_to?: boolean;
  is_stale?: boolean;
}

type FreshnessFields = {
  rate_unit?: string;
  is_stale?: boolean;
  last_confirmed_at?: string | null;
};
type ProgramFields = { program: string; portal_id: string; portal_name: string };
type DisplayRate = Omit<ComparableRate, 'rate_value'> & {
  rate_display: string;
  best_category_label?: string | null;
  payout_kind?: PayoutKind;
};

const DISPLAY_UNIT: Record<RateUnit, RegExp> = {
  pct_cash: /%$/,
  points_per_dollar: / pts?\/\$$/,
  miles_per_dollar: / mi\/\$$/,
  cents_per_gallon: /¢\/gal$/,
  flat_cash: /^\$/,
  flat_points: / pts?$/,
  flat_miles: / miles?$/,
};

/**
 * Compares rows in the same unit and kind. Sorts stale rows last, then higher
 * confirmed category values (or the reported values when absent) first.
 * For equal values, fixed rates come first, then higher advertised ceilings.
 */
export function compareRates<Unit extends string, Kind extends RateKind>(
  a: ComparableRate<Unit, Kind>,
  b: ComparableRate<NoInfer<Unit>, NoInfer<Kind>>,
): number {
  if (a.rate_unit !== b.rate_unit) {
    throw new CbysMixedUnitError(a.rate_unit, b.rate_unit);
  }
  if (a.rate_kind !== b.rate_kind) {
    throw new CbysMixedKindError(a.rate_kind, b.rate_kind);
  }
  return (
    Number(a.is_stale === true) - Number(b.is_stale === true) ||
    (b.best_category_value ?? b.rate_value) - (a.best_category_value ?? a.rate_value) ||
    Number(a.is_up_to === true) - Number(b.is_up_to === true) ||
    b.rate_value - a.rate_value
  );
}

/** Retains each row's original metadata and the first-seen order of the units. */
export function groupRatesByUnit<T extends ComparableRate>(rates: readonly T[]): Map<T['rate_unit'], T[]> {
  const groups = new Map<T['rate_unit'], T[]>();
  for (const row of rates) {
    const group = groups.get(row.rate_unit);
    if (group) group.push(row);
    else groups.set(row.rate_unit, [row]);
  }
  for (const group of groups.values()) group.sort(compareRates);
  return groups;
}

/** Returns the leading row per unit, omitting units whose rows are all stale. */
export function bestPerUnit<T extends ComparableRate>(rates: readonly T[]): Map<T['rate_unit'], T> {
  const best = new Map<T['rate_unit'], T>();
  for (const [unit, [leader]] of groupRatesByUnit(rates)) {
    if (leader && !leader.is_stale) best.set(unit, leader);
  }
  return best;
}

const CURRENCY_TERMS = new Set(['mile', 'miles', 'airline miles', 'point', 'points', 'cash', 'cashback', 'cash back']);

const PROGRAM_ALIASES = new Map([
  ['aa', 'aa-eshopping'],
  ['american', 'aa-eshopping'],
  ['american airlines', 'aa-eshopping'],
  ['aadvantage', 'aa-eshopping'],
  ['delta', 'delta-skymiles'],
  ['united', 'united-mileageplus'],
  ['mileageplus', 'united-mileageplus'],
]);

function programTokens(value: string): string {
  return value.match(/[\p{L}\p{M}\p{N}]+/gu)?.join(' ') ?? '';
}

/**
 * Finds exact program, portal ID, or portal name matches in that order.
 * Falls back to known aliases and contiguous whole tokens.
 * @throws {CbysAmbiguousProgramError} For a generic currency query.
 */
export function filterByProgram<T extends ProgramFields>(rates: readonly T[], program: string): T[] {
  const query = normalizeLookupKey(program);
  const tokens = programTokens(query);
  if (!tokens) return [];
  if (CURRENCY_TERMS.has(tokens)) throw new CbysAmbiguousProgramError(query);

  const fields = ['program', 'portal_id', 'portal_name'] as const;
  for (const field of fields) {
    const matches = rates.filter((row) => normalizeLookupKey(row[field]) === query);
    if (matches.length) return matches;
  }

  const portalId = PROGRAM_ALIASES.get(tokens);
  if (portalId) return rates.filter((row) => normalizeLookupKey(row.portal_id) === portalId);

  const phrase = ` ${tokens} `;
  return rates.filter((row) => fields.some((field) => ` ${programTokens(normalizeLookupKey(row[field]))} `.includes(phrase)));
}

export interface RateFreshness {
  isStale: boolean | null;
  lastConfirmedAt: string | null;
  ageHours: number | null;
}

export function freshness(row: FreshnessFields, now: Date | number = Date.now()): RateFreshness {
  const lastConfirmedAt = row.last_confirmed_at ?? null;
  const ageMs = Number(now) - Date.parse(lastConfirmedAt ?? '');
  return {
    isStale: row.is_stale ?? null,
    lastConfirmedAt,
    ageHours: Number.isFinite(ageMs) ? Math.max(0, ageMs) / 3_600_000 : null,
  };
}

function formatCategoryValue(value: number, unit: string): string {
  switch (unit) {
    case 'pct_cash': return `${value}%`;
    case 'miles_per_dollar': return `${value} mi/$`;
    case 'points_per_dollar': return `${value} ${value === 1 ? 'pt' : 'pts'}/$`;
    case 'cents_per_gallon': return `${value}¢/gal`;
    case 'flat_cash': return `$${value}`;
    case 'flat_points': return `${value.toLocaleString('en-US')} ${value === 1 ? 'pt' : 'pts'}`;
    case 'flat_miles': return `${value.toLocaleString('en-US')} ${value === 1 ? 'mile' : 'miles'}`;
    default: return `${value} (${unit})`;
  }
}

export function formatRate(row: DisplayRate): string {
  const unitPattern = Object.hasOwn(DISPLAY_UNIT, row.rate_unit)
    ? DISPLAY_UNIT[row.rate_unit as RateUnit]
    : null;
  const display = unitPattern?.test(row.rate_display)
    ? row.rate_display
    : `${row.rate_display} (${row.rate_unit})`;
  const qualifier = row.is_up_to ? 'up to ' : '';
  const bonus = row.rate_kind === 'one_time_bonus' ? ' (one-time bonus)' : '';
  const payout = row.payout_kind === 'gift_card' ? ' (gift card payout)' : '';
  const stale = row.is_stale ? ' [stale]' : '';
  const categoryLabel = row.best_category_label?.trim() || 'Confirmed category';
  const category = row.is_up_to && row.best_category_value != null
    ? ` · ${categoryLabel}: ${formatCategoryValue(row.best_category_value, row.rate_unit)}`
    : '';
  return `${qualifier}${display}${category}${bonus}${payout}${stale}`;
}

export function attributionFor(envelope: Envelope<unknown>, store: { page_url: string }) {
  return {
    source: envelope.source,
    attribution: envelope.attribution,
    page_url: store.page_url,
    disclosure: envelope.disclosure,
  };
}
