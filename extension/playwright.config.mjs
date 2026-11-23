import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {
    viewport: { width: 380, height: 620 },
    deviceScaleFactor: 2,
    colorScheme: 'light',
  },
});
