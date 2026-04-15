/**
 * Lead Tracker
 * Main entry point for browser event tracking
 * Captures clicks, scrolls, mouse movement, and page views with consent gating
 */

const { captureClick, captureScroll, captureMousemove, capturePageView } = require('./events');
const { EVENT_TYPES } = require('./constants');

// Module-level state
let eventQueue = [];
let sessionId = null;
let sessionData = {
  maxScrollPct: 0,
  startTime: new Date().toISOString()
};
let throttleData = {
  lastMousemoveTime: 0
};

// Consent state - will be set by consent module
let hasConsentFn = () => true; // Default: assume consent

/**
 * Generate a simple session ID
 * @returns {string} - Session identifier
 */
function generateSessionId() {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Initialize the tracker on page load
 * @param {Object} options - Configuration options
 * @param {Function} options.hasConsent - Consent checking function
 */
function initTracker(options = {}) {
  if (options.hasConsent) {
    hasConsentFn = options.hasConsent;
  }

  // Generate session ID
  sessionId = generateSessionId();

  // Capture initial page view
  capturePageView(eventQueue, hasConsentFn);

  // Attach click listener
  const clickHandler = (e) => captureClick(e, eventQueue, hasConsentFn);
  document.addEventListener('click', clickHandler);

  // Attach scroll listener
  const scrollHandler = (e) => captureScroll(e, eventQueue, hasConsentFn, sessionData);
  window.addEventListener('scroll', scrollHandler);

  // Attach mousemove listener
  const mousemoveHandler = (e) => captureMousemove(e, eventQueue, hasConsentFn, throttleData);
  document.addEventListener('mousemove', mousemoveHandler);

  // Intercept History API for SPA route changes
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;

  history.pushState = function(...args) {
    originalPushState.apply(this, args);
    // Emit page view event on route change
    setTimeout(() => {
      capturePageView(eventQueue, hasConsentFn);
    }, 0);
    return;
  };

  history.replaceState = function(...args) {
    originalReplaceState.apply(this, args);
    // Emit page view event on route replace
    setTimeout(() => {
      capturePageView(eventQueue, hasConsentFn);
    }, 0);
    return;
  };

  console.log('[Tracker] Initialized with session ID:', sessionId);
}

/**
 * Get current session ID
 * @returns {string} - Session identifier
 */
function getSessionId() {
  return sessionId;
}

/**
 * Get current event queue
 * @returns {Array} - Array of captured events
 */
function getEventQueue() {
  return eventQueue;
}

/**
 * Flush events from queue (called by RudderStack integration)
 * @returns {Array} - Events that were flushed
 */
function flushEvents() {
  const eventsToFlush = [...eventQueue];
  eventQueue = [];
  return eventsToFlush;
}

/**
 * Add events to queue manually (for testing)
 * @param {Object} event - Event object to add
 */
function queueEvent(event) {
  eventQueue.push(event);
}

/**
 * Reset tracker state (for testing)
 */
function reset() {
  eventQueue = [];
  sessionData = { maxScrollPct: 0, startTime: new Date().toISOString() };
  throttleData = { lastMousemoveTime: 0 };
  sessionId = generateSessionId();
}

// Initialize on page load or domready if already loaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initTracker();
  });
} else {
  initTracker();
}

// Export for use in other modules
module.exports = {
  initTracker,
  getSessionId,
  getEventQueue,
  flushEvents,
  queueEvent,
  reset
};
