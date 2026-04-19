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
let cartId = null;
let cartItems = new Map();
let seenOrderIds = new Set();
let sessionData = {
  maxScrollPct: 0,
  startTime: new Date().toISOString()
};
let throttleData = {
  lastMousemoveTime: 0
};

// Consent state - will be set by consent module
let hasConsentFn = () => true; // Default: assume consent

const STORAGE_KEYS = {
  CART_ID: 'lead_tracker_cart_id',
  SEEN_ORDERS: 'lead_tracker_seen_orders'
};

function isBrowser() {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined';
}

function safeRead(key) {
  if (!isBrowser()) return null;
  try {
    return localStorage.getItem(key);
  } catch (_) {
    return null;
  }
}

function safeWrite(key, value) {
  if (!isBrowser()) return;
  try {
    localStorage.setItem(key, value);
  } catch (_) {
    // Ignore localStorage write failures and keep in-memory state.
  }
}

function generateId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Generate a simple session ID
 * @returns {string} - Session identifier
 */
function generateSessionId() {
  return generateId('session');
}

function normalizePositiveNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function normalizeQuantity(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

function ensureCartId() {
  if (!cartId) {
    cartId = safeRead(STORAGE_KEYS.CART_ID) || generateId('cart');
    safeWrite(STORAGE_KEYS.CART_ID, cartId);
  }
  return cartId;
}

function loadSeenOrders() {
  const raw = safeRead(STORAGE_KEYS.SEEN_ORDERS);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      seenOrderIds = new Set(parsed.filter(Boolean));
    }
  } catch (_) {
    seenOrderIds = new Set();
  }
}

function persistSeenOrders() {
  safeWrite(STORAGE_KEYS.SEEN_ORDERS, JSON.stringify(Array.from(seenOrderIds)));
}

function getCartItemsAsProducts() {
  return Array.from(cartItems.values()).map((item) => ({
    product_id: item.product_id,
    category: item.category,
    price: item.price,
    quantity: item.quantity
  }));
}

function getCartTotal() {
  return getCartItemsAsProducts().reduce((sum, item) => {
    return sum + ((item.price || 0) * (item.quantity || 0));
  }, 0);
}

function enqueue(event) {
  eventQueue.push({
    ...event,
    timestamp: new Date().toISOString()
  });
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
  ensureCartId();
  loadSeenOrders();

  if (typeof document === 'undefined' || typeof window === 'undefined') {
    return;
  }

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

function productView(payload = {}) {
  if (!hasConsentFn()) return null;

  const product_id = payload.product_id || null;
  const category = payload.category || null;
  const price = normalizePositiveNumber(payload.price);
  const currency = payload.currency || null;

  if (!product_id) return null;

  const event = {
    type: EVENT_TYPES.PRODUCT_VIEW,
    product_id,
    category,
    price,
    currency,
    properties: {
      product_id,
      category,
      price,
      currency
    }
  };

  enqueue(event);
  return event;
}

function addToCart(payload = {}) {
  if (!hasConsentFn()) return null;

  const product_id = payload.product_id || null;
  const quantity = normalizeQuantity(payload.quantity);
  const price = normalizePositiveNumber(payload.price);
  const category = payload.category || null;
  const currency = payload.currency || null;

  if (!product_id || !quantity || price === null) return null;

  const current = cartItems.get(product_id) || {
    product_id,
    quantity: 0,
    price,
    category,
    currency
  };

  current.quantity += quantity;
  current.price = price;
  current.category = category || current.category || null;
  current.currency = currency || current.currency || null;
  cartItems.set(product_id, current);

  const event = {
    type: EVENT_TYPES.ADD_TO_CART,
    cart_id: ensureCartId(),
    product_id,
    quantity,
    price,
    category,
    currency,
    cart_value: Number(getCartTotal().toFixed(2)),
    properties: {
      cart_id: ensureCartId(),
      product_id,
      quantity,
      price,
      category,
      currency,
      cart_value: Number(getCartTotal().toFixed(2))
    }
  };

  enqueue(event);
  return event;
}

function removeFromCart(payload = {}) {
  if (!hasConsentFn()) return null;

  const product_id = payload.product_id || null;
  const quantity = normalizeQuantity(payload.quantity);

  if (!product_id || !quantity) return null;

  const current = cartItems.get(product_id);
  if (current) {
    current.quantity = Math.max(0, current.quantity - quantity);
    if (current.quantity === 0) {
      cartItems.delete(product_id);
    } else {
      cartItems.set(product_id, current);
    }
  }

  const event = {
    type: EVENT_TYPES.REMOVE_FROM_CART,
    cart_id: ensureCartId(),
    product_id,
    quantity,
    cart_value: Number(getCartTotal().toFixed(2)),
    properties: {
      cart_id: ensureCartId(),
      product_id,
      quantity,
      cart_value: Number(getCartTotal().toFixed(2))
    }
  };

  enqueue(event);
  return event;
}

function purchase(payload = {}) {
  if (!hasConsentFn()) return null;

  const order_id = payload.order_id || null;
  if (!order_id || seenOrderIds.has(order_id)) return null;

  const products = Array.isArray(payload.items) ? payload.items : getCartItemsAsProducts();
  const normalizedProducts = products
    .map((item) => ({
      product_id: item.product_id || null,
      category: item.category || null,
      price: normalizePositiveNumber(item.price),
      quantity: normalizeQuantity(item.quantity) || 1
    }))
    .filter((item) => item.product_id);

  const computedTotal = normalizedProducts.reduce((sum, item) => {
    return sum + ((item.price || 0) * (item.quantity || 0));
  }, 0);
  const total = normalizePositiveNumber(payload.total);
  const currency = payload.currency || null;

  const event = {
    type: EVENT_TYPES.PURCHASE,
    order_id,
    total: Number((total === null ? computedTotal : total).toFixed(2)),
    revenue: Number((total === null ? computedTotal : total).toFixed(2)),
    currency,
    cart_id: ensureCartId(),
    products: normalizedProducts,
    properties: {
      order_id,
      total: Number((total === null ? computedTotal : total).toFixed(2)),
      revenue: Number((total === null ? computedTotal : total).toFixed(2)),
      currency,
      cart_id: ensureCartId(),
      products: normalizedProducts
    }
  };

  seenOrderIds.add(order_id);
  persistSeenOrders();
  enqueue(event);

  cartItems = new Map();
  cartId = generateId('cart');
  safeWrite(STORAGE_KEYS.CART_ID, cartId);

  return event;
}

function search(payload = {}) {
  if (!hasConsentFn()) return null;

  const query = typeof payload.query === 'string' ? payload.query.trim() : '';
  const results_count = normalizeQuantity(payload.results_count);

  if (!query) return null;

  const event = {
    type: EVENT_TYPES.SEARCH,
    query,
    results_count: results_count || 0,
    properties: {
      query,
      results_count: results_count || 0
    }
  };

  enqueue(event);
  return event;
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
  cartItems = new Map();
  cartId = generateId('cart');
  safeWrite(STORAGE_KEYS.CART_ID, cartId);
  seenOrderIds = new Set();
  persistSeenOrders();
}

// Initialize on page load or domready if already loaded
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initTracker();
    });
  } else {
    initTracker();
  }
}

// Export for use in other modules
module.exports = {
  initTracker,
  getSessionId,
  getEventQueue,
  flushEvents,
  productView,
  addToCart,
  removeFromCart,
  purchase,
  search,
  queueEvent,
  reset
};
