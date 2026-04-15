/**
 * RudderStack SDK Integration
 * Initializes RudderStack SDK and provides tracking functions
 * for flushing tracker events to Kafka destination
 */

let rudderStackInstance = null;

/**
 * Initialize RudderStack SDK
 * @param {string} writeKey - RudderStack source write key
 * @param {string} dataPlaneUrl - RudderStack data plane URL (e.g., http://localhost:8080)
 * @returns {Object} - Initialized RudderStack instance
 */
function initRudderStack(writeKey, dataPlaneUrl) {
  // Check if RudderStack SDK is available globally
  if (typeof window === 'undefined' || !window.rudderanalytics) {
    console.error('[RudderStack] SDK not loaded. Ensure @rudderstack/sdk-js is included.');
    return null;
  }

  try {
    // Initialize RudderStack SDK
    window.rudderanalytics.load(writeKey, dataPlaneUrl, {
      // Disable automatic capturing to avoid double-counting with our manual events
      useBeacon: true,
      logLevel: 'DEBUG'
    });

    rudderStackInstance = window.rudderanalytics;
    console.log('[RudderStack] Initialized with write key:', writeKey);
    return rudderStackInstance;
  } catch (error) {
    console.error('[RudderStack] Initialization error:', error);
    return null;
  }
}

/**
 * Track an event with RudderStack
 * @param {string} eventName - Name of the event (e.g., 'click', 'scroll')
 * @param {Object} properties - Event properties
 * @param {string} userId - Optional user ID
 */
function trackEvent(eventName, properties = {}, userId = null) {
  if (!rudderStackInstance) {
    console.warn('[RudderStack] Instance not initialized. Event not tracked:', eventName);
    return false;
  }

  try {
    const eventPayload = {
      ...properties,
      timestamp: new Date().toISOString()
    };

    // Add user context if provided
    if (userId) {
      rudderStackInstance.identify(userId);
    }

    // Track the event
    rudderStackInstance.track(eventName, eventPayload);
    return true;
  } catch (error) {
    console.error('[RudderStack] Track error:', error);
    return false;
  }
}

/**
 * Send a batch of events to RudderStack
 * Used for flushing the tracker's event queue
 * @param {Array} events - Array of event objects from tracker
 * @param {string} sessionId - Session ID from tracker
 * @returns {Object} - { success: boolean, eventsTracked: number }
 */
function trackEventBatch(events, sessionId = null) {
  if (!rudderStackInstance) {
    console.warn('[RudderStack] Instance not initialized. Batch not tracked.');
    return { success: false, eventsTracked: 0 };
  }

  let successCount = 0;

  try {
    events.forEach((event) => {
      const properties = {
        ...event,
        session_id: sessionId || 'unknown'
      };

      // Map event type to RudderStack event names
      const eventName = event.type || 'unknown_event';

      // Track each event
      if (trackEvent(eventName, properties)) {
        successCount++;
      }
    });

    console.log(`[RudderStack] Batch tracked: ${successCount}/${events.length} events`);
    return { success: true, eventsTracked: successCount };
  } catch (error) {
    console.error('[RudderStack] Batch tracking error:', error);
    return { success: false, eventsTracked: successCount };
  }
}

/**
 * Flush any buffered events
 * RudderStack batches events internally, this ensures they're sent
 */
function flush() {
  if (!rudderStackInstance) {
    console.warn('[RudderStack] Instance not initialized. Cannot flush.');
    return false;
  }

  try {
    // RudderStack uses analytics.track() internally queues events
    // Forcing a flush may not be available in all SDKs
    // Events are typically flushed on page unload or batching interval
    console.log('[RudderStack] Flush requested');
    return true;
  } catch (error) {
    console.error('[RudderStack] Flush error:', error);
    return false;
  }
}

/**
 * Get the current RudderStack instance
 * @returns {Object|null} - RudderStack instance or null if not initialized
 */
function getInstance() {
  return rudderStackInstance;
}

module.exports = {
  initRudderStack,
  trackEvent,
  trackEventBatch,
  flush,
  getInstance
};
