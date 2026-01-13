/**
 * NationBuilder page context detection
 *
 * Parses URL patterns and DOM elements to determine what type of page
 * the user is viewing and extract relevant information.
 */

export interface PageContext {
  page_type: string;
  person_name?: string;
  person_id?: string;
  list_name?: string;
  list_id?: string;
  event_name?: string;
  event_id?: string;
  donation_id?: string;
  donation_amount?: string;
}

/**
 * Detect the current NationBuilder page context from URL and DOM
 */
export function detectPageContext(): PageContext | null {
  const pathname = window.location.pathname;

  // Try each page type detector in order of specificity
  return (
    detectPersonPage(pathname) ||
    detectListPage(pathname) ||
    detectEventPage(pathname) ||
    detectDonationPage(pathname) ||
    detectDashboardPage(pathname) ||
    null
  );
}

/**
 * Person profile page detection
 * URL patterns:
 *   /admin/signups/{id}
 *   /admin/signups/{id}/edit
 *   /admin/signups/{id}/donations
 *   etc.
 */
function detectPersonPage(pathname: string): PageContext | null {
  // Match /admin/signups/{id} where id is numeric
  const signupMatch = pathname.match(/\/admin\/signups\/(\d+)/);
  if (!signupMatch) return null;

  const personId = signupMatch[1];
  const personName = extractPersonNameFromDOM();

  return {
    page_type: 'person',
    person_id: personId,
    person_name: personName || undefined,
  };
}

/**
 * Extract person name from the page DOM
 * NationBuilder typically shows the name in page headers or breadcrumbs
 */
function extractPersonNameFromDOM(): string | null {
  // Try various selectors commonly used in NB admin for person names

  // 1. Page header h1/h2 that contains the person's name
  const pageTitle = document.querySelector('.page-title, .page-header h1, .page-header h2');
  if (pageTitle?.textContent) {
    const text = pageTitle.textContent.trim();
    // Filter out generic titles
    if (text && !text.toLowerCase().includes('signups') && !text.toLowerCase().includes('edit')) {
      return text;
    }
  }

  // 2. Breadcrumb with person name (often the last breadcrumb)
  const breadcrumbs = document.querySelectorAll('.breadcrumb li, .breadcrumbs a, nav[aria-label="breadcrumb"] li');
  if (breadcrumbs.length > 0) {
    const lastBreadcrumb = breadcrumbs[breadcrumbs.length - 1];
    const text = lastBreadcrumb?.textContent?.trim();
    if (text && !text.toLowerCase().includes('signups') && !text.toLowerCase().includes('edit')) {
      return text;
    }
  }

  // 3. Profile header area
  const profileHeader = document.querySelector('.profile-header h1, .signup-header h1, [data-signup-name]');
  if (profileHeader?.textContent) {
    return profileHeader.textContent.trim();
  }

  // 4. Look for a name in the main content area header
  const mainHeader = document.querySelector('main h1, #main h1, .content h1');
  if (mainHeader?.textContent) {
    const text = mainHeader.textContent.trim();
    // Basic check - names typically have 2-4 words
    const words = text.split(/\s+/);
    if (words.length >= 2 && words.length <= 5 && !text.includes(':')) {
      return text;
    }
  }

  return null;
}

/**
 * List page detection
 * URL patterns:
 *   /admin/lists/{id}
 *   /admin/signups?list_id={id}
 *   /admin/signups?filter=...
 */
function detectListPage(pathname: string): PageContext | null {
  // Match /admin/lists/{id}
  const listMatch = pathname.match(/\/admin\/lists\/(\d+)/);
  if (listMatch) {
    return {
      page_type: 'list',
      list_id: listMatch[1],
      list_name: extractListNameFromDOM(),
    };
  }

  // Check for signups page with list filter
  if (pathname === '/admin/signups' || pathname.startsWith('/admin/signups')) {
    const params = new URLSearchParams(window.location.search);
    const listId = params.get('list_id');
    if (listId) {
      return {
        page_type: 'list',
        list_id: listId,
        list_name: extractListNameFromDOM(),
      };
    }

    // Check if on signups list without specific filter - still a list view
    const hasFilter = params.has('filter') || params.has('q') || params.has('tags');
    if (hasFilter || pathname === '/admin/signups') {
      return {
        page_type: 'signups_list',
        list_name: extractListNameFromDOM() || 'All Signups',
      };
    }
  }

  return null;
}

/**
 * Extract list name from DOM
 */
function extractListNameFromDOM(): string | undefined {
  // Try page title first
  const pageTitle = document.querySelector('.page-title, .page-header h1, h1.list-name');
  if (pageTitle?.textContent) {
    const text = pageTitle.textContent.trim();
    if (text && text.toLowerCase() !== 'lists' && text.toLowerCase() !== 'signups') {
      return text;
    }
  }

  // Try list name in breadcrumbs
  const breadcrumbs = document.querySelectorAll('.breadcrumb li, .breadcrumbs a');
  for (let i = breadcrumbs.length - 1; i >= 0; i--) {
    const text = breadcrumbs[i]?.textContent?.trim();
    if (text && text.toLowerCase() !== 'lists' && text.toLowerCase() !== 'signups') {
      return text;
    }
  }

  return undefined;
}

