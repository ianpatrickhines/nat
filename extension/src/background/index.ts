// Background service worker for Nat Chrome extension
// Handles auth state, API connections, message passing, and SSE streaming

// ============================================================================
// Types
// ============================================================================

interface AuthState {
  isAuthenticated: boolean;
  userId: string | null;
  tenantId: string | null;
  nbConnected: boolean;
  nbNeedsReauth: boolean;
  subscriptionStatus: 'active' | 'trialing' | 'cancelled' | 'past_due' | 'unpaid' | null;
}

interface PageContext {
  page_type?: string;
  person_name?: string;
  person_id?: string;
  list_name?: string;
  event_name?: string;
}

interface QueryRequest {
  query: string;
  context?: PageContext;
}

interface SSEEvent {
  type: 'text' | 'tool_use' | 'tool_result' | 'error' | 'done';
  data: Record<string, unknown>;
}

interface ToolCallInfo {
  name: string;
  input: Record<string, unknown>;
}

interface StreamingState {
  isStreaming: boolean;
  abortController: AbortController | null;
  currentQuery: string | null;
  partialResponse: string;
  toolCalls: ToolCallInfo[];
}

// Message types from content scripts
type MessageType =
  | { type: 'GET_AUTH_STATE' }
  | { type: 'SET_AUTH_STATE'; authToken: string; userId: string; tenantId: string }
  | { type: 'CLEAR_AUTH_STATE' }
  | { type: 'SET_NB_CONNECTION'; nbConnected: boolean; nbNeedsReauth?: boolean }
  | { type: 'SET_SUBSCRIPTION_STATUS'; status: AuthState['subscriptionStatus'] }
  | { type: 'SUBMIT_QUERY'; query: string; context?: PageContext }
  | { type: 'CANCEL_QUERY' }
  | { type: 'GET_STREAMING_STATE' };

// Message types to content scripts
type BroadcastMessage =
  | { type: 'AUTH_STATE_CHANGED'; authState: AuthState }
  | { type: 'STREAMING_TEXT'; text: string; partial: string }
  | { type: 'STREAMING_TOOL_USE'; name: string; input: Record<string, unknown> }
  | { type: 'STREAMING_TOOL_RESULT'; result: string; isError: boolean }
  | { type: 'STREAMING_ERROR'; error: string; errorCode: string; retryAfter?: number }
  | { type: 'STREAMING_DONE'; response: string; toolCalls: ToolCallInfo[] }
  | { type: 'TOGGLE_SIDEBAR' };

// ============================================================================
// Configuration
// ============================================================================

// Streaming endpoint - Lambda Function URL for SSE (configured at build time)
const STREAMING_URL = 'https://streaming.nat.example.com'; // Lambda Function URL for SSE

// ============================================================================
// State Management
// ============================================================================

// Current streaming state (service workers are ephemeral, but this persists per "wakeup")
let streamingState: StreamingState = {
  isStreaming: false,
  abortController: null,
  currentQuery: null,
  partialResponse: '',
  toolCalls: [],
};

// ============================================================================
// Auth Token Management
// ============================================================================

/**
 * Get the current auth state from chrome.storage
 */
async function getAuthState(): Promise<AuthState> {
  return new Promise((resolve) => {
    chrome.storage.local.get([
      'authToken',
      'userId',
      'tenantId',
      'nbConnected',
      'nbNeedsReauth',
      'subscriptionStatus'
    ], (result) => {
      resolve({
        isAuthenticated: !!result.authToken,
        userId: result.userId || null,
        tenantId: result.tenantId || null,
        nbConnected: !!result.nbConnected,
        nbNeedsReauth: !!result.nbNeedsReauth,
        subscriptionStatus: result.subscriptionStatus || null,
      });
    });
  });
}

/**
 * Set auth credentials in chrome.storage
 */
async function setAuthState(authToken: string, userId: string, tenantId: string): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({
      authToken,
      userId,
      tenantId,
    }, () => resolve());
  });
}

/**
 * Clear all auth state from chrome.storage
 */
