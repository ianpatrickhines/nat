/**
 * Nat Success Page JavaScript
 * Verifies subscription status and displays success/error states
 */

// API endpoint - configure for production
const VERIFY_API_URL = import.meta.env.VITE_VERIFY_API_URL || 'https://api.natassistant.com/stripe/verify-session';

// Chrome Web Store URL - placeholder until extension is published
const CHROME_STORE_URL = import.meta.env.VITE_CHROME_STORE_URL || 'https://chrome.google.com/webstore/detail/nat';

interface VerifyResponse {
  status: 'active' | 'trialing' | 'incomplete' | 'past_due' | 'canceled' | 'unpaid';
  plan: string;
  customer_email: string;
}

interface VerifyError {
  error: string;
}

// Plan display names
const PLAN_NAMES: Record<string, string> = {
  starter: 'Starter ($49/month)',
  team: 'Team ($149/month)',
  organization: 'Organization ($399/month)',
};

// DOM elements
const loadingState = document.getElementById('loading-state');
const successState = document.getElementById('success-state');
const errorState = document.getElementById('error-state');
const planNameEl = document.getElementById('plan-name');
const errorMessageEl = document.getElementById('error-message');
const chromeStoreLink = document.getElementById('chrome-store-link') as HTMLAnchorElement | null;

function showState(state: 'loading' | 'success' | 'error'): void {
  if (loadingState) loadingState.style.display = state === 'loading' ? 'flex' : 'none';
  if (successState) successState.style.display = state === 'success' ? 'flex' : 'none';
  if (errorState) errorState.style.display = state === 'error' ? 'flex' : 'none';
}

function showError(message: string): void {
  if (errorMessageEl) {
    errorMessageEl.textContent = message;
  }
  showState('error');
}

function showSuccess(plan: string): void {
  if (planNameEl) {
    planNameEl.textContent = PLAN_NAMES[plan] || plan;
  }
  if (chromeStoreLink) {
    chromeStoreLink.href = CHROME_STORE_URL;
  }
  showState('success');
}

async function verifySession(sessionId: string): Promise<void> {
  try {
    const response = await fetch(VERIFY_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ session_id: sessionId }),
    });

    const data: VerifyResponse | VerifyError = await response.json();

    if (!response.ok) {
      throw new Error((data as VerifyError).error || 'Failed to verify subscription');
    }

    const verifyData = data as VerifyResponse;

    if (verifyData.status === 'active' || verifyData.status === 'trialing') {
      showSuccess(verifyData.plan);
    } else {
      showError(`Your subscription status is "${verifyData.status}". Please contact support if you believe this is an error.`);
    }
  } catch (error) {
    console.error('Verification error:', error);
    showError('We couldn\'t verify your subscription. If you completed payment, please wait a moment and refresh this page, or contact support.');
  }
}

// On page load, check for session_id in URL
function init(): void {
  const urlParams = new URLSearchParams(window.location.search);
  const sessionId = urlParams.get('session_id');

  if (!sessionId) {
    // No session ID - show success anyway (user may have bookmarked the page)
    // In production, might want to redirect to home or show a different message
    showSuccess('starter'); // Default fallback
    return;
  }

  verifySession(sessionId);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// Console greeting for developers
console.log(
  '%cNat%c - Thanks for subscribing!',
  'color: #7c3aed; font-weight: bold; font-size: 16px;',
  'color: inherit; font-size: 14px;'
);
