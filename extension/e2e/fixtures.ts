/**
 * Playwright test fixtures for Chrome extension testing
 *
 * Provides:
 * - Persistent browser context with extension loaded
 * - Helper functions for extension interaction
 * - Mock chrome.storage setup
 */

import { test as base, chromium, BrowserContext, Page } from '@playwright/test';
import path from 'path';

// Extended test fixtures
export interface ExtensionFixtures {
  context: BrowserContext;
  extensionId: string;
  nbPage: Page;
}

// Helper to get extension ID from service worker URL
async function getExtensionId(context: BrowserContext): Promise<string> {
  // Wait for service worker to register
  let serviceWorker = context.serviceWorkers()[0];

  if (!serviceWorker) {
    // Wait for service worker to appear
    serviceWorker = await context.waitForEvent('serviceworker');
  }

  const extensionId = serviceWorker.url().split('/')[2];
  return extensionId;
}

// Base test with extension fixtures
export const test = base.extend<ExtensionFixtures>({
  // Override context to use persistent context with extension
  context: async ({}, use) => {
    const pathToExtension = path.join(__dirname, '..', 'dist');

    const context = await chromium.launchPersistentContext('', {
      headless: false, // Extensions require headed mode
      args: [
        `--disable-extensions-except=${pathToExtension}`,
        `--load-extension=${pathToExtension}`,
        '--no-sandbox',
      ],
    });

    await use(context);
    await context.close();
  },

  // Get extension ID
  extensionId: async ({ context }, use) => {
    const id = await getExtensionId(context);
    await use(id);
  },

  // Create a page that simulates a NationBuilder page
  nbPage: async ({ context }, use) => {
    const page = await context.newPage();

    // Set up mock chrome.storage before navigating
    // This injects the mock auth state into the extension's storage
    await page.addInitScript(() => {
      // Mock auth state for tests
      (window as unknown as { __TEST_AUTH_STATE__: unknown }).__TEST_AUTH_STATE__ = {
        isAuthenticated: true,
        userId: 'test-user-123',
        tenantId: 'test-tenant-456',
        nbConnected: true,
        nbNeedsReauth: false,
        subscriptionStatus: 'active',
      };
    });

    await use(page);
    await page.close();
  },
});

export { expect } from '@playwright/test';

/**
 * Helper to set auth state in extension storage
 * Call this before tests that need specific auth states
 */
export async function setAuthState(
  context: BrowserContext,
  extensionId: string,
  authState: {
    isAuthenticated: boolean;
    userId?: string | null;
    tenantId?: string | null;
    nbConnected?: boolean;
    nbNeedsReauth?: boolean;
    subscriptionStatus?: 'active' | 'trialing' | 'cancelled' | 'past_due' | 'unpaid' | null;
  }
): Promise<void> {
  // Access extension's background page to set storage
  const backgroundPage = await getBackgroundPage(context, extensionId);

  await backgroundPage.evaluate(async (state) => {
    await chrome.storage.local.set({ authState: state });
    // Also send message to notify any listeners
    chrome.runtime.sendMessage({ type: 'AUTH_STATE_CHANGED', authState: state });
  }, authState);
}

/**
 * Helper to set tutorial completion state
 */
export async function setTutorialCompleted(
  context: BrowserContext,
  extensionId: string,
  completed: boolean
): Promise<void> {
  const backgroundPage = await getBackgroundPage(context, extensionId);

  await backgroundPage.evaluate(async (isCompleted) => {
    if (isCompleted) {
      await chrome.storage.local.set({ nat_tutorial_completed: true });
    } else {
      await chrome.storage.local.remove('nat_tutorial_completed');
    }
  }, completed);
}

/**
 * Get the extension's background service worker page
 */
async function getBackgroundPage(context: BrowserContext, extensionId: string): Promise<Page> {
  const backgroundPages = context.backgroundPages();

  // For MV3 extensions, we need to use service workers
  let backgroundPage = backgroundPages.find(
    (p) => p.url().includes(extensionId)
  );

  if (!backgroundPage) {
    // Create a page to access the extension's service worker
    backgroundPage = await context.newPage();
    await backgroundPage.goto(`chrome-extension://${extensionId}/background.js`);
  }

  return backgroundPage;
}

/**
 * Helper to wait for sidebar to appear on page
 */
export async function waitForSidebar(page: Page): Promise<void> {
  await page.waitForSelector('.nat-sidebar', { timeout: 10000 });
}

/**
 * Helper to check if sidebar is visible
 */
export async function isSidebarVisible(page: Page): Promise<boolean> {
  const sidebar = page.locator('.nat-sidebar');
  return sidebar.isVisible();
}

/**
 * Helper to get sidebar state (open/collapsed)
 */
export async function getSidebarState(page: Page): Promise<'open' | 'collapsed' | 'hidden'> {
  const sidebar = page.locator('.nat-sidebar');

  if (!(await sidebar.isVisible())) {
    return 'hidden';
  }

  const hasOpenClass = await sidebar.evaluate((el) =>
    el.classList.contains('nat-sidebar--open')
  );

  return hasOpenClass ? 'open' : 'collapsed';
}

/**
 * Helper to toggle sidebar via keyboard shortcut
 */
export async function toggleSidebarWithKeyboard(page: Page): Promise<void> {
  const isMac = process.platform === 'darwin';
  const modifier = isMac ? 'Meta' : 'Control';
  await page.keyboard.press(`${modifier}+k`);
}

/**
 * Helper to send a chat message
 */
export async function sendChatMessage(page: Page, message: string): Promise<void> {
  const input = page.locator('.nat-chat__input');
  await input.fill(message);

  const sendButton = page.locator('.nat-chat__send-btn');
  await sendButton.click();
}

/**
 * Helper to wait for chat response
 */
export async function waitForChatResponse(page: Page, timeout = 10000): Promise<string> {
  // Wait for the last assistant message
  const messages = page.locator('.nat-chat__message--assistant');
  await messages.last().waitFor({ timeout });

  // Get the content of the last message
  const content = await messages.last().locator('.nat-chat__message-content').textContent();
  return content || '';
}
