import { useState, useEffect, useRef } from 'preact/hooks';

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

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  toolCalls?: ToolCallInfo[];
  results?: PersonResult[];
}

interface PageContext {
  page_type?: string;
  person_name?: string;
  person_id?: string;
  list_name?: string;
  event_name?: string;
}

interface ChatProps {
  pageContext?: PageContext;
}

// Message types from background service worker
type BroadcastMessage =
  | { type: 'STREAMING_TEXT'; text: string; partial: string }
  | { type: 'STREAMING_TOOL_USE'; name: string; input: Record<string, unknown> }
  | { type: 'STREAMING_TOOL_RESULT'; result: string; isError: boolean }
  | { type: 'STREAMING_ERROR'; error: string; errorCode: string; retryAfter?: number }
  | { type: 'STREAMING_DONE'; response: string; toolCalls: ToolCallInfo[] }
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
          // Mark message as error
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageId
                ? {
                    ...msg,
                    isStreaming: false,
                    content: msg.content || `Error: ${message.error}`,
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

          // Clean up
          if (streamingMessageId) {
            toolResultsRef.current.delete(streamingMessageId);
          }
          setIsStreaming(false);
          setStreamingMessageId(null);
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

    // Send to background service worker
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'SUBMIT_QUERY',
        query: query.trim(),
        context: pageContext,
      });

      if (!response.success) {
        // Update message with error
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  isStreaming: false,
                  content: response.error || 'Failed to send query',
                }
              : msg
          )
        );
        setIsStreaming(false);
        setStreamingMessageId(null);
      }
    } catch (error) {
      // Handle extension context invalidated error
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                isStreaming: false,
                content: 'Connection error. Please refresh the page.',
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
    } catch {
      // Ignore errors when cancelling
    }
  };

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
    </div>
  );
}
