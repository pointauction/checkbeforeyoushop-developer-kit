import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { CbysError, CbysFixtureMissingError } from './errors.js';
import { normalizeLookupKey } from './normalize.js';

export { CbysFixtureMissingError };

/**
 * Replay GET requests from a fixture directory. The explicit directory overrides
 * CBYS_FIXTURES_DIR. A missing capture rejects without a network fallback.
 * @param {string} [dir]
 * @returns {import('./client.js').CbysFetch}
 */
export function createFixtureFetch(dir = process.env.CBYS_FIXTURES_DIR) {
  if (!dir) throw new TypeError('Set CBYS_FIXTURES_DIR or pass a fixture directory');
  const root = resolve(dir);
  const manifestPath = resolve(root, 'manifest.json');
  const prefix = root.endsWith(sep) ? root : root + sep;
  /** @type {Promise<Record<string, { file: string, status: number }>> | undefined} */
  let requests;

  return async (input, init) => {
    const url = new URL(input);
    const query = url.searchParams.get('q') ?? '';
    const key = url.pathname === '/api/v1/search.json'
      ? `${url.pathname}?q=${normalizeLookupKey(query)}`
      : url.pathname;
    if (init?.method && init.method.toUpperCase() !== 'GET') {
      throw new CbysFixtureMissingError(`${init.method} ${key}`);
    }

    requests ??= readRequests(manifestPath);
    const index = await requests;
    if (!Object.hasOwn(index, key)) throw new CbysFixtureMissingError(key);
    const entry = index[key];
    if (typeof entry?.file !== 'string' || !Number.isInteger(entry.status) ||
        entry.status < 200 || entry.status > 599) {
      throw new CbysError(`Invalid fixture manifest entry for ${key}`);
    }

    const file = resolve(root, entry.file);
    if (!file.startsWith(prefix)) throw new CbysError(`Fixture file must be inside the fixture directory for ${key}`);

    let body;
    try {
      body = await readFile(file, { encoding: 'utf8', signal: init?.signal });
    } catch (error) {
      if (error?.code === 'ENOENT') throw new CbysFixtureMissingError(key, { cause: error });
      throw new CbysError(`Could not read fixture for ${key}`, { cause: error });
    }
    return new Response([204, 205, 304].includes(entry.status) ? null : body, {
      status: entry.status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  };
}

/** @param {string} file */
async function readRequests(file) {
  try {
    const { requests } = JSON.parse(await readFile(file, 'utf8'));
    if (!requests || typeof requests !== 'object' || Array.isArray(requests)) {
      throw new TypeError('Expected a requests object');
    }
    return requests;
  } catch (error) {
    throw new CbysError(`Could not read fixture manifest at ${file}`, { cause: error });
  }
}
