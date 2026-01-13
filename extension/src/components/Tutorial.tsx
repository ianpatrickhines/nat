import { useState, useEffect } from 'preact/hooks';
import { JSX } from 'preact';

// ============================================================================
// Types
// ============================================================================

interface TutorialStep {
  title: string;
  description: string;
  icon: JSX.Element;
  examples?: string[];
}

interface TutorialProps {
  onComplete: () => void;
}

// ============================================================================
// Tutorial Storage
// ============================================================================

const TUTORIAL_COMPLETED_KEY = 'nat_tutorial_completed';

/**
 * Check if the tutorial has been completed
 */
export async function isTutorialCompleted(): Promise<boolean> {
  try {
    const result = await chrome.storage.local.get(TUTORIAL_COMPLETED_KEY);
    return result[TUTORIAL_COMPLETED_KEY] === true;
  } catch (error) {
    console.error('Failed to check tutorial status:', error);
    return false;
  }
}

/**
 * Mark the tutorial as completed
 */
export async function markTutorialCompleted(): Promise<void> {
  try {
    await chrome.storage.local.set({ [TUTORIAL_COMPLETED_KEY]: true });
  } catch (error) {
    console.error('Failed to mark tutorial completed:', error);
  }
}

/**
 * Reset the tutorial (for testing)
 */
export async function resetTutorial(): Promise<void> {
  try {
    await chrome.storage.local.remove(TUTORIAL_COMPLETED_KEY);
  } catch (error) {
    console.error('Failed to reset tutorial:', error);
  }
}

// ============================================================================
// Tutorial Steps
// ============================================================================

const tutorialSteps: TutorialStep[] = [
  {
    title: 'Welcome to Nat!',
    description:
      'Nat is your AI assistant for NationBuilder. Ask questions, look up people, manage lists, and more - all without leaving the page you\'re on.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
      </svg>
    ),
  },
  {
    title: 'What Nat Can Do',
    description:
      'Nat understands your NationBuilder data. Try asking about people, donations, events, lists, and more.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <path d="M21 21l-4.35-4.35" />
      </svg>
    ),
    examples: [
      '"Find donors who gave over $500 this year"',
      '"Who are my most active volunteers?"',
      '"Add this person to the canvassing list"',
      '"Show me upcoming events in Boston"',
    ],
  },
  {
    title: 'Getting Help',
    description:
      'Not sure what to ask? Just describe what you\'re trying to do in plain language. Nat will figure out the best way to help.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
    examples: [
      '"I need to find people who volunteered but never donated"',
      '"Help me clean up duplicate contacts"',
      '"What happened with donations last month?"',
    ],
  },
  {
    title: 'Confirmations & Safety',
    description:
      'Before making any changes to your data (like deleting records or modifying lists), Nat will always ask for confirmation. You\'re in control.',
    icon: (
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
];

// ============================================================================
// Tutorial Component
// ============================================================================

export function Tutorial({ onComplete }: TutorialProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const step = tutorialSteps[currentStep];
  const isLastStep = currentStep === tutorialSteps.length - 1;

  const handleNext = () => {
    if (isLastStep) {
      handleComplete();
    } else {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleSkip = () => {
    handleComplete();
  };

  const handleComplete = async () => {
    await markTutorialCompleted();
    onComplete();
  };

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === 'ArrowRight') {
        handleNext();
      } else if (e.key === 'ArrowLeft' && currentStep > 0) {
        setCurrentStep(currentStep - 1);
      } else if (e.key === 'Escape') {
        handleSkip();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStep, isLastStep]);

  return (
    <div className="nat-tutorial">
      {/* Progress dots */}
      <div className="nat-tutorial__progress">
        {tutorialSteps.map((_, index) => (
          <div
            key={index}
            className={`nat-tutorial__dot ${
              index === currentStep ? 'nat-tutorial__dot--active' : ''
            } ${index < currentStep ? 'nat-tutorial__dot--completed' : ''}`}
            onClick={() => setCurrentStep(index)}
            role="button"
            aria-label={`Go to step ${index + 1}`}
          />
        ))}
      </div>

      {/* Step content */}
      <div className="nat-tutorial__content">
        <div className="nat-tutorial__icon">{step.icon}</div>
        <h2 className="nat-tutorial__title">{step.title}</h2>
        <p className="nat-tutorial__description">{step.description}</p>

        {step.examples && (
          <div className="nat-tutorial__examples">
            <div className="nat-tutorial__examples-label">Try asking:</div>
            {step.examples.map((example, index) => (
              <div key={index} className="nat-tutorial__example">
                {example}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Navigation buttons */}
      <div className="nat-tutorial__buttons">
        <button
          className="nat-tutorial__btn nat-tutorial__btn--skip"
          onClick={handleSkip}
        >
          Skip
        </button>
        <button
          className="nat-tutorial__btn nat-tutorial__btn--next"
          onClick={handleNext}
        >
          {isLastStep ? 'Get Started' : 'Next'}
        </button>
      </div>

      {/* Step counter */}
      <div className="nat-tutorial__counter">
        Step {currentStep + 1} of {tutorialSteps.length}
      </div>
    </div>
  );
}

// ============================================================================
// Hook for tutorial state management
// ============================================================================

export function useTutorialState() {
  const [showTutorial, setShowTutorial] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkTutorial = async () => {
      const completed = await isTutorialCompleted();
      setShowTutorial(!completed);
      setIsLoading(false);
    };

    checkTutorial();
  }, []);

  const completeTutorial = () => {
    setShowTutorial(false);
  };

  return { showTutorial, isLoading, completeTutorial };
}
