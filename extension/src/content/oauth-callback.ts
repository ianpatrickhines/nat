/**
 * OAuth-success content script.
 *
 * Runs on the Nat OAuth success page (configured via SUCCESS_REDIRECT_URL on the
 * backend, e.g. https://natassistant.com/connected). After the NationBuilder
 * connect flow completes, the backend's `nb_oauth_callback` Lambda redirects
 * here with:
 *
 *   ?user_id=<id>&nation=<slug>#session_token=<jwt>
 *
 * The minted session token is delivered in the URL *fragment* so it never
 * reaches the success page's server or its access logs. This script reads it,
 * hands it to the background service worker (which stores it in chrome.storage
 * for use as `Authorization: Bearer`), then strips the fragment from the URL so
 * the token isn't left lingering in the address bar / history.
 */

function readToken(): {
  sessionToken: string;
  userId: string;
  nationSlug: string;
} | null {
  // Token lives in the fragment (after '#').
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash;
  const fragment = new URLSearchParams(hash);
  const sessionToken = fragment.get('session_token');
  if (!sessionToken) {
    return null;
  }

  // Identity is for UI display only; the signed token is the source of truth.
  const query = new URLSearchParams(window.location.search);
  const userId = query.get('user_id') || '';
  const nationSlug = query.get('nation') || '';

  return { sessionToken, userId, nationSlug };
}

function clearFragment(): void {
  try {
    // Remove the fragment so the token isn't left in the address bar/history.
    history.replaceState(
      null,
      '',
      window.location.pathname + window.location.search
    );
  } catch {
    // history may be unavailable in some contexts; non-fatal.
  }
}

function handoffToken(): void {
  const session = readToken();
  if (!session) {
    return;
  }

  try {
    const sending = chrome.runtime.sendMessage({
      type: 'SET_SESSION',
      sessionToken: session.sessionToken,
      userId: session.userId,
      nationSlug: session.nationSlug,
    });
    if (sending && typeof sending.catch === 'function') {
      sending.catch(() => {});
    }
  } catch {
    // chrome.runtime may be unavailable if the extension context was invalidated.
  }

  clearFragment();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', handoffToken);
} else {
  handoffToken();
}
