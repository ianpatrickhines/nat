/**
 * Undo Stack Management
 *
 * Tracks undoable actions taken by Nat during the current session.
 * Actions are stored in sessionStorage so they clear when the tab closes.
 */

// ============================================================================
// Types
// ============================================================================

/**
 * An action that can potentially be undone.
 * Not all actions are undoable - only those with clear inverse operations.
 */
export interface UndoableAction {
  /** Unique ID for this action */
  id: string;
  /** Timestamp when action was taken */
  timestamp: number;
  /** The tool that was called */
  toolName: string;
  /** The input parameters used */
  toolInput: Record<string, unknown>;
  /** Human-readable description of what happened */
  description: string;
  /** The type of undo operation (if undoable) */
  undoType: UndoType;
  /** Data needed to reverse the action */
  undoData: Record<string, unknown>;
}

/**
 * Types of undo operations supported
 */
export type UndoType =
  | 'delete_created'      // Delete something that was created
  | 'recreate_deleted'    // Recreate something that was deleted (if we have the data)
  | 'restore_updated'     // Restore previous values after an update
  | 'remove_from_list'    // Remove from a list (reverse of add_to_list)
  | 'add_to_list'         // Add back to a list (reverse of remove_from_list)
  | 'remove_tag'          // Remove a tag (reverse of add_tag)
  | 'add_tag'             // Add a tag back (reverse of remove_tag)
  | 'not_undoable';       // Action cannot be undone

/**
 * Mapping of tool names to their undo configurations
 */
interface UndoConfig {
  undoType: UndoType;
  description: (input: Record<string, unknown>) => string;
  undoData: (input: Record<string, unknown>, result?: unknown) => Record<string, unknown>;
}

// ============================================================================
// Tool Undo Configurations
// ============================================================================

/**
 * Configuration for how to undo each tool.
 * Only tools with clear reverse operations are included.
 */
const UNDO_CONFIGS: Record<string, UndoConfig> = {
  // Creating a signup can be undone by deleting it
  create_signup: {
    undoType: 'delete_created',
    description: (input) => `Created person ${input.first_name || ''} ${input.last_name || input.email || ''}`.trim(),
    undoData: (_input, result) => {
      // Result should contain the created signup's ID
      const data = result as { data?: { id?: string } } | undefined;
      return { signup_id: data?.data?.id };
    },
  },

  // Adding to a list can be undone by removing from the list
  add_to_list: {
    undoType: 'remove_from_list',
    description: (input) => `Added person ${input.person_id} to list ${input.list_id}`,
    undoData: (input) => ({
      person_id: input.person_id,
      list_id: input.list_id,
    }),
  },

  // Removing from a list can be undone by adding back
  remove_from_list: {
    undoType: 'add_to_list',
    description: (input) => `Removed person ${input.person_id} from list ${input.list_id}`,
    undoData: (input) => ({
      person_id: input.person_id,
      list_id: input.list_id,
    }),
  },

  // Adding a tag can be undone by removing it
  add_signup_tagging: {
    undoType: 'remove_tag',
    description: (input) => `Added tag "${input.tag_name || input.tag_id}" to person ${input.signup_id}`,
    undoData: (input, result) => {
      const data = result as { data?: { id?: string } } | undefined;
      return {
        signup_id: input.signup_id,
        tagging_id: data?.data?.id,
        tag_name: input.tag_name,
      };
    },
  },

  // Removing a tag can be undone by adding it back
  remove_signup_tagging: {
    undoType: 'add_tag',
    description: (input) => `Removed tag from person ${input.signup_id}`,
    undoData: (input) => ({
      signup_id: input.signup_id,
      tag_name: input.tag_name,
    }),
  },

  // Creating a contact can be undone by deleting it
  create_contact: {
    undoType: 'delete_created',
    description: (input) => `Created contact for person ${input.signup_id}`,
    undoData: (_input, result) => {
      const data = result as { data?: { id?: string } } | undefined;
      return { contact_id: data?.data?.id };
    },
  },

  // Creating a donation can be undone by deleting it
  create_donation: {
    undoType: 'delete_created',
    description: (input) => `Created donation of $${input.amount || '?'} for person ${input.donor_id}`,
    undoData: (_input, result) => {
      const data = result as { data?: { id?: string } } | undefined;
      return { donation_id: data?.data?.id };
    },
  },

  // Creating an event RSVP can be undone by deleting it
  create_event_rsvp: {
    undoType: 'delete_created',
    description: (input) => `Created RSVP for person ${input.person_id} to event ${input.event_id}`,
    undoData: (_input, result) => {
      const data = result as { data?: { id?: string } } | undefined;
      return { rsvp_id: data?.data?.id };
    },
  },

  // Note: update operations are complex to undo because we'd need to store
  // the previous state. For now, we mark them as not directly undoable,
  // but we could enhance this later with "restore previous values" support.
};

