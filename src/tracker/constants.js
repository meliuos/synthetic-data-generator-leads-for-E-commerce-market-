/**
 * Lead Tracker Constants
 * Configuration for event types, throttle intervals, and tracking behavior
 */

const EVENT_TYPES = {
  CLICK: 'click',
  SCROLL: 'scroll',
  MOUSEMOVE: 'mousemove',
  PAGE_VIEW: 'page_view',
  PRODUCT_VIEW: 'product_view',
  ADD_TO_CART: 'add_to_cart',
  REMOVE_FROM_CART: 'remove_from_cart',
  PURCHASE: 'purchase',
  SEARCH: 'search'
};

const THROTTLE_INTERVALS = {
  MOUSEMOVE: 100 // milliseconds - 10 events per second max
};

const CONFIG = {
  EVENT_TYPES,
  THROTTLE_INTERVALS
};

module.exports = CONFIG;
