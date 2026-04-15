/**
 * Event Capture Functions
 * Captures user interactions: clicks, scrolls, mouse movement, and page views
 */

const { normalizeCoordinates } = require('./coordinates');
const { EVENT_TYPES } = require('./constants');

/**
 * Capture click event with document-relative coordinates
 * @param {MouseEvent} event - Click event object
 * @param {Array} eventQueue - Shared event queue
 * @param {Function} hasConsent - Function to check if user consented to tracking
 */
function captureClick(event, eventQueue, hasConsent) {
  if (!hasConsent()) return;

  const { x_pct, y_pct } = normalizeCoordinates(event.clientX, event.clientY);

  const target = event.target;
  let selector = target.tagName.toLowerCase();
  if (target.id) {
    selector += `#${target.id}`;
  } else if (target.className) {
    selector += `.${target.className.replace(/\s+/g, '.')}`;
  }

  const clickEvent = {
    type: EVENT_TYPES.CLICK,
    x_pct,
    y_pct,
    element_selector: selector,
    timestamp: new Date().toISOString()
  };

  eventQueue.push(clickEvent);
}

/**
 * Capture scroll event with scroll depth percentage
 * @param {Event} event - Scroll event
 * @param {Array} eventQueue - Shared event queue
 * @param {Function} hasConsent - Function to check if user consented to tracking
 * @param {Object} sessionData - Session tracking data
 */
function captureScroll(event, eventQueue, hasConsent, sessionData) {
  if (!hasConsent()) return;

  const scrollTop = window.scrollY || window.pageYOffset || 0;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  const scroll_pct = docHeight > 0 ? Math.round((scrollTop / docHeight) * 100) : 0;

  // Track max scroll depth for the session
  if (scroll_pct > (sessionData.maxScrollPct || 0)) {
    sessionData.maxScrollPct = scroll_pct;
  }

  const scrollEvent = {
    type: EVENT_TYPES.SCROLL,
    scroll_pct,
    max_scroll_pct: sessionData.maxScrollPct,
    timestamp: new Date().toISOString()
  };

  eventQueue.push(scrollEvent);
}

/**
 * Capture mousemove event with throttling
 * @param {MouseEvent} event - Mousemove event
 * @param {Array} eventQueue - Shared event queue
 * @param {Function} hasConsent - Function to check if user consented to tracking
 * @param {Object} throttleData - Throttle state tracking
 */
function captureMousemove(event, eventQueue, hasConsent, throttleData) {
  if (!hasConsent()) return;

  const now = Date.now();
  const lastMousemoveTime = throttleData.lastMousemoveTime || 0;
  const throttleInterval = 100; // 100ms = 10 events per second max

  // Check throttle - only capture if enough time has passed
  if (now - lastMousemoveTime < throttleInterval) {
    return;
  }

  throttleData.lastMousemoveTime = now;

  const { x_pct, y_pct } = normalizeCoordinates(event.clientX, event.clientY);

  const mousemoveEvent = {
    type: EVENT_TYPES.MOUSEMOVE,
    x_pct,
    y_pct,
    timestamp: new Date().toISOString()
  };

  eventQueue.push(mousemoveEvent);
}

/**
 * Capture page view event
 * @param {Array} eventQueue - Shared event queue
 * @param {Function} hasConsent - Function to check if user consented to tracking
 */
function capturePageView(eventQueue, hasConsent) {
  if (!hasConsent()) return;

  const pageViewEvent = {
    type: EVENT_TYPES.PAGE_VIEW,
    url: window.location.href,
    title: document.title,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    document_width: document.documentElement.scrollWidth,
    document_height: document.documentElement.scrollHeight,
    timestamp: new Date().toISOString()
  };

  eventQueue.push(pageViewEvent);
}

module.exports = {
  captureClick,
  captureScroll,
  captureMousemove,
  capturePageView
};
