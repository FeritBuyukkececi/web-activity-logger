/**
 * Content script for capturing DOM interactions.
 * Captures: click, input, change, submit events.
 * Uses MutationObserver to track dynamically added elements.
 */

(function() {
  'use strict';

  const MAX_INNER_TEXT_LENGTH = 100;
  const CAPTURED_EVENTS = ['click', 'input', 'change', 'submit'];

  /**
   * Generate a unique CSS selector for an element.
   * Priority: ID > tag.classes > tag:nth-child(n)
   */
  function generateSelector(element) {
    if (!element || !element.tagName) {
      return null;
    }

    const tagName = element.tagName.toLowerCase();

    // Priority 1: ID selector
    if (element.id) {
      return `#${element.id}`;
    }

    // Priority 2: Tag + class selector
    if (element.className && typeof element.className === 'string') {
      const classes = element.className.trim().split(/\s+/).filter(c => c);
      if (classes.length > 0) {
        return `${tagName}.${classes.join('.')}`;
      }
    }

    // Priority 3: nth-child fallback
    let index = 1;
    if (element.parentElement) {
      const siblings = Array.from(element.parentElement.children);
      const sameTagSiblings = siblings.filter(s => s.tagName === element.tagName);
      index = sameTagSiblings.indexOf(element) + 1;
    }
    return `${tagName}:nth-child(${index})`;
  }

  /**
   * Extract relevant attributes from an element.
   */
  function getAttributes(element) {
    const attrs = {};
    const relevantAttrs = ['id', 'class', 'name', 'type', 'href', 'src', 'value', 'placeholder', 'data-testid'];

    for (const attr of relevantAttrs) {
      if (element.hasAttribute(attr)) {
        attrs[attr] = element.getAttribute(attr);
      }
    }

    return attrs;
  }

  /**
   * Get truncated innerText of an element.
   */
  function getInnerText(element) {
    const text = element.innerText || '';
    if (text.length > MAX_INNER_TEXT_LENGTH) {
      return text.substring(0, MAX_INNER_TEXT_LENGTH) + '...';
    }
    return text;
  }

  /**
   * Get input value, masking password fields.
   */
  function getInputValue(element) {
    if (element.type === 'password') {
      return null;
    }
    return element.value || null;
  }

  /**
   * Collect all form field values for a submit event.
   */
  function getFormValues(form) {
    const values = {};
    const formData = new FormData(form);

    for (const [name, value] of formData.entries()) {
      // Check if this is a password field
      const field = form.querySelector(`[name="${name}"]`);
      if (field && field.type === 'password') {
        values[name] = '[REDACTED]';
      } else {
        values[name] = value;
      }
    }

    return values;
  }

  /**
   * Create an interaction log entry.
   */
  function createLogEntry(eventType, element, extraData = {}) {
    return {
      timestamp: Date.now(),
      type: 'interaction',
      event: eventType,
      selector: generateSelector(element),
      tagName: element.tagName,
      attributes: getAttributes(element),
      value: null,
      innerText: getInnerText(element),
      url: window.location.href,
      ...extraData
    };
  }

  /**
   * Send event to background script and expose to page for Playwright.
   */
  function sendEvent(logEntry) {
    // Send to background script
    try {
      chrome.runtime.sendMessage({
        type: 'interaction',
        data: logEntry
      });
    } catch (e) {
      // Extension context may be invalidated
      console.debug('Web Logger: Could not send event', e);
    }

    // Also log to console for Playwright to capture
    console.log('WEB_LOGGER_EVENT:' + JSON.stringify(logEntry));

    // And expose via window variable for polling
    try {
      if (typeof window.__webLoggerEvents__ === 'undefined') {
        window.__webLoggerEvents__ = [];
      }
      window.__webLoggerEvents__.push(logEntry);
    } catch (e) {
      // Content script isolation may prevent this
    }
  }

  /**
   * Handle click events.
   */
  function handleClick(event) {
    const element = event.target;
    const logEntry = createLogEntry('click', element);
    sendEvent(logEntry);
  }

  /**
   * Handle input events.
   */
  function handleInput(event) {
    const element = event.target;
    const logEntry = createLogEntry('input', element, {
      value: getInputValue(element)
    });
    sendEvent(logEntry);
  }

  /**
   * Handle change events.
   */
  function handleChange(event) {
    const element = event.target;
    const logEntry = createLogEntry('change', element, {
      value: getInputValue(element)
    });
    sendEvent(logEntry);
  }

  /**
   * Handle submit events.
   */
  function handleSubmit(event) {
    const form = event.target;
    const logEntry = createLogEntry('submit', form, {
      formValues: getFormValues(form)
    });
    sendEvent(logEntry);
  }

  /**
   * Attach event listeners to an element.
   */
  function attachListeners(element) {
    // Only attach to interactive elements for click
    const interactiveSelector = 'a, button, input, select, textarea, [onclick], [role="button"], [tabindex]';

    if (element.matches && element.matches(interactiveSelector)) {
      element.addEventListener('click', handleClick, { capture: true, passive: true });
    }

    // Input and change events for form elements
    if (element.matches && element.matches('input, select, textarea')) {
      element.addEventListener('input', handleInput, { capture: true, passive: true });
      element.addEventListener('change', handleChange, { capture: true, passive: true });
    }

    // Submit events for forms
    if (element.tagName === 'FORM') {
      element.addEventListener('submit', handleSubmit, { capture: true, passive: true });
    }
  }

  /**
   * Initialize listeners on existing elements.
   */
  function initializeListeners() {
    // Attach to document for bubbling events (more efficient)
    document.addEventListener('click', handleClick, { capture: true, passive: true });
    document.addEventListener('input', handleInput, { capture: true, passive: true });
    document.addEventListener('change', handleChange, { capture: true, passive: true });
    document.addEventListener('submit', handleSubmit, { capture: true, passive: true });
  }

  /**
   * Set up MutationObserver for dynamically added elements.
   */
  function setupMutationObserver() {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            // Attach listeners to the new element and its descendants
            attachListeners(node);
            const descendants = node.querySelectorAll('a, button, input, select, textarea, form, [onclick], [role="button"], [tabindex]');
            descendants.forEach(attachListeners);
          }
        }
      }
    });

    observer.observe(document.documentElement || document.body || document, {
      childList: true,
      subtree: true
    });

    return observer;
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initializeListeners();
      setupMutationObserver();
    });
  } else {
    initializeListeners();
    setupMutationObserver();
  }
})();
