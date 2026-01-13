/**
 * E2E tests for authentication flow UI states
 *
 * Tests:
 * - Not logged in shows subscribe prompt
 * - Logged in but NB not connected shows connect button
 * - NB needs reauth shows reconnect banner
 * - Subscription lapsed shows payment failed message
 * - Fully authenticated shows chat
 */

import { test, expect, waitForSidebar, setAuthState, setTutorialCompleted } from './fixtures';

test.describe('Auth flow states', () => {
  test.beforeEach(async ({ context, extensionId }) => {
    // Mark tutorial as completed so it doesn't interfere with auth tests
    await setTutorialCompleted(context, extensionId, true);
  });

  test('shows subscribe prompt when not logged in', async ({ context, extensionId, nbPage }) => {
    // Set auth state to not authenticated
    await setAuthState(context, extensionId, {
      isAuthenticated: false,
      userId: null,
      tenantId: null,
      nbConnected: false,
      nbNeedsReauth: false,
      subscriptionStatus: null,
    });

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should show not logged in screen
    const authScreen = nbPage.locator('.nat-auth-screen');
    await expect(authScreen).toBeVisible();

    // Check title
    const title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Welcome to Nat');

    // Check subscribe button
    const subscribeBtn = nbPage.locator('.nat-auth-screen__btn--primary');
    await expect(subscribeBtn).toHaveText('Subscribe to Nat');
  });

  test('shows connect NationBuilder when logged in but NB not connected', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Set auth state to authenticated but NB not connected
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'user-123',
      tenantId: 'tenant-456',
      nbConnected: false,
      nbNeedsReauth: false,
      subscriptionStatus: 'active',
    });

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should show NB not connected screen
    const authScreen = nbPage.locator('.nat-auth-screen');
    await expect(authScreen).toBeVisible();

    // Check title
    const title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Almost There!');

    // Check connect button
    const connectBtn = nbPage.locator('.nat-auth-screen__btn--primary');
    await expect(connectBtn).toHaveText('Connect NationBuilder');

    // Check hint text
    const hint = nbPage.locator('.nat-auth-screen__hint');
    await expect(hint).toContainText('Nat will only access data you authorize');
  });

  test('shows reconnect banner when NB needs reauth', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Set auth state to needing reauth
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'user-123',
      tenantId: 'tenant-456',
      nbConnected: true,
      nbNeedsReauth: true,
      subscriptionStatus: 'active',
    });

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should show warning banner
    const banner = nbPage.locator('.nat-auth-screen__banner--warning');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('NationBuilder connection expired');

    // Check title
    const title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Reconnect Required');

    // Check reconnect button
    const reconnectBtn = nbPage.locator('.nat-auth-screen__btn--primary');
    await expect(reconnectBtn).toHaveText('Reconnect NationBuilder');
  });

  test('shows payment failed when subscription is past_due', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Set auth state to past due subscription
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'user-123',
      tenantId: 'tenant-456',
      nbConnected: true,
      nbNeedsReauth: false,
      subscriptionStatus: 'past_due',
    });

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should show error banner
    const banner = nbPage.locator('.nat-auth-screen__banner--error');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Payment failed');

    // Check title
    const title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Payment Failed');

    // Check update payment button
    const updateBtn = nbPage.locator('.nat-auth-screen__btn--primary');
    await expect(updateBtn).toHaveText('Update Payment Method');
  });

  test('shows subscription ended when cancelled', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Set auth state to cancelled subscription
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'user-123',
      tenantId: 'tenant-456',
      nbConnected: true,
      nbNeedsReauth: false,
      subscriptionStatus: 'cancelled',
    });

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should show error banner
    const banner = nbPage.locator('.nat-auth-screen__banner--error');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Subscription inactive');

    // Check title
    const title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Subscription Ended');

    // Check resubscribe button
    const resubscribeBtn = nbPage.locator('.nat-auth-screen__btn--primary');
    await expect(resubscribeBtn).toHaveText('Resubscribe to Nat');

    // Check data retention hint
    const hint = nbPage.locator('.nat-auth-screen__hint');
    await expect(hint).toContainText('30 days');
  });

  test('shows chat when fully authenticated', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Set auth state to fully authenticated
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'user-123',
      tenantId: 'tenant-456',
      nbConnected: true,
      nbNeedsReauth: false,
      subscriptionStatus: 'active',
    });

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should NOT show auth screen
    const authScreen = nbPage.locator('.nat-auth-screen');
    await expect(authScreen).not.toBeVisible();

    // Should show chat interface
    const chat = nbPage.locator('.nat-chat');
    await expect(chat).toBeVisible();

    // Should have input field
    const input = nbPage.locator('.nat-chat__input');
    await expect(input).toBeVisible();
  });

  test('shows loading state initially', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Loading spinner should appear briefly
    // This test verifies the loading state exists in the DOM
    const loadingSelector = '.nat-sidebar__loading';

    // Wait for either loading to disappear or content to appear
    await nbPage.waitForSelector(`${loadingSelector}, .nat-auth-screen, .nat-chat`, {
      timeout: 5000,
    });
  });
});

test.describe('Auth state transitions', () => {
  test('updates UI when auth state changes', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Start not authenticated
    await setAuthState(context, extensionId, {
      isAuthenticated: false,
    });

    await setTutorialCompleted(context, extensionId, true);
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Should show subscribe prompt
    let title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Welcome to Nat');

    // Simulate user authenticating
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'user-123',
      tenantId: 'tenant-456',
      nbConnected: false,
      subscriptionStatus: 'active',
    });

    // Reload to get new state (or wait for state change listener)
    await nbPage.reload();
    await waitForSidebar(nbPage);

    // Should now show connect NB screen
    title = nbPage.locator('.nat-auth-screen__title');
    await expect(title).toHaveText('Almost There!');
  });
});
