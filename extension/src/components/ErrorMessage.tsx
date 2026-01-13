/**
 * ErrorMessage component for displaying user-friendly error messages
 * Maps technical error codes to natural language messages
 */

// ============================================================================
// Error Code to User-Friendly Message Mapping
// ============================================================================

interface ErrorInfo {
  message: string;
  /** Optional title displayed above the message */
  title?: string;
  /** Optional action the user can take */
  action?: {
    label: string;
    url?: string;
    onClick?: () => void;
  };
  /** Icon type: 'error', 'warning', 'info' */
  variant: 'error' | 'warning' | 'info';
}

/**
 * Map backend error codes to user-friendly messages
 */
export function getErrorInfo(errorCode: string, rawError?: string, retryAfter?: number): ErrorInfo {
  switch (errorCode) {
    // NationBuilder API errors
    case 'NB_NOT_CONNECTED':
      return {
        title: 'NationBuilder Not Connected',
        message: 'Connect your NationBuilder account to start using Nat.',
        action: {
          label: 'Connect Now',
          // This would be handled by the auth screen, not a URL action
        },
        variant: 'warning',
      };

    case 'NB_NEEDS_REAUTH':
      return {
        title: 'Reconnection Required',
        message: 'Your NationBuilder connection has expired. Please reconnect to continue.',
        action: {
          label: 'Reconnect',
        },
        variant: 'warning',
      };

    case 'NB_TOKENS_MISSING':
      return {
        title: 'Connection Error',
        message: "NationBuilder isn't responding right now. Please try again in a moment.",
        variant: 'error',
      };

    case 'NB_API_ERROR':
    case 'NB_ERROR':
      return {
        title: 'NationBuilder Unavailable',
        message: "NationBuilder isn't responding right now. Please try again in a moment.",
        variant: 'error',
      };

    case 'NB_PERMISSION_ERROR':
    case 'NB_FORBIDDEN':
      return {
        title: 'Permission Denied',
        message: "Your NationBuilder account doesn't have permission to perform this action. Check your admin settings.",
        variant: 'warning',
      };

    // Claude/Agent errors
    case 'AGENT_ERROR':
    case 'CLAUDE_ERROR':
    case 'AI_ERROR':
      return {
        title: 'Nat Unavailable',
        message: 'Nat is temporarily unavailable. Please try again in a moment.',
        variant: 'error',
      };

    // Subscription/Payment errors
    case 'PAYMENT_REQUIRED':
    case 'QUERY_LIMIT_EXCEEDED':
    case 'QUOTA_EXCEEDED':
      return {
        title: 'Monthly Limit Reached',
        message: "You've reached your monthly query limit.",
        action: {
          label: 'Upgrade Plan',
          url: 'https://nat.hines.digital/pricing', // Placeholder URL
        },
        variant: 'warning',
      };

    case 'SUBSCRIPTION_INACTIVE':
    case 'SUBSCRIPTION_CANCELLED':
      return {
        title: 'Subscription Ended',
        message: 'Your subscription has ended. Renew to continue using Nat.',
        action: {
          label: 'Renew Subscription',
          url: 'https://nat.hines.digital/pricing', // Placeholder URL
        },
        variant: 'warning',
      };

    // Rate limiting
    case 'RATE_LIMIT_EXCEEDED':
      const waitTime = retryAfter ? Math.ceil(retryAfter) : 5;
      return {
        title: 'Slow Down',
        message: `Please wait ${waitTime} second${waitTime !== 1 ? 's' : ''} before sending another message.`,
        variant: 'info',
      };

    // Connection/Network errors
    case 'CONNECTION_ERROR':
    case 'NETWORK_ERROR':
      return {
        title: 'Connection Lost',
        message: 'Connection to the server was lost. Check your internet and try again.',
        variant: 'error',
      };

    case 'TIMEOUT':
      return {
        title: 'Request Timeout',
        message: 'The request took too long. Please try again.',
        variant: 'error',
      };

    // User/Auth errors
    case 'USER_NOT_FOUND':
    case 'UNAUTHORIZED':
      return {
        title: 'Session Expired',
        message: 'Your session has expired. Please refresh the page and try again.',
        variant: 'warning',
      };

    case 'NO_TENANT':
      return {
        title: 'Account Issue',
        message: "There's an issue with your account. Please contact support.",
        variant: 'error',
      };

    case 'FORBIDDEN':
      return {
        title: 'Access Denied',
        message: "You don't have permission to perform this action.",
        variant: 'warning',
      };

    // Bad request errors
    case 'BAD_REQUEST':
    case 'INVALID_REQUEST':
      return {
        title: 'Invalid Request',
        message: 'Something went wrong with that request. Please try again.',
        variant: 'error',
      };

    // API/Server errors
    case 'API_ERROR':
    case 'SERVER_ERROR':
    case 'INTERNAL_ERROR':
      return {
        title: 'Server Error',
        message: 'Something went wrong on our end. Please try again in a moment.',
        variant: 'error',
      };

    // Unknown/Default
    default:
      // Try to provide a friendly message even for unknown errors
      if (rawError && rawError.toLowerCase().includes('nationbuilder')) {
        return {
          title: 'NationBuilder Error',
          message: "NationBuilder isn't responding right now. Please try again in a moment.",
          variant: 'error',
        };
      }
      if (rawError && rawError.toLowerCase().includes('permission')) {
        return {
          title: 'Permission Denied',
          message: "Your NationBuilder account doesn't have permission to perform this action.",
          variant: 'warning',
        };
      }
      return {
        title: 'Something Went Wrong',
        message: rawError || 'An unexpected error occurred. Please try again.',
        variant: 'error',
      };
  }
}

/**
 * Format error for display in chat message
 * Returns just the message text for inline display
 */
export function formatErrorMessage(errorCode: string, rawError?: string, retryAfter?: number): string {
  const info = getErrorInfo(errorCode, rawError, retryAfter);
  return info.message;
}

// ============================================================================
// ErrorMessage Component
// ============================================================================

interface ErrorMessageProps {
  errorCode: string;
  error?: string;
  retryAfter?: number;
  onAction?: () => void;
}

/**
 * Renders a user-friendly error message with optional action button
 */
export function ErrorMessage({ errorCode, error, retryAfter, onAction }: ErrorMessageProps) {
  const info = getErrorInfo(errorCode, error, retryAfter);

  const handleAction = () => {
    if (info.action?.onClick) {
      info.action.onClick();
    } else if (info.action?.url) {
      window.open(info.action.url, '_blank', 'noopener,noreferrer');
    } else if (onAction) {
      onAction();
    }
  };

  return (
    <div className={`nat-error-message nat-error-message--${info.variant}`}>
      <div className="nat-error-message__icon">
        {info.variant === 'error' && (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
          </svg>
        )}
        {info.variant === 'warning' && (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
        )}
        {info.variant === 'info' && (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clipRule="evenodd" />
          </svg>
        )}
      </div>
      <div className="nat-error-message__content">
        {info.title && (
          <div className="nat-error-message__title">{info.title}</div>
        )}
        <div className="nat-error-message__text">{info.message}</div>
        {info.action && (
          <button
            className={`nat-error-message__action nat-error-message__action--${info.variant}`}
            onClick={handleAction}
          >
            {info.action.label}
          </button>
        )}
      </div>
    </div>
  );
}