// ============================================================================
// Storage Key
// ============================================================================

const UNDO_STACK_KEY = 'nat_undo_stack';

// ============================================================================
// Undo Stack Functions
// ============================================================================

/**
 * Get the current undo stack from session storage
 */
export function getUndoStack(): UndoableAction[] {
  try {
    const data = sessionStorage.getItem(UNDO_STACK_KEY);
    if (!data) return [];
    return JSON.parse(data) as UndoableAction[];
  } catch {
    return [];
  }
}

/**
 * Save the undo stack to session storage
 */
function saveUndoStack(stack: UndoableAction[]): void {
  try {
    // Keep only the last 50 actions to prevent unbounded growth
    const trimmed = stack.slice(-50);
    sessionStorage.setItem(UNDO_STACK_KEY, JSON.stringify(trimmed));
  } catch {
    // Session storage might be full or disabled
    console.error('Failed to save undo stack');
  }
}

/**
 * Record an action that was just executed.
 * Returns the UndoableAction if it can be undone, null otherwise.
 */
export function recordAction(
  toolName: string,
  toolInput: Record<string, unknown>,
  result?: unknown
): UndoableAction | null {
  const config = UNDO_CONFIGS[toolName];

  // If we don't have an undo config for this tool, it's not undoable
  if (!config) {
    return null;
  }

  const action: UndoableAction = {
    id: `action-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    timestamp: Date.now(),
    toolName,
    toolInput,
    description: config.description(toolInput),
    undoType: config.undoType,
    undoData: config.undoData(toolInput, result),
  };

  // Add to stack
  const stack = getUndoStack();
  stack.push(action);
  saveUndoStack(stack);

  return action;
}

/**
 * Get the most recent undoable action
 */
export function getLastAction(): UndoableAction | null {
  const stack = getUndoStack();
  if (stack.length === 0) return null;
  return stack[stack.length - 1];
}

/**
 * Pop the most recent action from the stack (after it's been undone)
 */
export function popLastAction(): UndoableAction | null {
  const stack = getUndoStack();
  if (stack.length === 0) return null;
  const action = stack.pop();
  saveUndoStack(stack);
  return action || null;
}

/**
 * Clear the entire undo stack
 */
export function clearUndoStack(): void {
  try {
    sessionStorage.removeItem(UNDO_STACK_KEY);
  } catch {
    // Ignore errors
  }
}

/**
 * Get a human-readable description of what can be undone
 */
export function getUndoDescription(): string | null {
  const action = getLastAction();
  if (!action) return null;
  return action.description;
}

/**
 * Generate the reverse tool call for an action
 */
export function getUndoToolCall(action: UndoableAction): { toolName: string; toolInput: Record<string, unknown> } | null {
  switch (action.undoType) {
    case 'delete_created':
      // Need to call the appropriate delete tool
      if (action.toolName === 'create_signup' && action.undoData.signup_id) {
        return { toolName: 'delete_signup', toolInput: { id: action.undoData.signup_id } };
      }
      if (action.toolName === 'create_contact' && action.undoData.contact_id) {
        return { toolName: 'delete_contact', toolInput: { id: action.undoData.contact_id } };
      }
      if (action.toolName === 'create_donation' && action.undoData.donation_id) {
        return { toolName: 'delete_donation', toolInput: { id: action.undoData.donation_id } };
      }
      if (action.toolName === 'create_event_rsvp' && action.undoData.rsvp_id) {
        return { toolName: 'delete_event_rsvp', toolInput: { id: action.undoData.rsvp_id } };
      }
      break;

    case 'remove_from_list':
      return {
        toolName: 'remove_from_list',
        toolInput: {
          person_id: action.undoData.person_id,
          list_id: action.undoData.list_id,
        },
      };

    case 'add_to_list':
      return {
        toolName: 'add_to_list',
        toolInput: {
          person_id: action.undoData.person_id,
          list_id: action.undoData.list_id,
        },
      };

    case 'remove_tag':
      if (action.undoData.tagging_id) {
        return {
          toolName: 'remove_signup_tagging',
          toolInput: {
            signup_id: action.undoData.signup_id,
            id: action.undoData.tagging_id,
          },
        };
      }
      break;

    case 'add_tag':
      return {
        toolName: 'add_signup_tagging',
        toolInput: {
          signup_id: action.undoData.signup_id,
          tag_name: action.undoData.tag_name,
        },
      };

    case 'not_undoable':
    default:
      return null;
  }

  return null;
}

/**
 * Check if a tool action is one that we track for undo
 */
export function isUndoableToolName(toolName: string): boolean {
  return toolName in UNDO_CONFIGS;
}
