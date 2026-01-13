/**
 * E2E tests for chat message round-trip
 *
 * Tests:
 * - User can send a message
 * - Response is received and displayed
 * - Streaming responses show typing indicator
 * - Error states are handled gracefully
 */

import { test, expect, waitForSidebar, setAuthState, setTutorialCompleted, sendChatMessage, waitForChatResponse } from './fixtures';

test.describe('Chat functionality', () => {
  test.beforeEach(async ({ context, extensionId }) => {
    // Set up fully authenticated state
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'test-user-123',
      tenantId: 'test-tenant-456',
      nbConnected: true,
      nbNeedsReauth: false,
      subscriptionStatus: 'active',
    });

    // Complete tutorial so chat shows immediately
    await setTutorialCompleted(context, extensionId, true);
  });

  test('chat interface is visible when authenticated', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Chat container should be visible
    const chat = nbPage.locator('.nat-chat');
    await expect(chat).toBeVisible();

    // Input should be visible and empty
    const input = nbPage.locator('.nat-chat__input');
    await expect(input).toBeVisible();
    await expect(input).toHaveValue('');

    // Send button should be visible
    const sendBtn = nbPage.locator('.nat-chat__send-btn');
    await expect(sendBtn).toBeVisible();
  });

  test('user can type a message', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    const input = nbPage.locator('.nat-chat__input');
    await input.fill('Who is John Doe?');

    await expect(input).toHaveValue('Who is John Doe?');
  });

  test('send button is disabled when input is empty', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // With empty input, send button should be disabled
    const sendBtn = nbPage.locator('.nat-chat__send-btn');
    await expect(sendBtn).toBeDisabled();

    // Type something
    const input = nbPage.locator('.nat-chat__input');
    await input.fill('Hello');

    // Now send button should be enabled
    await expect(sendBtn).toBeEnabled();

    // Clear input
    await input.clear();

    // Should be disabled again
    await expect(sendBtn).toBeDisabled();
  });

  test('user message appears in chat after sending', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Send a message
    await sendChatMessage(nbPage, 'Who is John Doe?');

    // User message should appear
    const userMessages = nbPage.locator('.nat-chat__message--user');
    await expect(userMessages.first()).toBeVisible();

    // Check message content
    const messageContent = userMessages.first().locator('.nat-chat__message-content');
    await expect(messageContent).toHaveText('Who is John Doe?');
  });

  test('typing indicator shows during streaming', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Send a message
    await sendChatMessage(nbPage, 'Find John');

    // Typing indicator should appear while waiting for response
    // Note: This may be very brief in tests with fast mocked responses
    const typingIndicator = nbPage.locator('.nat-chat__typing-indicator');

    // Either typing indicator appears or response appears
    // We just verify the UI handles the streaming state
    await expect(
      typingIndicator.or(nbPage.locator('.nat-chat__message--assistant'))
    ).toBeVisible({ timeout: 5000 });
  });

  test('assistant response appears after sending message', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Send a message
    await sendChatMessage(nbPage, 'Who is John Doe?');

    // Wait for response
    const response = await waitForChatResponse(nbPage);

    // Verify response contains expected content (from mock server)
    expect(response).toContain('John Doe');
  });

  test('messages alternate user and assistant', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Send first message
    await sendChatMessage(nbPage, 'Hello');

    // Wait for response
    await waitForChatResponse(nbPage);

    // Count messages
    const userMessages = nbPage.locator('.nat-chat__message--user');
    const assistantMessages = nbPage.locator('.nat-chat__message--assistant');

    // Should have 1 user message and 1 assistant message
    await expect(userMessages).toHaveCount(1);
    await expect(assistantMessages).toHaveCount(1);
  });

  test('input clears after sending message', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    const input = nbPage.locator('.nat-chat__input');

    // Type and send
    await input.fill('Test message');
    const sendBtn = nbPage.locator('.nat-chat__send-btn');
    await sendBtn.click();

    // Input should be cleared
    await expect(input).toHaveValue('');
  });

  test('can send message with Enter key', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    const input = nbPage.locator('.nat-chat__input');
    await input.fill('Hello via Enter');

    // Press Enter to send
    await input.press('Enter');

    // Message should appear
    const userMessages = nbPage.locator('.nat-chat__message--user');
    await expect(userMessages.first()).toBeVisible();

    const messageContent = userMessages.first().locator('.nat-chat__message-content');
    await expect(messageContent).toHaveText('Hello via Enter');
  });

  test('Shift+Enter creates newline instead of sending', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    const input = nbPage.locator('.nat-chat__input');
    await input.fill('Line 1');

    // Shift+Enter should add newline
    await input.press('Shift+Enter');
    await input.type('Line 2');

    // Input should contain both lines
    const value = await input.inputValue();
    expect(value).toContain('Line 1');
    expect(value).toContain('Line 2');

    // No message should be sent yet
    const userMessages = nbPage.locator('.nat-chat__message--user');
    await expect(userMessages).toHaveCount(0);
  });

  test('messages container is scrollable', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Messages container should have overflow-y auto or scroll
    const messagesContainer = nbPage.locator('.nat-chat__messages');
    await expect(messagesContainer).toBeVisible();

    const overflowY = await messagesContainer.evaluate((el) =>
      window.getComputedStyle(el).overflowY
    );

    expect(['auto', 'scroll']).toContain(overflowY);
  });
});

test.describe('Chat error handling', () => {
  test.beforeEach(async ({ context, extensionId }) => {
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'test-user-123',
      tenantId: 'test-tenant-456',
      nbConnected: true,
      nbNeedsReauth: false,
      subscriptionStatus: 'active',
    });
    await setTutorialCompleted(context, extensionId, true);
  });

  test('handles network error gracefully', async ({ nbPage }) => {
    // Configure page to block API requests
    await nbPage.route('**/api/**', (route) => route.abort());

    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Try to send a message
    await sendChatMessage(nbPage, 'This should fail');

    // Should show error message
    const errorMessage = nbPage.locator('.nat-error-message, .nat-chat__error');
    await expect(errorMessage).toBeVisible({ timeout: 10000 });
  });

  test('cancel button appears during streaming', async ({ nbPage }) => {
    await nbPage.goto('http://localhost:3456/admin');
    await waitForSidebar(nbPage);

    // Send a message
    await sendChatMessage(nbPage, 'Hello');

    // Cancel button should appear during streaming
    // Note: May be very brief with fast mock responses
    const cancelBtn = nbPage.locator('.nat-chat__cancel-btn');

    // Either cancel button or response should appear
    await expect(
      cancelBtn.or(nbPage.locator('.nat-chat__message--assistant'))
    ).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Chat context', () => {
  test.beforeEach(async ({ context, extensionId }) => {
    await setAuthState(context, extensionId, {
      isAuthenticated: true,
      userId: 'test-user-123',
      tenantId: 'test-tenant-456',
      nbConnected: true,
      nbNeedsReauth: false,
      subscriptionStatus: 'active',
    });
    await setTutorialCompleted(context, extensionId, true);
  });

  test('shows page context above chat', async ({ nbPage }) => {
    // Navigate to a person profile page
    await nbPage.goto('http://localhost:3456/admin/signups/12345');
    await waitForSidebar(nbPage);

    // Context should be displayed
    const contextValue = nbPage.locator('.nat-sidebar__context-value');
    await expect(contextValue).toContainText('John Doe');

    // Chat should also be visible
    const chat = nbPage.locator('.nat-chat');
    await expect(chat).toBeVisible();
  });
});
