import { useState, useEffect } from 'preact/hooks';

// ============================================================================
// Types
// ============================================================================

interface AuthState {
  isAuthenticated: boolean;
  userId: string | null;
  tenantId: string | null;
  /** Slug of the NationBuilder nation the user is currently in (per-nation billing). */
  nationSlug: string | null;
  nbConnected: boolean;
  nbNeedsReauth: boolean;
  subscriptionStatus: 'active' | 'trialing' | 'cancelled' | 'past_due' | 'unpaid' | 'none' | null;
}

type AuthScreenType =
  | 'not_logged_in'       // User not authenticated to Nat - show sign-in / subscribe prompt
  | 'nation_not_subscribed' // Authenticated, but this nation has no subscription
  | 'nb_not_connected'    // Logged in but NB not connected
  | 'nb_needs_reauth'     // NB connection needs reauthorization
  | 'subscription_lapsed' // Nation subscription lapsed (cancelled/past_due/unpaid)
  | 'ready';              // All good, show chat

interface AuthScreenProps {
  authState: AuthState;
  onAuthStateChange?: () => void;
}

// ============================================================================
// Configuration
// ============================================================================

// These would be configured at build time with actual URLs
const STRIPE_CHECKOUT_URL = 'https://nat.example.com/pricing';
const NB_CONNECT_URL = 'https://nat.example.com/auth/nationbuilder';
const UPDATE_CARD_URL = 'https://billing.stripe.com/p/login/test'; // Stripe billing portal

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Determine which auth screen to show based on auth state
 */
