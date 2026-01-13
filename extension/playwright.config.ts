import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Playwright configuration for Chrome extension E2E testing.
 *
 * Chrome extensions require a persistent context with --load-extension flag.
 * We use Chromium only (no Firefox/Safari support for MV3 extensions).
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Extensions require serial execution due to shared browser context
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker for extension testing
  reporter: 'html',
  timeout: 30000,

  use: {
    // Base URL for test server (mocked NB pages)
    baseURL: 'http://localhost:3456',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium-extension',
      use: {
        ...devices['Desktop Chrome'],
        // Extension path - built extension in dist directory
        launchOptions: {
          args: [
            `--disable-extensions-except=${path.join(__dirname, 'dist')}`,
            `--load-extension=${path.join(__dirname, 'dist')}`,
          ],
        },
      },
    },
  ],

  // Local mock server for testing
  webServer: {
    command: 'npm run test:server',
    url: 'http://localhost:3456',
    reuseExistingServer: !process.env.CI,
    timeout: 10000,
  },
});
