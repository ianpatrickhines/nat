import { render } from 'preact';
import { Sidebar, SidebarHandle } from '../components/Sidebar';
import { createRef } from 'preact';
import { detectPageContext, extractNationSlugFromUrl, watchForPageChanges, PageContext } from '../utils/pageContext';

// Reference to sidebar for keyboard toggle and context updates
let sidebarRef: { current: SidebarHandle | null } = { current: null };

// Store current page context
let currentPageContext: PageContext | null = null;

// Track the last reported slug so we only message the background on change.
let lastReportedNationSlug: string | null | undefined = undefined;

/**
 * Detect the nation slug from the current URL and report it to the background
 * worker so it can be attached to backend requests (per-nation billing).
 */
function reportNationSlug() {
  const nationSlug = extractNationSlugFromUrl(window.location.href);
  if (nationSlug === lastReportedNationSlug) {
    return;
  }
  lastReportedNationSlug = nationSlug;

  try {
    const sending = chrome.runtime.sendMessage({ type: 'SET_NATION_SLUG', nationSlug });
    // sendMessage returns a Promise in MV3; ignore failures (e.g. worker asleep).
    if (sending && typeof sending.catch === 'function') {
      sending.catch(() => {});
    }
  } catch {
    // chrome.runtime may be unavailable if the extension context was invalidated.
  }
}

function updateBodyMargin(isOpen: boolean) {
  // Adjust body margin to prevent sidebar from overlapping NB content
  document.body.style.marginRight = isOpen ? '350px' : '40px';
  document.body.style.transition = 'margin-right 0.2s ease';
}

function setupKeyboardShortcut() {
  document.addEventListener('keydown', (event) => {
    // Cmd+K (Mac) or Ctrl+K (Windows/Linux) toggles sidebar
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    const modifier = isMac ? event.metaKey : event.ctrlKey;

    if (modifier && event.key === 'k') {
      event.preventDefault();
      event.stopPropagation();

      if (sidebarRef.current) {
        sidebarRef.current.toggle();
      }
    }
  });
}

function init() {
  // Check if we're on a NationBuilder domain
  if (!window.location.hostname.includes('nationbuilder.com')) {
    return;
  }

  // Don't inject if sidebar already exists
  if (document.getElementById('nat-sidebar-root')) {
    return;
  }

  // Create container for the sidebar
  const container = document.createElement('div');
  container.id = 'nat-sidebar-root';
  document.body.appendChild(container);

  // Create ref for sidebar
  sidebarRef = createRef<SidebarHandle>();

  // Detect initial page context
  currentPageContext = detectPageContext();

  // Detect and report the nation slug for per-nation billing
  reportNationSlug();

  // Set initial body margin
  updateBodyMargin(true);

  // Set up keyboard shortcut
  setupKeyboardShortcut();

  // Set up page context watching for SPA navigation
  watchForPageChanges((context) => {
    currentPageContext = context;
    // The slug can change on SPA navigation between nations; re-report it.
    reportNationSlug();
    if (sidebarRef.current) {
      sidebarRef.current.setPageContext(context);
    }
  });

  // Render the Preact app with initial context
  render(
    <Sidebar
      ref={sidebarRef}
      onToggle={updateBodyMargin}
      initialPageContext={currentPageContext}
    />,
    container
  );
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
