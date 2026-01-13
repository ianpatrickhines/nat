// Confirmation dialog component for destructive actions
import { useCallback } from 'preact/hooks';

// ============================================================================
// Types
// ============================================================================

export interface ConfirmationRequest {
  toolId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  summary: string;
}

interface ConfirmationDialogProps {
  confirmation: ConfirmationRequest;
  onConfirm: (toolId: string) => void;
  onCancel: () => void;
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get a user-friendly title for the action type
 */
function getActionTitle(toolName: string): string {
  if (toolName.startsWith('delete_')) {
    return 'Confirm Delete';
  }
  if (toolName === 'remove_from_list') {
    return 'Confirm Removal';
  }
  if (toolName.startsWith('update_')) {
    return 'Confirm Update';
  }
  return 'Confirm Action';
}

/**
 * Get warning message based on action type
 */
function getWarningMessage(toolName: string): string {
  if (toolName.startsWith('delete_')) {
    return 'This action cannot be undone. The record will be permanently deleted.';
  }
  if (toolName === 'remove_from_list') {
    return 'This will remove the person from the list. You can add them back later if needed.';
  }
  if (toolName.startsWith('update_')) {
    return 'This will modify the existing record with the new values.';
  }
  return 'Are you sure you want to proceed with this action?';
}

/**
 * Get icon for action type
 */
function getActionIcon(toolName: string): 'delete' | 'warning' | 'info' {
  if (toolName.startsWith('delete_') || toolName === 'remove_from_list') {
    return 'delete';
  }
  if (toolName.startsWith('update_')) {
    return 'warning';
  }
  return 'info';
}

// ============================================================================
// Component
// ============================================================================

export function ConfirmationDialog({
  confirmation,
  onConfirm,
  onCancel,
}: ConfirmationDialogProps) {
  const handleConfirm = useCallback(() => {
    onConfirm(confirmation.toolId);
  }, [confirmation.toolId, onConfirm]);

  const handleCancel = useCallback(() => {
    onCancel();
  }, [onCancel]);

  // Handle keyboard events
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleCancel();
    } else if (e.key === 'Enter') {
      handleConfirm();
    }
  }, [handleCancel, handleConfirm]);

  const iconType = getActionIcon(confirmation.toolName);
  const title = getActionTitle(confirmation.toolName);
  const warningMessage = getWarningMessage(confirmation.toolName);

  return (
    <div
      className="nat-confirmation-overlay"
      onClick={handleCancel}
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="nat-confirmation-title"
    >
      <div
        className="nat-confirmation-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Icon */}
        <div className={`nat-confirmation__icon nat-confirmation__icon--${iconType}`}>
          {iconType === 'delete' && (
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
          )}
          {iconType === 'warning' && (
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
          )}
          {iconType === 'info' && (
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          )}
        </div>

        {/* Title */}
        <h3 id="nat-confirmation-title" className="nat-confirmation__title">
          {title}
        </h3>

        {/* Summary */}
        <p className="nat-confirmation__summary">
          {confirmation.summary}
        </p>

        {/* Warning message */}
        <p className="nat-confirmation__warning">
          {warningMessage}
        </p>

        {/* Buttons */}
        <div className="nat-confirmation__buttons">
          <button
            type="button"
            className="nat-confirmation__btn nat-confirmation__btn--cancel"
            onClick={handleCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className={`nat-confirmation__btn nat-confirmation__btn--confirm nat-confirmation__btn--${iconType}`}
            onClick={handleConfirm}
            autoFocus
          >
            {iconType === 'delete' ? 'Delete' : iconType === 'warning' ? 'Update' : 'Proceed'}
          </button>
        </div>
      </div>
    </div>
  );
}
