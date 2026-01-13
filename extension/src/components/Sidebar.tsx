import { useState, useImperativeHandle, forwardRef } from 'preact/compat';
import { Chat } from './Chat';
import { AuthScreen, useAuthState, getAuthScreenType } from './AuthScreen';
import { Tutorial, useTutorialState } from './Tutorial';
import { PageContext, getContextDisplayText } from '../utils/pageContext';

export interface SidebarHandle {
  toggle: () => void;
  isOpen: () => boolean;
  setPageContext: (context: PageContext | null) => void;
}

interface SidebarProps {
  initialOpen?: boolean;
  onToggle?: (isOpen: boolean) => void;
  initialPageContext?: PageContext | null;
}

export const Sidebar = forwardRef<SidebarHandle, SidebarProps>(
  function Sidebar({ initialOpen = true, onToggle, initialPageContext }, ref) {
    const [isOpen, setIsOpen] = useState(initialOpen);
    const [pageContext, setPageContext] = useState<PageContext | null>(initialPageContext || null);
    const { authState, isLoading } = useAuthState();
    const { showTutorial, isLoading: tutorialLoading, completeTutorial } = useTutorialState();

    const toggleSidebar = () => {
      const newState = !isOpen;
      setIsOpen(newState);
      onToggle?.(newState);
    };

    // Expose methods to parent via ref
    useImperativeHandle(ref, () => ({
      toggle: toggleSidebar,
      isOpen: () => isOpen,
      setPageContext: (context: PageContext | null) => setPageContext(context),
    }));

    // Get display text for current context
    const contextDisplayText = getContextDisplayText(pageContext);

    // Determine what content to show based on auth state
    const screenType = getAuthScreenType(authState);
    const showChat = screenType === 'ready';

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
              {contextDisplayText && (
                <div className="nat-sidebar__context">
                  <span className="nat-sidebar__context-label">Viewing:</span>
                  <span className="nat-sidebar__context-value">{contextDisplayText}</span>
                </div>
              )}
            </header>

            <main className="nat-sidebar__main">
              {isLoading || tutorialLoading ? (
                <div className="nat-sidebar__loading">
                  <div className="nat-sidebar__loading-spinner"></div>
                  <span>Loading...</span>
                </div>
              ) : showChat ? (
                showTutorial ? (
                  <Tutorial onComplete={completeTutorial} />
                ) : (
                  <Chat pageContext={pageContext} />
                )
              ) : (
                <AuthScreen authState={authState} />
              )}
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