async function clearAuthState(): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.remove([
      'authToken',
      'userId',
      'tenantId',
      'nbConnected',
      'nbNeedsReauth',
      'subscriptionStatus'
    ], () => resolve());
  });
}

/**
 * Update NationBuilder connection state
 */
async function setNbConnection(nbConnected: boolean, nbNeedsReauth?: boolean): Promise<void> {
  return new Promise((resolve) => {
    const updates: Record<string, boolean> = { nbConnected };
    if (nbNeedsReauth !== undefined) {
      updates.nbNeedsReauth = nbNeedsReauth;
    }
    chrome.storage.local.set(updates, () => resolve());
  });
}

/**
 * Update subscription status
 */
async function setSubscriptionStatus(status: AuthState['subscriptionStatus']): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ subscriptionStatus: status }, () => resolve());
  });
}

// ============================================================================
// Broadcasting to Content Scripts
// ============================================================================

/**
 * Broadcast a message to all NationBuilder tabs
 */
async function broadcastToNbTabs(message: BroadcastMessage): Promise<void> {
  try {
    const tabs = await chrome.tabs.query({ url: '*://*.nationbuilder.com/*' });

    for (const tab of tabs) {
      if (tab.id) {
        try {
          await chrome.tabs.sendMessage(tab.id, message);
        } catch {
          // Tab might not have content script loaded yet, ignore
        }
      }
    }
  } catch (error) {
    console.error('Failed to broadcast to tabs:', error);
  }
}

/**
 * Notify all tabs of auth state change
 */
async function notifyAuthStateChanged(): Promise<void> {
  const authState = await getAuthState();
  await broadcastToNbTabs({ type: 'AUTH_STATE_CHANGED', authState });
}

// ============================================================================
// SSE Connection Management
// ============================================================================

/**
 * Parse an SSE event from a text chunk
 */
function parseSSEEvent(eventText: string): SSEEvent | null {
  const lines = eventText.trim().split('\n');
  let eventType = '';
  let dataStr = '';

  for (const line of lines) {
    if (line.startsWith('event: ')) {
      eventType = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      dataStr = line.slice(6);
    }
  }

  if (!eventType || !dataStr) {
    return null;
  }

  try {
    const data = JSON.parse(dataStr) as Record<string, unknown>;
    return { type: eventType as SSEEvent['type'], data };
  } catch {
    console.error('Failed to parse SSE data:', dataStr);
    return null;
  }
}

/**
 * Process SSE events from the streaming response
 */
async function processSSEStream(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';

  // Start keepalive alarm to prevent service worker termination during streaming
  chrome.alarms.create('keepalive', { delayInMinutes: 0.4 });

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by double newlines
      const events = buffer.split('\n\n');

      // Keep the last incomplete event in buffer
      buffer = events.pop() || '';

      for (const eventText of events) {
        if (!eventText.trim()) continue;

        const event = parseSSEEvent(eventText);
        if (!event) continue;

        await handleSSEEvent(event);
      }
    }

    // Process any remaining buffer
    if (buffer.trim()) {
      const event = parseSSEEvent(buffer);
      if (event) {
        await handleSSEEvent(event);
      }
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.log('SSE stream aborted');
    } else {
      console.error('SSE stream error:', error);
      await broadcastToNbTabs({
        type: 'STREAMING_ERROR',
        error: 'Connection to server lost',
        errorCode: 'CONNECTION_ERROR',
      });
    }
  } finally {
    streamingState.isStreaming = false;
    streamingState.abortController = null;
    // Clear keepalive alarm when streaming ends
    chrome.alarms.clear('keepalive');
  }
}

/**
 * Handle a single SSE event
 */
