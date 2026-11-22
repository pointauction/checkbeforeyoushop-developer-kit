import {
  CbysBadRequestError,
  CbysError,
  CbysFixtureMissingError,
  CbysHttpError,
  CbysNetworkError,
  CbysNotFoundError,
  CbysTimeoutError,
} from './errors.js';
import type {
  Envelope,
  HighsData,
  MerchantHit,
  PortalData,
  PortalsData,
  ResolveStoreResult,
  SearchData,
  StoreData,
} from './types.js';

export type CbysFetch = (url: string, init?: RequestInit) => Promise<Response>;

export interface CbysClientOptions {
  baseUrl?: string | URL;
  fetch?: CbysFetch;
  /** Per-attempt timeout, including the response body. Defaults to 10,000 ms. */
  timeoutMs?: number;
  userAgent?: string;
  /** Retries after the initial attempt. Defaults to 2. */
  retries?: number;
}

const MAX_TIMER_MS = 2_147_483_647;
const DEFAULT_ORIGIN = 'https://checkbeforeyoushop.com';
const API_PATH = '/api/v1';

export class CbysClient {
  readonly #baseUrl: string;
  readonly #fetch: CbysFetch;
  readonly #timeoutMs: number;
  readonly #userAgent: string | undefined;
  readonly #retries: number;

  constructor(options: CbysClientOptions = {}) {
    const baseUrl = new URL(options.baseUrl ?? DEFAULT_ORIGIN);
    if (!['http:', 'https:'].includes(baseUrl.protocol) ||
        baseUrl.username || baseUrl.password || baseUrl.search || baseUrl.hash) {
      throw new TypeError('baseUrl must be an HTTP(S) URL without credentials, a query or a fragment');
    }

    this.#baseUrl = baseUrl.href.replace(/\/+$/, '');
    this.#fetch = (options.fetch ?? globalThis.fetch).bind(globalThis);
    this.#timeoutMs = options.timeoutMs ?? 10_000;
    this.#userAgent = options.userAgent;
    this.#retries = options.retries ?? 2;

    if (!Number.isInteger(this.#timeoutMs) || this.#timeoutMs < 1 || this.#timeoutMs > MAX_TIMER_MS) {
      throw new RangeError(`timeoutMs must be an integer between 1 and ${MAX_TIMER_MS}`);
    }
    if (!Number.isSafeInteger(this.#retries) || this.#retries < 0) {
      throw new RangeError('retries must be a non-negative safe integer');
    }
  }

  async search(q: string): Promise<Envelope<SearchData>> {
    const query = q.trim();
    const url = this.#url('/search.json');
    url.searchParams.set('q', query);
    if (query.length < 2) {
      throw new CbysBadRequestError('q must be at least 2 characters', url.href);
    }
    return this.#get(url);
  }

  async getStore(slug: string): Promise<Envelope<StoreData>> {
    return this.#get(this.#resourceUrl('merchants', slug));
  }

  async listPortals(): Promise<Envelope<PortalsData>> {
    return this.#get(this.#url('/portals.json'));
  }

  async getPortal(id: string): Promise<Envelope<PortalData>> {
    return this.#get(this.#resourceUrl('portals', id));
  }

  async getHighs(): Promise<Envelope<HighsData>> {
    return this.#get(this.#url('/highs.json'));
  }

  async resolveStore(query: string): Promise<ResolveStoreResult> {
    const key = query.trim().toLowerCase();
    let search: Envelope<SearchData>;
    try {
      search = await this.search(query);
    } catch (error) {
      // Offline snapshots may contain the exact merchant detail without a search capture.
      if (error instanceof CbysFixtureMissingError) {
        const store = await this.#probeSlug(key);
        if (store) return { status: 'found', store, matchedBy: 'slug', portalHits: [] };
      }
      throw error;
    }

    const results = search.data.results;
    const merchants = results.filter((hit) => hit.kind === 'merchant');
    const portalHits = results.filter((hit) => hit.kind === 'portal');

    // The search endpoint ranks names and domains, and may omit a valid slug.
    const slugMatch = merchants.find((hit) => hit.slug.toLowerCase() === key) ?? await this.#probeSlug(key);
    if (slugMatch) return { status: 'found', store: slugMatch, matchedBy: 'slug', portalHits };

    const names = merchants.filter((hit) => hit.name.toLowerCase() === key);
    const exact = names.length ? names : merchants.filter((hit) => hit.domain?.toLowerCase() === key);
    const [first] = exact;
    if (exact.length === 1 && first) {
      return { status: 'found', store: first, matchedBy: names.length ? 'name' : 'domain', portalHits };
    }

    const candidates = exact.length ? exact : merchants.filter((hit) => !hit.did_you_mean);
    if (candidates.length) return { status: 'ambiguous', candidates, portalHits };
    return { status: 'not_found', suggestions: merchants.filter((hit) => hit.did_you_mean), portalHits };
  }

  async #probeSlug(slug: string): Promise<MerchantHit | undefined> {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) return undefined;
    try {
      const { data: { merchant } } = await this.getStore(slug);
      if (merchant.slug.toLowerCase() !== slug) return undefined;
      return {
        kind: 'merchant',
        slug: merchant.slug,
        name: merchant.name,
        domain: merchant.domain,
        page_url: merchant.page_url,
        did_you_mean: false,
      };
    } catch (error) {
      // A successful search can still be used when an optional fixture probe is absent.
      if (error instanceof CbysNotFoundError || error instanceof CbysFixtureMissingError) {
        return undefined;
      }
      throw error;
    }
  }

  #url(path: string): URL {
    return new URL(`${this.#baseUrl}${API_PATH}${path}`);
  }

