import { useState, useEffect, useRef, useCallback } from 'preact/hooks';
import { PageContext } from '../utils/pageContext';
import { ConfirmationDialog, ConfirmationRequest } from './ConfirmationDialog';
import { ErrorMessage } from './ErrorMessage';
import {
  recordAction,
  popLastAction,
  getUndoStack,
  isUndoableToolName,
  UndoableAction,
} from '../utils/undoStack';

// ============================================================================
// Types
// ============================================================================

interface ToolCallInfo {
  name: string;
  input: Record<string, unknown>;
}

interface PersonResult {
  name?: string;
  first_name?: string;
  last_name?: string;
  city_district?: string;
  state_above_abbrev?: string;
  id?: number;
  nationbuilder_url?: string;
}

interface ErrorDetails {
  errorCode: string;
  error?: string;
  retryAfter?: number;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  toolCalls?: ToolCallInfo[];
  results?: PersonResult[];
  /** Error details for displaying user-friendly error messages */
  errorDetails?: ErrorDetails;
}

interface ChatProps {
  pageContext?: PageContext | null;
}

// Message types from background service worker
type BroadcastMessage =
  | { type: 'STREAMING_TEXT'; text: string; partial: string }
  | { type: 'STREAMING_TOOL_USE'; name: string; input: Record<string, unknown> }
  | { type: 'STREAMING_TOOL_RESULT'; result: string; isError: boolean }
  | { type: 'STREAMING_ERROR'; error: string; errorCode: string; retryAfter?: number }
  | { type: 'STREAMING_DONE'; response: string; toolCalls: ToolCallInfo[]; toolResults?: Record<string, unknown>[] }
  | { type: 'STREAMING_CONFIRMATION_REQUIRED'; confirmation: ConfirmationRequest }
  | { type: 'STREAMING_UNDO_COMPLETE'; action: UndoableAction; description: string }
  | { type: 'AUTH_STATE_CHANGED' }
  | { type: 'TOGGLE_SIDEBAR' };

// ============================================================================
// Utility Functions
// ============================================================================

function generateId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Format location string from person data
 */
function formatLocation(person: PersonResult): string {
  const parts: string[] = [];
  if (person.city_district) parts.push(person.city_district);
  if (person.state_above_abbrev) parts.push(person.state_above_abbrev);
  return parts.join(', ');
}

/**
 * Get display name from person data
 */
function getDisplayName(person: PersonResult): string {
  if (person.name) return person.name;
  const parts: string[] = [];
  if (person.first_name) parts.push(person.first_name);
  if (person.last_name) parts.push(person.last_name);
  return parts.join(' ') || 'Unknown';
}

// ============================================================================
// Chat Component
// ============================================================================

