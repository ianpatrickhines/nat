import { useState, useImperativeHandle, forwardRef } from 'preact/compat';

export interface SidebarHandle {
  toggle: () => void;
  isOpen: () => boolean;
}

interface SidebarProps {
  initialOpen?: boolean;
  onToggle?: (isOpen: boolean) => void;
}

export const Sidebar = forwardRef<SidebarHandle, SidebarProps>(
  function Sidebar({ initialOpen = true, onToggle }, ref) {
    const [isOpen, setIsOpen] = useState(initialOpen);

    const toggleSidebar = () => {
      const newState = !isOpen;
      setIsOpen(newState);
      onToggle?.(newState);
    };

    // Expose toggle method to parent via ref
    useImperativeHandle(ref, () => ({
      toggle: toggleSidebar,
      isOpen: () => isOpen
    }));

    return (
      <div className={`nat-sidebar ${isOpen ? 'nat-sidebar--open' : 'nat-sidebar--collapsed'}`}>
        <button
          className="nat-sidebar__toggle"
          onClick={toggleSidebar}
          aria-label={isOpen ? 'Collapse sidebar (⌘K)' : 'Expand sidebar (⌘K)'}
          title={isOpen ? 'Collapse (⌘K / Ctrl+K)' : 'Expand (⌘K / Ctrl+K)'}
        >
          {isOpen ? '→' : '←'}
        </button>

        {isOpen ? (
          <div className="nat-sidebar__content">
            <header className="nat-sidebar__header">
              <h1 className="nat-sidebar__title">Nat</h1>
              <span className="nat-sidebar__subtitle">NationBuilder Assistant</span>
            </header>

            <main className="nat-sidebar__main">
              <p className="nat-sidebar__placeholder">
                Extension loaded successfully. Chat UI coming soon.
              </p>
            </main>
          </div>
        ) : (
          <div className="nat-sidebar__collapsed-content">
            <div className="nat-sidebar__collapsed-icon" title="Nat - Click or press ⌘K to expand">
              <span className="nat-sidebar__collapsed-letter">N</span>
            </div>
          </div>
        )}
      </div>
    );
  }
);
