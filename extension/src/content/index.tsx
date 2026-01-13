import { render } from 'preact';
import { Sidebar } from '../components/Sidebar';

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

  // Render the Preact app
  render(<Sidebar />, container);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