export function getAuthScreenType(authState: AuthState): AuthScreenType {
  // Not authenticated to Nat at all (the user themselves isn't signed in)
  if (!authState.isAuthenticated) {
    return 'not_logged_in';
  }

  // Authenticated, but this nation has never subscribed (no subscription on record).
  // Distinct from a lapsed subscription: here we prompt to subscribe the nation.
  if (authState.subscriptionStatus === null || authState.subscriptionStatus === 'none') {
    return 'nation_not_subscribed';
  }

  // Nation subscription exists but is no longer active (cancelled / payment failed)
  if (authState.subscriptionStatus !== 'active' && authState.subscriptionStatus !== 'trialing') {
    return 'subscription_lapsed';
  }

  // NB needs reauthorization
  if (authState.nbNeedsReauth) {
    return 'nb_needs_reauth';
  }

  // NB not connected
  if (!authState.nbConnected) {
    return 'nb_not_connected';
  }

  // Everything is good
  return 'ready';
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Not logged in - Show subscribe prompt
 */
function NotLoggedInScreen() {
  const handleSubscribe = () => {
    window.open(STRIPE_CHECKOUT_URL, '_blank');
  };

  return (
    <div className="nat-auth-screen">
      <div className="nat-auth-screen__icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      </div>
      <h2 className="nat-auth-screen__title">Welcome to Nat</h2>
      <p className="nat-auth-screen__description">
        Your AI assistant for NationBuilder. Subscribe to start organizing smarter.
      </p>
      <button
        className="nat-auth-screen__btn nat-auth-screen__btn--primary"
        onClick={handleSubscribe}
      >
        Subscribe to Nat
      </button>
      <p className="nat-auth-screen__hint">
        Already subscribed?{' '}
        <a href={STRIPE_CHECKOUT_URL} target="_blank" rel="noopener noreferrer">
          Sign in
        </a>
      </p>
    </div>
  );
}

/**
 * Authenticated, but the current nation has no subscription -
 * Show a "Subscribe your nation" prompt.
 */
function NationNotSubscribedScreen({ nationSlug }: { nationSlug: string | null }) {
  const handleSubscribe = () => {
    // Pass the detected nation through so checkout can pre-fill it.
    const url = nationSlug
      ? `${STRIPE_CHECKOUT_URL}?nation_slug=${encodeURIComponent(nationSlug)}`
      : STRIPE_CHECKOUT_URL;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="nat-auth-screen">
      <div className="nat-auth-screen__icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4" />
        </svg>
      </div>
      <h2 className="nat-auth-screen__title">Subscribe your nation</h2>
      <p className="nat-auth-screen__description">
        {nationSlug
          ? <>Nat isn't active for <strong>{nationSlug}</strong> yet. Subscribe this nation and everyone on your team can use Nat.</>
          : <>This nation doesn't have an active Nat subscription yet. Subscribe to let everyone on your team use Nat.</>}
      </p>
      <button
        className="nat-auth-screen__btn nat-auth-screen__btn--primary"
        onClick={handleSubscribe}
      >
        Subscribe your nation
      </button>
      <p className="nat-auth-screen__hint">
        One subscription covers your whole nation — no per-seat billing.
      </p>
    </div>
  );
}

/**
 * Logged in but NB not connected - Show connect NationBuilder button
 */
function NbNotConnectedScreen() {
  const handleConnect = () => {
    window.open(NB_CONNECT_URL, '_blank');
  };

  return (
    <div className="nat-auth-screen">
      <div className="nat-auth-screen__icon nat-auth-screen__icon--success">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      </div>
      <h2 className="nat-auth-screen__title">Almost There!</h2>
      <p className="nat-auth-screen__description">
        Connect your NationBuilder account to let Nat help you manage your nation.
      </p>
      <button
        className="nat-auth-screen__btn nat-auth-screen__btn--primary"
        onClick={handleConnect}
      >
        Connect NationBuilder
      </button>
      <p className="nat-auth-screen__hint">
        Nat will only access data you authorize. You can disconnect at any time.
      </p>
    </div>
  );
}

/**
 * NB needs reauthorization - Show reconnect banner with explanation
 */
function NbNeedsReauthScreen() {
  const handleReconnect = () => {
    window.open(NB_CONNECT_URL, '_blank');
  };

  return (
    <div className="nat-auth-screen">
      <div className="nat-auth-screen__banner nat-auth-screen__banner--warning">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span>NationBuilder connection expired</span>
      </div>
      <div className="nat-auth-screen__icon nat-auth-screen__icon--warning">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
        </svg>
      </div>
      <h2 className="nat-auth-screen__title">Reconnect Required</h2>
      <p className="nat-auth-screen__description">
        Your NationBuilder authorization has expired. This happens periodically for security. Please reconnect to continue using Nat.
      </p>
      <button
        className="nat-auth-screen__btn nat-auth-screen__btn--primary"
        onClick={handleReconnect}
      >
        Reconnect NationBuilder
      </button>
      <p className="nat-auth-screen__hint">
        Your chat history and preferences are safe.
      </p>
    </div>
  );
}

/**
 * Subscription lapsed - Show payment failed with update card link
 */
function SubscriptionLapsedScreen({ subscriptionStatus }: { subscriptionStatus: AuthState['subscriptionStatus'] }) {
  const handleUpdateCard = () => {
    window.open(UPDATE_CARD_URL, '_blank');
  };

  const handleResubscribe = () => {
    window.open(STRIPE_CHECKOUT_URL, '_blank');
  };

  // Different messaging based on subscription status
  const isCancelled = subscriptionStatus === 'cancelled';
  const isPaymentFailed = subscriptionStatus === 'past_due' || subscriptionStatus === 'unpaid';

  return (
    <div className="nat-auth-screen">
      <div className="nat-auth-screen__banner nat-auth-screen__banner--error">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span>{isPaymentFailed ? 'Payment failed' : 'Subscription inactive'}</span>
      </div>
      <div className="nat-auth-screen__icon nat-auth-screen__icon--error">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
          <line x1="1" y1="10" x2="23" y2="10" />
        </svg>
      </div>
      <h2 className="nat-auth-screen__title">
        {isPaymentFailed ? 'Payment Failed' : 'Subscription Ended'}
      </h2>
      <p className="nat-auth-screen__description">
        {isPaymentFailed
          ? "We couldn't process your payment. Please update your card to continue using Nat."
          : "Your Nat subscription has ended. Resubscribe to continue using Nat with your NationBuilder account."
        }
      </p>
      {isPaymentFailed ? (
        <button
          className="nat-auth-screen__btn nat-auth-screen__btn--primary"
          onClick={handleUpdateCard}
        >
          Update Payment Method
        </button>
      ) : (
        <button
          className="nat-auth-screen__btn nat-auth-screen__btn--primary"
          onClick={handleResubscribe}
        >
          Resubscribe to Nat
        </button>
      )}
      {isCancelled && (
        <p className="nat-auth-screen__hint">
          Your data will be kept for 30 days after cancellation.
        </p>
      )}
      {isPaymentFailed && (
        <p className="nat-auth-screen__hint">
          Need help?{' '}
          <a href="mailto:support@nat.example.com">Contact support</a>
        </p>
      )}
    </div>
  );
}

// ============================================================================
// Main AuthScreen Component
// ============================================================================

export function AuthScreen({ authState }: AuthScreenProps) {
  const screenType = getAuthScreenType(authState);

  switch (screenType) {
    case 'not_logged_in':
      return <NotLoggedInScreen />;

    case 'nation_not_subscribed':
      return <NationNotSubscribedScreen nationSlug={authState.nationSlug} />;

    case 'nb_not_connected':
      return <NbNotConnectedScreen />;

    case 'nb_needs_reauth':
      return <NbNeedsReauthScreen />;

    case 'subscription_lapsed':
      return <SubscriptionLapsedScreen subscriptionStatus={authState.subscriptionStatus} />;

    case 'ready':
      // This shouldn't render - parent should show Chat instead
      return null;
  }
}

// ============================================================================
// Hook to fetch and manage auth state
// ============================================================================

export function useAuthState() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    userId: null,
    tenantId: null,
    nationSlug: null,
    nbConnected: false,
    nbNeedsReauth: false,
    subscriptionStatus: null,
  });
  const [isLoading, setIsLoading] = useState(true);

  // Fetch initial auth state
  useEffect(() => {
    const fetchAuthState = async () => {
      try {
        const response = await chrome.runtime.sendMessage({ type: 'GET_AUTH_STATE' });
        if (response) {
          setAuthState(response as AuthState);
        }
      } catch (error) {
        console.error('Failed to get auth state:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchAuthState();
  }, []);

  // Listen for auth state changes
  useEffect(() => {
    const handleMessage = (message: { type: string; authState?: AuthState }) => {
      if (message.type === 'AUTH_STATE_CHANGED' && message.authState) {
        setAuthState(message.authState);
      }
    };

    chrome.runtime.onMessage.addListener(handleMessage);
    return () => {
      chrome.runtime.onMessage.removeListener(handleMessage);
    };
  }, []);

  return { authState, isLoading };
}

export type { AuthState, AuthScreenType };
