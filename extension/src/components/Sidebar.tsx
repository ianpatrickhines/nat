import { useState } from 'preact/hooks';

interface SidebarProps {
  initialOpen?: boolean;
}

export function Sidebar({ initialOpen = true }: SidebarProps) {
  const [isOpen, setIsOpen] = useState(initialOpen);

  const toggleSidebar = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className={`nat-sidebar ${isOpen ? 'nat-sidebar--open' : 'nat-sidebar--collapsed'}`}>
      <button
        className="nat-sidebar__toggle"
        onClick={toggleSidebar}
        aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {isOpen ? '→' : '←'}
      </button>

      {isOpen && (
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
      )}
    </div>
  );
}
