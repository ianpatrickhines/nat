import { render } from 'preact';
import { Sidebar, SidebarHandle } from '../components/Sidebar';
import { createRef } from 'preact';
import { detectPageContext, watchForPageChanges, PageContext } from '../utils/pageContext';

// Reference to sidebar for keyboard toggle and context updates
let sidebarRef: { current: SidebarHandle | null } = { current: null };

// Store current page context
let currentPageContext: PageContext | null = null;

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

  // Set initial body margin
  updateBodyMargin(true);

  // Set up keyboard shortcut
  setupKeyboardShortcut();

  // Set up page context watching for SPA navigation
  watchForPageChanges((context) => {
    currentPageContext = context;
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
