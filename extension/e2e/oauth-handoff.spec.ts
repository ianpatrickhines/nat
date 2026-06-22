/**
 * E2E tests for the session-token handoff (issue #10).
 *
 * After the NationBuilder OAuth flow, the backend redirects to the success page
 * with the minted session token in the URL fragment. The oauth-callback content
 * script reads it and stores it in chrome.storage via the background worker.
 *
 * These tests route the production success domain (natassistant.com) to the
 * local mock server so the content script (which matches that host) injects.
 */

import { test, expect, getStorageValue } from './fixtures';

const SESSION_TOKEN = 'header.payload.signature';
const USER_ID = 'user-abc';
const NATION_SLUG = 'examplenation';

test.describe('Session token handoff', () => {
  test('stores the session token from the success-page fragment', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    // Route the production success domain to the local mock server so the
    // oauth-callback content script (matched on natassistant.com) injects.
    await nbPage.route('**://natassistant.com/connected*', async (route) => {
      const res = await route.fetch({ url: 'http://localhost:3456/connected' });
      const body = await res.text();
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body,
      });
    });

    // Navigate to the success URL exactly as the backend builds it:
    //   ?user_id=...&nation=...#session_token=<jwt>
    await nbPage.goto(
      `https://natassistant.com/connected?user_id=${USER_ID}&nation=${NATION_SLUG}` +
        `#session_token=${SESSION_TOKEN}`
    );

    // The content script should hand the token to the background worker, which
    // stores it under `authToken` and marks the nation connected.
    await expect
      .poll(() => getStorageValue(context, extensionId, 'authToken'), {
        timeout: 5000,
      })
      .toBe(SESSION_TOKEN);

    expect(await getStorageValue(context, extensionId, 'userId')).toBe(USER_ID);
    expect(await getStorageValue(context, extensionId, 'nationSlug')).toBe(
      NATION_SLUG
    );
    expect(await getStorageValue(context, extensionId, 'nbConnected')).toBe(true);
    expect(await getStorageValue(context, extensionId, 'nbNeedsReauth')).toBe(
      false
    );

    // The token must be stripped from the URL fragment after handoff so it
    // isn't left in the address bar / history.
    expect(new URL(nbPage.url()).hash).toBe('');
  });

  test('ignores the success page when no token is present', async ({
    context,
    extensionId,
    nbPage,
  }) => {
    await nbPage.route('**://natassistant.com/connected*', async (route) => {
      const res = await route.fetch({ url: 'http://localhost:3456/connected' });
      const body = await res.text();
      await route.fulfill({ status: 200, contentType: 'text/html', body });
    });

    await nbPage.goto('https://natassistant.com/connected?error=missing_code');

    // No token means nothing is written.
    await nbPage.waitForTimeout(500);
    expect(
      await getStorageValue(context, extensionId, 'authToken')
    ).toBeUndefined();
  });
});