export function Chat({ pageContext }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<ConfirmationRequest | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const toolResultsRef = useRef<Map<string, PersonResult[]>>(new Map());

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Listen for messages from background service worker
  useEffect(() => {
    const handleMessage = (message: BroadcastMessage) => {
      switch (message.type) {
        case 'STREAMING_TEXT': {
          // Update the streaming message with new text
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageId
                ? { ...msg, content: message.partial }
                : msg
            )
          );
          break;
        }

        case 'STREAMING_TOOL_USE': {
          // Track tool use - will update when we get results
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageId
                ? {
                    ...msg,
                    toolCalls: [
                      ...(msg.toolCalls || []),
                      { name: message.name, input: message.input },
                    ],
                  }
                : msg
            )
          );
          break;
        }

        case 'STREAMING_TOOL_RESULT': {
          // Try to parse person results from tool result
          try {
            const resultData = JSON.parse(message.result);
            if (resultData && typeof resultData === 'object') {
              // Look for results array in various formats
              let personResults: PersonResult[] = [];

              if (Array.isArray(resultData.results)) {
                personResults = resultData.results;
              } else if (Array.isArray(resultData.people)) {
                personResults = resultData.people;
              } else if (Array.isArray(resultData)) {
                personResults = resultData;
              } else if (resultData.id && (resultData.name || resultData.first_name)) {
                // Single person result
                personResults = [resultData];
              }

              if (personResults.length > 0 && streamingMessageId) {
                // Store results for this message
                const currentResults = toolResultsRef.current.get(streamingMessageId) || [];
                toolResultsRef.current.set(streamingMessageId, [...currentResults, ...personResults]);
              }
            }
          } catch {
            // Not JSON or doesn't contain person data, ignore
          }
          break;
        }

        case 'STREAMING_ERROR': {
          // Mark message as error with user-friendly error info
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageId
                ? {
                    ...msg,
                    isStreaming: false,
                    // Keep any partial content, but store error details for display
                    content: msg.content || '',
                    errorDetails: {
                      errorCode: message.errorCode,
                      error: message.error,
                      retryAfter: message.retryAfter,
                    },
                  }
                : msg
            )
          );
          setIsStreaming(false);
          setStreamingMessageId(null);
          break;
        }

        case 'STREAMING_DONE': {
          // Finalize the message
          const finalResults = streamingMessageId
            ? toolResultsRef.current.get(streamingMessageId) || []
            : [];

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageId
                ? {
                    ...msg,
                    isStreaming: false,
                    content: message.response,
                    toolCalls: message.toolCalls,
                    results: finalResults.length > 0 ? finalResults : undefined,
                  }
                : msg
            )
          );

          // Record undoable actions for the undo stack
          // Tool results may be passed from backend for recording undo data
          if (message.toolCalls && message.toolCalls.length > 0) {
            const toolResults = message.toolResults || [];
            message.toolCalls.forEach((tc, idx) => {
              if (isUndoableToolName(tc.name)) {
                recordAction(tc.name, tc.input, toolResults[idx]);
              }
            });
          }

          // Clean up
          if (streamingMessageId) {
            toolResultsRef.current.delete(streamingMessageId);
          }
          setIsStreaming(false);
          setStreamingMessageId(null);
          setPendingConfirmation(null);
          break;
        }

        case 'STREAMING_CONFIRMATION_REQUIRED': {
          // Show confirmation dialog
          setPendingConfirmation(message.confirmation);
          // Update message to show waiting state
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageId
                ? {
                    ...msg,
                    content: msg.content || 'Waiting for confirmation...',
                  }
                : msg
            )
          );
          break;
        }

        case 'STREAMING_UNDO_COMPLETE': {
          // An undo operation completed - remove the action from the stack
          popLastAction();
          // The response text will come through STREAMING_DONE
          break;
        }
      }
    };

    // Add listener for messages from background
    chrome.runtime.onMessage.addListener(handleMessage);

    return () => {
      chrome.runtime.onMessage.removeListener(handleMessage);
    };
  }, [streamingMessageId]);

  // Submit query to background service worker
  const submitQuery = async (query: string) => {
    if (!query.trim() || isStreaming) return;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: query.trim(),
      timestamp: new Date(),
    };

    // Create placeholder for assistant message
    const assistantMessageId = generateId();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInputValue('');
    setIsStreaming(true);
    setStreamingMessageId(assistantMessageId);

    // Send to background service worker with page context and undo stack
    // The undo stack is passed so the backend can detect "undo" queries
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'SUBMIT_QUERY',
        query: query.trim(),
        context: pageContext || undefined,
        undoStack: getUndoStack(),
      });

      if (!response.success) {
        // Update message with error - use error details for user-friendly display
        // Map common submission errors to error codes
        let errorCode = 'UNKNOWN_ERROR';
        const errorMsg = response.error || '';

        if (errorMsg.includes('Not authenticated')) {
          errorCode = 'UNAUTHORIZED';
        } else if (errorMsg.includes('NationBuilder not connected')) {
          errorCode = 'NB_NOT_CONNECTED';
        } else if (errorMsg.includes('reauthorization')) {
          errorCode = 'NB_NEEDS_REAUTH';
        } else if (errorMsg.includes('Subscription is not active')) {
          errorCode = 'SUBSCRIPTION_INACTIVE';
        } else if (errorMsg.includes('query is already in progress')) {
          errorCode = 'RATE_LIMIT_EXCEEDED';
        }

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  isStreaming: false,
                  content: '',
                  errorDetails: {
                    errorCode,
                    error: errorMsg,
                  },
                }
              : msg
          )
        );
        setIsStreaming(false);
        setStreamingMessageId(null);
      }
    } catch (error) {
      // Handle extension context invalidated error or network errors
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                isStreaming: false,
                content: '',
                errorDetails: {
                  errorCode: 'CONNECTION_ERROR',
                  error: error instanceof Error ? error.message : 'Connection error',
                },
              }
            : msg
        )
      );
      setIsStreaming(false);
      setStreamingMessageId(null);
    }
  };

  // Handle form submit
  const handleSubmit = (e: Event) => {
    e.preventDefault();
    submitQuery(inputValue);
  };

  // Handle Enter key (submit on Enter, newline on Shift+Enter)
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitQuery(inputValue);
    }
  };

  // Cancel current streaming query
  const cancelQuery = async () => {
    try {
      await chrome.runtime.sendMessage({ type: 'CANCEL_QUERY' });

      // Update streaming message
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamingMessageId
            ? { ...msg, isStreaming: false, content: msg.content || 'Cancelled' }
            : msg
        )
      );

      setIsStreaming(false);
      setStreamingMessageId(null);
      setPendingConfirmation(null);
    } catch {
      // Ignore errors when cancelling
    }
  };

  // Handle confirmation of destructive action
  const handleConfirmAction = useCallback(async (toolId: string) => {
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'CONFIRM_ACTION',
        toolId,
      });

      if (!response.success) {
        // Show error in current message
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === streamingMessageId
              ? {
                  ...msg,
                  content: response.error || 'Failed to confirm action',
                }
              : msg
          )
        );
      }

      // Clear pending confirmation - the response will come through streaming
      setPendingConfirmation(null);
      setIsStreaming(true);
    } catch (error) {
      console.error('Failed to confirm action:', error);
      setPendingConfirmation(null);
    }
  }, [streamingMessageId]);

  // Handle rejection of destructive action
  const handleRejectAction = useCallback(async () => {
    try {
      await chrome.runtime.sendMessage({ type: 'REJECT_ACTION' });
      setPendingConfirmation(null);
      setIsStreaming(false);
      setStreamingMessageId(null);
    } catch (error) {
      console.error('Failed to reject action:', error);
      setPendingConfirmation(null);
    }
  }, []);

  return (
    <div className="nat-chat">
      {/* Messages container */}
      <div className="nat-chat__messages">
        {messages.length === 0 ? (
          <div className="nat-chat__empty">
            <p className="nat-chat__empty-title">Ask Nat anything</p>
            <p className="nat-chat__empty-hint">
              Try "Who are my top donors?" or "Find people in Austin"
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`nat-chat__message nat-chat__message--${message.role}`}
            >
              {/* Error message display */}
              {message.errorDetails ? (
                <ErrorMessage
                  errorCode={message.errorDetails.errorCode}
                  error={message.errorDetails.error}
                  retryAfter={message.errorDetails.retryAfter}
                />
              ) : (
                <>
                  <div className="nat-chat__message-content">
                    {message.content}
                    {message.isStreaming && (
                      <span className="nat-chat__typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                      </span>
                    )}
                  </div>

                  {/* Person results display */}
                  {message.results && message.results.length > 0 && (
                    <div className="nat-chat__results">
                      {message.results.slice(0, 10).map((person, idx) => (
                        <div key={idx} className="nat-chat__result">
                          <span className="nat-chat__result-name">
                            {getDisplayName(person)}
                          </span>
                          {formatLocation(person) && (
                            <span className="nat-chat__result-location">
                              {formatLocation(person)}
                            </span>
                          )}
                          {person.id && (
                            <a
                              href={`https://${window.location.hostname}/admin/signups/${person.id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="nat-chat__result-link"
                            >
                              View Profile
                            </a>
                          )}
                        </div>
                      ))}
                      {message.results.length > 10 && (
                        <div className="nat-chat__results-more">
                          +{message.results.length - 10} more results
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form className="nat-chat__input-area" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className="nat-chat__input"
          value={inputValue}
          onInput={(e) => setInputValue((e.target as HTMLTextAreaElement).value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Nat a question..."
          disabled={isStreaming}
          rows={1}
        />
        {isStreaming ? (
          <button
            type="button"
            className="nat-chat__cancel-btn"
            onClick={cancelQuery}
            title="Cancel"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="nat-chat__send-btn"
            disabled={!inputValue.trim()}
            title="Send (Enter)"
          >
            Send
          </button>
        )}
      </form>

      {/* Confirmation dialog */}
      {pendingConfirmation && (
        <ConfirmationDialog
          confirmation={pendingConfirmation}
          onConfirm={handleConfirmAction}
          onCancel={handleRejectAction}
        />
      )}
    </div>
  );
}
