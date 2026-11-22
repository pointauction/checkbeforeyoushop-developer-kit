'use strict';

(async () => {
  const { origin, merchantPath, mount } = globalThis.CbysLookup;

  async function request(path, signal) {
    const response = await fetch(origin + path, {
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      redirect: 'error',
      signal,
    });
    return { status: response.status, body: await response.json() };
  }

  const lookup = mount(document.querySelector('#lookup'), {
    request,
    // The search catalog indexes store names and domains. A slug can differ from both.
    async resolveSlug(query, signal) {
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(query)) return null;
      const response = await request(merchantPath(query), signal);
      if (response.status === 404) return null;
      if (response.status !== 200) throw new Error('Merchant lookup failed');
      return response.body;
    },
  });

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url) return;
    const { protocol, hostname } = new URL(tab.url);
    if (['http:', 'https:'].includes(protocol) && hostname.includes('.')) {
      lookup.prefill(hostname);
    }
  } catch {
    // For restricted tabs, manual search is still available.
  }
})();