/**
 * Event page detection
 * URL patterns:
 *   /admin/sites/{slug}/pages/events/{id}
 *   /admin/sites/{slug}/pages/{page_id}/events/{id}
 */
function detectEventPage(pathname: string): PageContext | null {
  // Match event pages
  const eventMatch = pathname.match(/\/admin\/sites\/[^/]+\/pages\/(?:events\/(\d+)|.*\/events\/(\d+))/);
  if (!eventMatch) return null;

  const eventId = eventMatch[1] || eventMatch[2];
  const eventName = extractEventNameFromDOM();

  return {
    page_type: 'event',
    event_id: eventId,
    event_name: eventName,
  };
}

/**
 * Extract event name from DOM
 */
function extractEventNameFromDOM(): string | undefined {
  // Event name in page header
  const pageTitle = document.querySelector('.page-title, .page-header h1, .event-name, h1');
  if (pageTitle?.textContent) {
    const text = pageTitle.textContent.trim();
    if (text && text.toLowerCase() !== 'events' && text.toLowerCase() !== 'event') {
      return text;
    }
  }

  return undefined;
}

/**
 * Donation page detection
 * URL patterns:
 *   /admin/finance/donations/{id}
 *   /admin/sites/{slug}/pages/donations/{id}
 */
function detectDonationPage(pathname: string): PageContext | null {
  // Match /admin/finance/donations/{id}
  const financeMatch = pathname.match(/\/admin\/finance\/donations\/(\d+)/);
  if (financeMatch) {
    return {
      page_type: 'donation',
      donation_id: financeMatch[1],
      donation_amount: extractDonationAmountFromDOM(),
    };
  }

  // Match /admin/sites/.../pages/donations/{id}
  const siteMatch = pathname.match(/\/admin\/sites\/[^/]+\/pages\/donations\/(\d+)/);
  if (siteMatch) {
    return {
      page_type: 'donation',
      donation_id: siteMatch[1],
      donation_amount: extractDonationAmountFromDOM(),
    };
  }

  // Donations list page
  if (pathname === '/admin/finance/donations' || pathname.startsWith('/admin/finance/donations')) {
    return {
      page_type: 'donations_list',
    };
  }

  return null;
}

/**
 * Extract donation amount from DOM
 */
function extractDonationAmountFromDOM(): string | undefined {
  // Look for dollar amounts in the page
  const amountElement = document.querySelector('.donation-amount, .amount, [data-amount]');
  if (amountElement?.textContent) {
    const text = amountElement.textContent.trim();
    // Check if it looks like a dollar amount
    if (text.match(/\$[\d,.]+/)) {
      return text;
    }
  }

  return undefined;
}

/**
 * Dashboard/home page detection
 */
function detectDashboardPage(pathname: string): PageContext | null {
  if (pathname === '/admin' || pathname === '/admin/' || pathname === '/admin/dashboard') {
    return {
      page_type: 'dashboard',
    };
  }

  return null;
}

/**
 * Get a human-readable description of the page context
 */
export function getContextDisplayText(context: PageContext | null): string | null {
  if (!context) return null;

  switch (context.page_type) {
    case 'person':
      return context.person_name || `Person #${context.person_id}`;

    case 'list':
      return context.list_name || `List #${context.list_id}`;

    case 'signups_list':
      return context.list_name || 'Signups';

    case 'event':
      return context.event_name || `Event #${context.event_id}`;

    case 'donation':
      if (context.donation_amount) {
        return `Donation: ${context.donation_amount}`;
      }
      return `Donation #${context.donation_id}`;

    case 'donations_list':
      return 'Donations';

    case 'dashboard':
      return 'Dashboard';

    default:
      return context.page_type;
  }
}

/**
 * Watch for page navigation changes (SPA-style navigation)
 * Returns a cleanup function to stop watching
 */
export function watchForPageChanges(callback: (context: PageContext | null) => void): () => void {
  // Initial detection
  callback(detectPageContext());

  // Watch for URL changes via History API (SPA navigation)
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;

  history.pushState = function (...args) {
    originalPushState.apply(this, args);
    // Small delay to let DOM update
    setTimeout(() => callback(detectPageContext()), 100);
  };

  history.replaceState = function (...args) {
    originalReplaceState.apply(this, args);
    setTimeout(() => callback(detectPageContext()), 100);
  };

  // Watch for popstate (back/forward navigation)
  const handlePopState = () => {
    setTimeout(() => callback(detectPageContext()), 100);
  };
  window.addEventListener('popstate', handlePopState);

  // Also watch for hash changes
  const handleHashChange = () => {
    setTimeout(() => callback(detectPageContext()), 100);
  };
  window.addEventListener('hashchange', handleHashChange);

  // Cleanup function
  return () => {
    history.pushState = originalPushState;
    history.replaceState = originalReplaceState;
    window.removeEventListener('popstate', handlePopState);
    window.removeEventListener('hashchange', handleHashChange);
  };
}