async function handleSSEEvent(event: SSEEvent): Promise<void> {
  switch (event.type) {
    case 'text': {
      const text = event.data.text as string;
      streamingState.partialResponse += text;
      await broadcastToNbTabs({
        type: 'STREAMING_TEXT',
        text,
        partial: streamingState.partialResponse,
      });
      break;
    }

    case 'tool_use': {
      const toolInfo: ToolCallInfo = {
        name: event.data.name as string,
        input: event.data.input as Record<string, unknown>,
      };
      streamingState.toolCalls.push(toolInfo);
      await broadcastToNbTabs({
        type: 'STREAMING_TOOL_USE',
        name: toolInfo.name,
        input: toolInfo.input,
      });
      break;
    }

    case 'tool_result': {
      await broadcastToNbTabs({
        type: 'STREAMING_TOOL_RESULT',
        result: event.data.result as string,
        isError: event.data.is_error as boolean,
      });
      break;
    }

    case 'error': {
      await broadcastToNbTabs({
        type: 'STREAMING_ERROR',
        error: event.data.error as string,
        errorCode: event.data.error_code as string,
        retryAfter: event.data.retry_after as number | undefined,
      });
      break;
    }

    case 'done': {
      const response = event.data.response as string || streamingState.partialResponse;
      const toolCalls = event.data.tool_calls as ToolCallInfo[] || streamingState.toolCalls;

      await broadcastToNbTabs({
        type: 'STREAMING_DONE',
        response,
        toolCalls,
      });

      // Reset streaming state
      streamingState.partialResponse = '';
      streamingState.toolCalls = [];
      streamingState.currentQuery = null;
      break;
    }
  }
}

/**
 * Submit a query to the streaming backend
 */
