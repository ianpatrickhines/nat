/**
 * E2E tests for sidebar rendering on NationBuilder pages
 *
 * Tests:
 * - Sidebar renders on NB pages
 * - Sidebar is collapsible
 * - Keyboard shortcut toggles sidebar
 * - Page context is detected
 */

import { test, expect, waitForSidebar, getSidebarState, toggleSidebarWithKeyboard } from './fixtures';

test.describe('Sidebar rendering', () => {
  test('sidebar renders on NB admin page', async ({ nbPage }) => {
    // Navigate to mock NB page
    await nbPage.goto('http://localhost:3456/admin');

    // Wait for sidebar to inject
    await waitForSidebar(nbPage);

    // Verify sidebar is visible
    const sidebar = nbPage.locator('.nat-sidebar');
    await expect(sidebar).toBeVisible();

    // Verify sidebar is open by default
    const state = await getSidebarState(nbPage);
    expect(state).toBe('open');
  });

  test('sidebar shows correct title and subtitle', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Check title
    const title = nbPage.locator('.nat-sidebar__title');
    await expect(title).toHaveText('Nat');

    // Check subtitle
    const subtitle = nbPage.locator('.nat-sidebar__subtitle');
    await expect(subtitle).toHaveText('NationBuilder Assistant');
  });

  test('sidebar can be collapsed and expanded', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should start open
    let state = await getSidebarState(nbPage);
    expect(state).toBe('open');

    // Click toggle button
    const toggleBtn = nbPage.locator('.nat-sidebar__toggle');
    await toggleBtn.click();

    // Should now be collapsed
    state = await getSidebarState(nbPage);
    expect(state).toBe('collapsed');

    // Click again to expand
    await toggleBtn.click();

    // Should be open again
    state = await getSidebarState(nbPage);
    expect(state).toBe('open');
  });

  test('keyboard shortcut toggles sidebar', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should start open
    let state = await getSidebarState(nbPage);
    expect(state).toBe('open');

    // Press Cmd/Ctrl+K to toggle
    await toggleSidebarWithKeyboard(nbPage);

    // Should now be collapsed
    state = await getSidebarState(nbPage);
    expect(state).toBe('collapsed');

    // Press again to expand
    await toggleSidebarWithKeyboard(nbPage);

    // Should be open again
    state = await getSidebarState(nbPage);
    expect(state).toBe('open');
  });

  test('collapsed sidebar shows icon', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Collapse sidebar
    const toggleBtn = nbPage.locator('.nat-sidebar__toggle');
    await toggleBtn.click();

    // Check collapsed icon is visible
    const collapsedIcon = nbPage.locator('.nat-sidebar__collapsed-icon');
    await expect(collapsedIcon).toBeVisible();

    // Check it shows "N"
    const letter = nbPage.locator('.nat-sidebar__collapsed-letter');
    await expect(letter).toHaveText('N');
  });

  test('sidebar detects person profile context', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin/signups/12345');
    await waitForSidebar(nbPage);

    // Check context is displayed
    const contextLabel = nbPage.locator('.nat-sidebar__context-label');
    await expect(contextLabel).toHaveText('Viewing:');

    const contextValue = nbPage.locator('.nat-sidebar__context-value');
    // Context should show person name from page
    await expect(contextValue).toContainText('John Doe');
  });

  test('sidebar shows footer links', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Check Terms link
    const termsLink = nbPage.locator('.nat-sidebar__footer-link >> text=Terms');
    await expect(termsLink).toBeVisible();
    await expect(termsLink).toHaveAttribute('href', 'https://asknat.ai/terms');

    // Check Privacy link
    const privacyLink = nbPage.locator('.nat-sidebar__footer-link >> text=Privacy');
    await expect(privacyLink).toBeVisible();
    await expect(privacyLink).toHaveAttribute('href', 'https://asknat.ai/privacy');
  });
});

test.describe('Page context detection', () => {
  test('detects dashboard page', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Dashboard doesn't show specific context
    const contextValue = nbPage.locator('.nat-sidebar__context-value');
    // Context may or may not be present on dashboard
    const count = await contextValue.count();
    // Dashboard typically shows "Dashboard" or nothing
    if (count > 0) {
      await expect(contextValue).toContainText(/Dashboard/i);
    }
  });

  test('detects list page context', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin/lists/456');
    await waitForSidebar(nbPage);

    const contextValue = nbPage.locator('.nat-sidebar__context-value');
    // Should detect list context
    await expect(contextValue).toContainText('Volunteers');
  });

  test('detects event page context', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin/sites/testnation/pages/events/789');
    await waitForSidebar(nbPage);

    const contextValue = nbPage.locator('.nat-sidebar__context-value');
    // Should detect event context
    await expect(contextValue).toContainText('Town Hall Meeting');
  });
});
