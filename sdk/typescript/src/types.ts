export interface Envelope<T> {
  data: T;
  /** Newest confirmation the endpoint reports, when available. */
  data_as_of: string | null;
  source: string;
  attribution: string;
  disclosure: string;
}

interface SearchHitBase {
  slug: string;
  name: string;
  did_you_mean: boolean;
  page_url: string;
}

export interface MerchantHit extends SearchHitBase {
  kind: 'merchant';
  domain: string | null;
}

export interface PortalHit extends SearchHitBase {
  kind: 'portal';
  domain: null;
}

export type SearchHit = MerchantHit | PortalHit;

export interface SearchData {
  query: string;
  count: number;
  results: SearchHit[];
  did_you_mean: boolean;
}

export type ResolveStoreResult = { portalHits: PortalHit[] } & (
  | { status: 'found'; store: MerchantHit; matchedBy: 'slug' | 'name' | 'domain' }
  | { status: 'ambiguous'; candidates: MerchantHit[] }
  | { status: 'not_found'; suggestions: MerchantHit[] }
);

export type RateUnit =
  | 'pct_cash'
  | 'points_per_dollar'
  | 'miles_per_dollar'
  | 'cents_per_gallon'
  | 'flat_cash'
  | 'flat_points'
  | 'flat_miles';

export type RateKind = 'earn_rate' | 'one_time_bonus';
export type UnitGroup = 'Cashback' | 'Points' | 'Airline miles' | 'Other';
export type PayoutKind = 'gift_card' | null;
export type PortalCategory = 'cashback' | 'airline' | 'card' | 'points' | 'giftcard';

export interface RateValue {
  rate_value: number;
  rate_unit: RateUnit;
  rate_kind: RateKind;
  rate_display: string;
  unit_group: UnitGroup;
}

interface PortalProgram {
  portal_id: string;
  portal_name: string;
  program: string;
  payout_kind: PayoutKind;
}

interface RateFlags {
  is_up_to: boolean;
  is_elevated: boolean;
  is_stale: boolean;
}

export interface BestStoreRate extends RateValue, PortalProgram, RateFlags {
  best_category_value: number | null;
  best_category_label: string | null;
  last_confirmed_at: string;
  go_url: string | null;
}

export interface StoreRate extends BestStoreRate {
  listing_label: string | null;
}

export interface Store {
  slug: string;
  name: string;
  domain: string | null;
  page_url: string;
  portals_tracked: number;
  tracked_since: string | null;
}

export interface Verdict {
  /** Upstream prose that can single out one program across units. */
  headline: string;
  tone: 'ath' | 'high' | 'good' | 'typical' | 'low' | 'young';
  /** Keep these qualifications with the headline when displaying the verdict. */
  caveats: string[];
}

export interface StoreData {
  merchant: Store;
  /** Upstream prose that can single out one program across units. Use per-unit rows for comparisons. */
  summary: string;
  /**
   * Upstream prose that can single out one program across units.
   * Use per-unit rows for comparisons and preserve all verdict.caveats when displaying it.
   */
  verdict: Verdict | null;
  /** The API's per-unit leaders. */
  best_rates: BestStoreRate[];
  rates: StoreRate[];
}

export interface PortalProfile {
  portal_id: string;
  name: string;
  program: string;
  payout_kind?: PayoutKind;
  category: PortalCategory;
  category_label: string;
  merchants_tracked: number;
  cadence_hours: number;
  last_success_at: string | null;
  page_url: string;
}

export interface PortalDirectoryEntry extends PortalProfile {
  payout_kind: PayoutKind;
  is_active: boolean;
}

export interface PortalsData {
  count: number;
  active_count: number;
  portals: PortalDirectoryEntry[];
}

interface StoreLink {
  merchant_slug: string;
  merchant_name: string;
  page_url: string;
}

export interface PortalRate extends RateValue, StoreLink, RateFlags {}

export interface PortalData {
  portal: PortalProfile;
  top_rates: PortalRate[];
}

export interface HighRate extends RateValue, StoreLink, PortalProgram {
  is_all_time_high: boolean;
  typical_range: string | null;
}

export interface HighsData {
  count: number;
  highs: HighRate[];
}
