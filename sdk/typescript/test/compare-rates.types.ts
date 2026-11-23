import { compareRates, type ComparableRate, type StoreRate } from '../src/index.js';

const percent = { rate_unit: 'pct_cash', rate_kind: 'earn_rate', rate_value: 3 } as const satisfies ComparableRate;
const miles = { rate_unit: 'miles_per_dollar', rate_kind: 'earn_rate', rate_value: 2 } as const satisfies ComparableRate;
const bonus = { ...percent, rate_kind: 'one_time_bonus' } as const satisfies ComparableRate;
declare const storeRows: StoreRate[];

compareRates(percent, percent);
storeRows.sort(compareRates);

// @ts-expect-error Different literal units.
compareRates(percent, miles);

// @ts-expect-error Different literal kinds even when the units match.
compareRates(percent, bonus);

compareRates(percent, {
  // @ts-expect-error Inline object literals also preserve the unit constraint.
  rate_unit: 'miles_per_dollar', rate_kind: 'earn_rate', rate_value: 2,
});
