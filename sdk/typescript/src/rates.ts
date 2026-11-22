import { CbysMixedKindError, CbysMixedUnitError } from './errors.js';
import type { Envelope, RateKind, RateUnit } from './types.js';

export interface ComparableRate {
  rate_unit: string;
  rate_kind: RateKind;
  rate_value: number;
  is_up_to?: boolean;
  is_stale?: boolean;
}

type FreshnessFields = {
  rate_unit?: string;
  is_stale?: boolean;
  last_confirmed_at?: string | null;
};
type ProgramFields = { program: string; portal_id: string; portal_name: string };
type DisplayRate = Pick<ComparableRate, 'rate_unit' | 'rate_kind' | 'is_up_to' | 'is_stale'> & {
  rate_display: string;
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

/** Comparator for rows in the same unit and rate kind. */
export function compareRates(a: ComparableRate, b: ComparableRate): number {
  if (a.rate_unit !== b.rate_unit) {
    throw new CbysMixedUnitError(a.rate_unit, b.rate_unit);
  }
  if (a.rate_kind !== b.rate_kind) {
    throw new CbysMixedKindError(a.rate_kind, b.rate_kind);
  }
  return (
    Number(a.is_stale === true) - Number(b.is_stale === true) ||
    b.rate_value - a.rate_value ||
    Number(a.is_up_to === true) - Number(b.is_up_to === true)
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

export function filterByProgram<T extends ProgramFields>(rates: readonly T[], program: string): T[] {
  const query = program.trim().toLowerCase();
  if (!query) return [];
  return rates.filter((row) => [row.program, row.portal_id, row.portal_name]
    .some((value) => value.toLowerCase().includes(query)));
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

export function formatRate(row: DisplayRate): string {
  const unitPattern = Object.hasOwn(DISPLAY_UNIT, row.rate_unit)
    ? DISPLAY_UNIT[row.rate_unit as RateUnit]
    : null;
  const display = unitPattern?.test(row.rate_display)
    ? row.rate_display
    : `${row.rate_display} (${row.rate_unit})`;
  const qualifier = row.is_up_to ? 'up to ' : '';
  const bonus = row.rate_kind === 'one_time_bonus' ? ' (one-time bonus)' : '';
  const stale = row.is_stale ? ' [stale]' : '';
  return `${qualifier}${display}${bonus}${stale}`;
}

export function attributionFor(envelope: Envelope<unknown>, store: { page_url: string }) {
  return {
    source: envelope.source,
    attribution: envelope.attribution,
    page_url: store.page_url,
    disclosure: envelope.disclosure,
  };
}