async function submitQuery(request: QueryRequest): Promise<{ success: boolean; error?: string }> {
  // Check if already streaming
  if (streamingState.isStreaming) {
    return { success: false, error: 'A query is already in progress' };
  }

  // Get auth state
  const authState = await getAuthState();

  if (!authState.isAuthenticated) {
    return { success: false, error: 'Not authenticated' };
  }

  if (!authState.nbConnected) {
    return { success: false, error: 'NationBuilder not connected' };
  }

  if (authState.nbNeedsReauth) {
    return { success: false, error: 'NationBuilder connection needs reauthorization' };
  }

  if (authState.subscriptionStatus !== 'active' && authState.subscriptionStatus !== 'trialing') {
    return { success: false, error: 'Subscription is not active' };
  }

  // Reset streaming state
  streamingState.isStreaming = true;
  streamingState.abortController = new AbortController();
  streamingState.currentQuery = request.query;
  streamingState.partialResponse = '';
  streamingState.toolCalls = [];

  try {
    // Get auth token for API call
    const { authToken } = await new Promise<{ authToken: string }>((resolve) => {
      chrome.storage.local.get(['authToken'], (result) => {
        resolve({ authToken: result.authToken || '' });
      });
    });

    // Make streaming request to Lambda Function URL
    const response = await fetch(STREAMING_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`,
        'X-Nat-User-Id': authState.userId || '',
        'X-Nat-Tenant-Id': authState.tenantId || '',
      },
      body: JSON.stringify({
        query: request.query,
        user_id: authState.userId,
        context: request.context || {},
      }),
      signal: streamingState.abortController.signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
      streamingState.isStreaming = false;
      streamingState.abortController = null;

      // Map HTTP status to error codes
      let errorCode = 'API_ERROR';
      if (response.status === 402) errorCode = 'PAYMENT_REQUIRED';
      else if (response.status === 403) errorCode = 'FORBIDDEN';
      else if (response.status === 429) errorCode = 'RATE_LIMIT_EXCEEDED';

      await broadcastToNbTabs({
        type: 'STREAMING_ERROR',
        error: (errorData as { error: string }).error,
        errorCode,
      });

      return { success: false, error: (errorData as { error: string }).error };
    }

    // Start processing the SSE stream
    if (response.body) {
      const reader = response.body.getReader();
      // Don't await - let it process in background
      processSSEStream(reader).catch(console.error);
    }

    return { success: true };
  } catch (error) {
    streamingState.isStreaming = false;
    streamingState.abortController = null;

    const errorMessage = error instanceof Error ? error.message : 'Unknown error';

    if (error instanceof Error && error.name !== 'AbortError') {
      await broadcastToNbTabs({
        type: 'STREAMING_ERROR',
        error: errorMessage,
        errorCode: 'NETWORK_ERROR',
      });
    }

    return { success: false, error: errorMessage };
  }
}

/**
 * Cancel the current streaming query
 */
function cancelQuery(): boolean {
  if (streamingState.abortController) {
    streamingState.abortController.abort();
    streamingState.isStreaming = false;
    streamingState.abortController = null;
    streamingState.currentQuery = null;
    streamingState.partialResponse = '';
    streamingState.toolCalls = [];
    return true;
  }
  return false;
}

// ============================================================================
// Message Handlers
// ============================================================================

/**
 * Handle messages from content scripts
 */
chrome.runtime.onMessage.addListener((
  message: MessageType,
  _sender: chrome.runtime.MessageSender,
  sendResponse: (response: unknown) => void
): boolean => {

  switch (message.type) {
    case 'GET_AUTH_STATE': {
      getAuthState().then((authState) => {
        sendResponse(authState);
      });
      return true; // Keep channel open for async response
    }

    case 'SET_AUTH_STATE': {
      setAuthState(message.authToken, message.userId, message.tenantId)
        .then(() => notifyAuthStateChanged())
        .then(() => sendResponse({ success: true }));
      return true;
    }

    case 'CLEAR_AUTH_STATE': {
      clearAuthState()
        .then(() => notifyAuthStateChanged())
        .then(() => sendResponse({ success: true }));
      return true;
    }

    case 'SET_NB_CONNECTION': {
      setNbConnection(message.nbConnected, message.nbNeedsReauth)
        .then(() => notifyAuthStateChanged())
        .then(() => sendResponse({ success: true }));
      return true;
    }

    case 'SET_SUBSCRIPTION_STATUS': {
      setSubscriptionStatus(message.status)
        .then(() => notifyAuthStateChanged())
        .then(() => sendResponse({ success: true }));
      return true;
    }

    case 'SUBMIT_QUERY': {
      submitQuery({ query: message.query, context: message.context })
        .then((result) => sendResponse(result));
      return true;
    }

    case 'CANCEL_QUERY': {
      const cancelled = cancelQuery();
      sendResponse({ success: cancelled });
      return false;
    }

    case 'GET_STREAMING_STATE': {
      sendResponse({
        isStreaming: streamingState.isStreaming,
        currentQuery: streamingState.currentQuery,
        partialResponse: streamingState.partialResponse,
        toolCalls: streamingState.toolCalls,
      });
      return false;
    }
  }

  return false;
});

// ============================================================================
// Extension Lifecycle
// ============================================================================

// Listen for extension install/update
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Nat extension installed');
    // Could open onboarding page here
  } else if (details.reason === 'update') {
    console.log('Nat extension updated to version', chrome.runtime.getManifest().version);
  }
});

// Extension action click handler (browser toolbar icon)
chrome.action.onClicked.addListener((tab) => {
  // Send message to content script to toggle sidebar
  if (tab.id) {
    chrome.tabs.sendMessage(tab.id, { type: 'TOGGLE_SIDEBAR' } as BroadcastMessage);
  }
});

// Listen for storage changes to sync state
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local') {
    // If any auth-related field changed, notify all tabs
    const authFields = ['authToken', 'userId', 'tenantId', 'nbConnected', 'nbNeedsReauth', 'subscriptionStatus'];
    const hasAuthChange = authFields.some((field) => field in changes);

    if (hasAuthChange) {
      notifyAuthStateChanged().catch(console.error);
    }
  }
});

// Keep service worker alive during streaming (Manifest V3 service workers can be killed)
// We use alarms as a keepalive mechanism
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepalive' && streamingState.isStreaming) {
    // Reset the alarm to keep the service worker alive
    chrome.alarms.create('keepalive', { delayInMinutes: 0.4 }); // ~25 seconds
  } else if (alarm.name === 'keepalive') {
    // Streaming finished, clear the alarm
    chrome.alarms.clear('keepalive');
  }
});

// Export for potential testing (though service workers don't really support module exports)
// These would be used by any testing framework
export type { AuthState, PageContext, QueryRequest, SSEEvent, StreamingState, MessageType, BroadcastMessage };