  #resourceUrl(resource: 'merchants' | 'portals', id: string): URL {
    const key = id.trim();
    const url = this.#url(`/${resource}/${encodeURIComponent(key)}.json`);
    if (!key) throw new CbysBadRequestError(`Missing ${resource === 'merchants' ? 'merchant slug' : 'portal id'}`, url.href);
    return url;
  }

  async #get<T>(url: URL): Promise<Envelope<T>> {
    for (let attempt = 0; ; attempt++) {
      const canRetry = attempt < this.#retries;
      let result: Download;
      try {
        result = await this.#attempt(url.href, canRetry);
      } catch (error) {
        if (!canRetry || !(error instanceof CbysNetworkError)) throw error;
        await wait(backoffMs(attempt));
        continue;
      }

      const { response, body } = result;
      if (canRetry && isRetryStatus(response.status)) {
        await wait(Math.max(backoffMs(attempt), retryAfterMs(response.headers.get('Retry-After'))));
        continue;
      }

      const payload = parseResponse(response, body, url.href);
      if (!isEnvelope<T>(payload)) {
        throw new CbysHttpError(response.status, 'Invalid API response envelope', url.href);
      }
      return payload;
    }
  }

  async #attempt(url: string, canRetry: boolean): Promise<Download> {
    const controller = new AbortController();
    const headers = new Headers({ Accept: 'application/json' });
    if (this.#userAgent) headers.set('User-Agent', this.#userAgent);

    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        const error = new CbysTimeoutError(url, this.#timeoutMs);
        reject(error);
        controller.abort(error);
      }, this.#timeoutMs);
    });

    try {
      return await Promise.race([
        deadline,
        this.#download(url, { method: 'GET', headers, signal: controller.signal, redirect: 'manual' }, canRetry),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }

  async #download(url: string, init: RequestInit, canRetry: boolean): Promise<Download> {
    let response: Response;
    try {
      response = await this.#fetch(url, init);
    } catch (error) {
      if (error instanceof CbysError) throw error;
      throw new CbysNetworkError(url, error);
    }

    if (canRetry && isRetryStatus(response.status)) {
      void response.body?.cancel().catch(() => {});
      return { response, body: '' };
    }

    try {
      return { response, body: await response.text() };
    } catch (error) {
      if (!response.ok) return { response, body: '' };
      throw new CbysNetworkError(url, error);
    }
  }
}

type Download = { response: Response; body: string };

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isEnvelope<T>(value: unknown): value is Envelope<T> {
  return isObject(value) && isObject(value.data) &&
    (value.data_as_of === null || typeof value.data_as_of === 'string') &&
    typeof value.source === 'string' &&
    typeof value.attribution === 'string' &&
    typeof value.disclosure === 'string';
}

function parseResponse(response: Response, body: string, url: string): unknown {
  let payload: unknown;
  try {
    payload = JSON.parse(body);
  } catch (error) {
    if (response.ok) {
      throw new CbysHttpError(response.status, 'Invalid JSON in API response', url, { cause: error });
    }
  }

  if (response.ok) return payload;

  const message = isObject(payload) && typeof payload.error === 'string'
    ? payload.error
    : `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ''}`;
  if (response.status === 400) throw new CbysBadRequestError(message, url);
  if (response.status === 404) throw new CbysNotFoundError(message, url);
  throw new CbysHttpError(response.status, message, url);
}

function isRetryStatus(status: number): boolean {
  return status === 429 || (status >= 500 && status < 600);
}

function backoffMs(attempt: number): number {
  const window = Math.min(250 * 2 ** attempt, 5_000);
  return window * (0.5 + 0.5 * Math.random());
}

function retryAfterMs(value: string | null): number {
  if (value === null) return 0;
  if (/^\d+$/.test(value)) {
    const ms = Number(value) * 1_000;
    return Number.isSafeInteger(ms) ? ms : 0;
  }
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.max(0, date - Date.now()) : 0;
}

async function wait(ms: number): Promise<void> {
  // Timers above the runtime limit otherwise fire nearly immediately.
  while (ms > MAX_TIMER_MS) {
    await new Promise((resolve) => setTimeout(resolve, MAX_TIMER_MS));
    ms -= MAX_TIMER_MS;
  }
  await new Promise((resolve) => setTimeout(resolve, ms));
}
