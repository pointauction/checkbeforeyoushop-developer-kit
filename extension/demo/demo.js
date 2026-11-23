'use strict';

(() => {
  const { capturedOn, responses } = globalThis.CbysDemoFixtures;
  const { mount } = globalThis.CbysLookup;

  mount(document.querySelector('#lookup'), {
    snapshot: capturedOn,
    async request(path) {
      if (!Object.hasOwn(responses, path)) {
        const error = new Error('Request not in fixtures');
        error.code = 'NOT_IN_FIXTURES';
        throw error;
      }
      const response = structuredClone(responses[path]);
      return globalThis.__CBYS_DEMO_TEST_TRANSFORM__?.(path, response) ?? response;
    },
  });
})();
