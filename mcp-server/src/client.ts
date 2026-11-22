import { readFile } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { setTimeout as delay } from "node:timers/promises";
import { z } from "zod";
import {
  attribution, directoryData, highsData, portalData, searchData, storeData,
} from "./schemas.js";

const apiRoot = "/api/v1";
const defaultBaseUrl = "https://checkbeforeyoushop.com";
const requestIntervalMs = 1_500;
const requestTimeoutMs = 10_000;
const manifestSchema = z.object({
  requests: z.record(
    z.string(),
    z.object({ file: z.string(), status: z.number().int().min(100).max(599) }),
  ),
});
const envelope = z.object({ data: z.unknown(), ...attribution });
const merchantPath = (slug: string) => `${apiRoot}/merchants/${encodeURIComponent(slug)}.json`;
const searchKey = (query: string) => `${apiRoot}/search.json?q=${query.trim().toLowerCase()}`;

export class CbysError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

export class CbysClient {
  readonly fixtureMode: boolean;
  private readonly fixturesDir?: string;
  private readonly baseUrl: string;
  private manifest?: Promise<z.infer<typeof manifestSchema>>;
  private pending = Promise.resolve();
  private nextRequestAt = 0;

  constructor(env: NodeJS.ProcessEnv = process.env) {
    this.fixturesDir = env.CBYS_FIXTURES_DIR;
    this.fixtureMode = this.fixturesDir !== undefined;
    this.baseUrl = env.CBYS_BASE_URL ?? defaultBaseUrl;
  }

  search(query: string) {
    const key = searchKey(query);
    const params = new URLSearchParams({ q: query.trim().toLowerCase() });
    return this.get(key, searchData, `${apiRoot}/search.json?${params}`);
  }

  merchant(slug: string) {
    return this.get(merchantPath(slug), storeData);
  }

  portals() {
    return this.get(`${apiRoot}/portals.json`, directoryData);
  }

  portal(id: string) {
    return this.get(`${apiRoot}/portals/${encodeURIComponent(id)}.json`, portalData);
  }

  highs() {
    return this.get(`${apiRoot}/highs.json`, highsData);
  }

  /** Skip speculative slug probes when the capture only recorded the search. */
  async hasMerchantFixture(slug: string) {
    if (!this.fixtureMode) return false;
    return Object.hasOwn((await this.getManifest()).requests, merchantPath(slug));
  }

  async hasSearchFixture(query: string) {
    if (!this.fixtureMode) return false;
    return Object.hasOwn((await this.getManifest()).requests, searchKey(query));
  }

  private getManifest() {
    return this.manifest ??= this.readManifest();
  }

  private async readManifest() {
    try {
      if (!this.fixturesDir) throw new Error();
      const body: unknown = JSON.parse(await readFile(resolve(this.fixturesDir, "manifest.json"), "utf8"));
      return manifestSchema.parse(body);
    } catch {
      throw new CbysError("Could not read the fixture manifest. Check CBYS_FIXTURES_DIR.");
    }
  }

  private async readFixture(key: string): Promise<unknown> {
    const { requests } = await this.getManifest();
    const entry = Object.hasOwn(requests, key) ? requests[key] : undefined;
    if (!entry) throw new CbysError(`${key} not in fixtures.`);
    if (entry.status < 200 || entry.status >= 300) {
      throw new CbysError(`CheckBeforeYouShop API returned HTTP ${entry.status}.`, entry.status);
    }
    const root = resolve(this.fixturesDir!);
    const file = resolve(root, entry.file);
    const path = relative(root, file);
    if (isAbsolute(path) || path === ".." || path.startsWith("../") || path.startsWith("..\\")) {
      throw new CbysError("A fixture file points outside CBYS_FIXTURES_DIR.");
    }
    try {
      return JSON.parse(await readFile(file, "utf8")) as unknown;
    } catch {
      throw new CbysError("Could not read the recorded fixture response.");
    }
  }

  private async fetchJson(path: string): Promise<unknown> {
    let url: URL;
    try {
      const base = new URL(this.baseUrl);
      if (!["http:", "https:"].includes(base.protocol) || base.username || base.password) {
        throw new Error();
      }
      url = new URL(path, base);
    } catch {
      throw new CbysError("CBYS_BASE_URL must be an HTTP(S) URL without credentials.");
    }

    const wait = this.nextRequestAt - performance.now();
    if (wait > 0) await delay(Math.ceil(wait));
    this.nextRequestAt = performance.now() + requestIntervalMs;

    try {
      const response = await fetch(url, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "User-Agent": "cbys-developer-kit-mcp/0.1",
        },
        redirect: "error",
        signal: AbortSignal.timeout(requestTimeoutMs),
      });
      if (!response.ok) {
        await response.body?.cancel();
        throw new CbysError(`CheckBeforeYouShop API returned HTTP ${response.status}.`, response.status);
      }
      return await response.json();
    } catch (error) {
      if (error instanceof CbysError) throw error;
      if (error instanceof SyntaxError) {
        throw new CbysError("The CheckBeforeYouShop API returned invalid JSON.");
      }
      throw new CbysError("Could not reach or read the CheckBeforeYouShop API. Try again shortly.");
    }
  }

  private async get<T extends z.ZodType>(key: string, schema: T, path = key) {
    let body: unknown;
    if (this.fixtureMode) {
      body = await this.readFixture(key);
    } else {
      const request = this.pending.then(() => this.fetchJson(path));
      this.pending = request.then(() => undefined, () => undefined);
      body = await request;
    }

    const parsed = envelope.safeParse(body);
    if (parsed.success) {
      const { data, ...metadata } = parsed.data;
      const validated = schema.safeParse(data);
      if (validated.success) {
        return { data: validated.data, ...metadata, fixture_mode: this.fixtureMode };
      }
    }
    throw new CbysError("The CheckBeforeYouShop API returned an unexpected response format.");
  }
}
