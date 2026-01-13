// Background service worker for Nat Chrome extension
// Handles auth state, API connections, and message passing

// Listen for extension install/update
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Nat extension installed');
  } else if (details.reason === 'update') {
    console.log('Nat extension updated to version', chrome.runtime.getManifest().version);
  }
});

// Message handler for content script communication
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'GET_AUTH_STATE') {
    // Return current auth state from storage
    chrome.storage.local.get(['authToken', 'userId', 'tenantId'], (result) => {
      sendResponse({
        isAuthenticated: !!result.authToken,
        userId: result.userId || null,
        tenantId: result.tenantId || null,
      });
    });
    return true; // Keep channel open for async response
  }

  if (message.type === 'SET_AUTH_STATE') {
    // Store auth state
    chrome.storage.local.set({
      authToken: message.authToken,
      userId: message.userId,
      tenantId: message.tenantId,
    }, () => {
      sendResponse({ success: true });
    });
    return true;
  }

  if (message.type === 'CLEAR_AUTH_STATE') {
    // Clear auth state
    chrome.storage.local.remove(['authToken', 'userId', 'tenantId'], () => {
      sendResponse({ success: true });
    });
    return true;
  }

  return false;
});

// Extension action click handler (browser toolbar icon)
chrome.action.onClicked.addListener((tab) => {
  // Send message to content script to toggle sidebar
  if (tab.id) {
    chrome.tabs.sendMessage(tab.id, { type: 'TOGGLE_SIDEBAR' });
  }
});
