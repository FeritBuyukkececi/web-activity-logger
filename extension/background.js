/**
 * Background service worker for relaying messages from content script.
 * Stores events and exposes them for Playwright to consume.
 */

// Store captured events
const capturedEvents = [];

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'interaction') {
    const event = message.data;

    // Add tab info
    event.tabId = sender.tab?.id;
    event.tabUrl = sender.tab?.url;

    capturedEvents.push(event);

    // Notify any connected external listeners
    try {
      chrome.runtime.sendMessage({
        type: 'newInteraction',
        data: event
      });
    } catch (e) {
      // No external listeners connected
    }
  }

  return true;
});

// Expose events via external messaging (for Playwright)
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (message.type === 'getEvents') {
    sendResponse({ events: capturedEvents });
    return true;
  }

  if (message.type === 'clearEvents') {
    capturedEvents.length = 0;
    sendResponse({ success: true });
    return true;
  }

  if (message.type === 'getAndClearEvents') {
    const events = [...capturedEvents];
    capturedEvents.length = 0;
    sendResponse({ events });
    return true;
  }
});

// Also expose via simple runtime API that Playwright can access via page.evaluate
// This creates a global variable accessible from the page context
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === 'web-logger') {
    port.onMessage.addListener((message) => {
      if (message.type === 'getEvents') {
        port.postMessage({ events: capturedEvents });
      }

      if (message.type === 'clearEvents') {
        capturedEvents.length = 0;
        port.postMessage({ success: true });
      }

      if (message.type === 'getAndClearEvents') {
        const events = [...capturedEvents];
        capturedEvents.length = 0;
        port.postMessage({ events });
      }
    });
  }
});
