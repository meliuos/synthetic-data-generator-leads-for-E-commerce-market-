/**
 * Cookie Consent Gate
 * Integrates vanilla-cookieconsent v3.1.0 to gate event tracking
 * No events are captured until user explicitly accepts cookies
 */

let consentState = false;
let consentCallbacks = [];

/**
 * Initialize the consent gate
 * Sets up the vanilla-cookieconsent banner
 * @param {Function} onConsent - Callback when user accepts consent
 */
function initConsentGate(onConsent = null) {
  // Check if user has already accepted consent (from localStorage)
  const storedConsent = localStorage.getItem('cookie_consent_accepted');
  
  if (storedConsent === 'true') {
    consentState = true;
    console.log('[Consent] User has previously accepted consent');
  } else {
    consentState = false;
  }

  if (onConsent) {
    consentCallbacks.push(onConsent);
  }

  // Try to load vanilla-cookieconsent if available
  // In a real implementation, this would be loaded via CDN or bundler
  setupConsentBanner();
}

/**
 * Set up the consent banner
 * This would use vanilla-cookieconsent.run() in production
 */
function setupConsentBanner() {
  // In this implementation, check if vanilla-cookieconsent is available globally
  if (typeof window !== 'undefined' && window.CookieConsent) {
    try {
      window.CookieConsent.run({
        categories: {
          necessary: {
            enabled: true,  // Automatically enabled for site functionality
            readonly: true
          },
          analytics: {
            enabled: false
          },
          marketing: {
            enabled: false
          }
        },
        onFirstConsent: (consent) => {
          handleConsentAccepted();
        },
        onConsent: (consent) => {
          handleConsentAccepted();
        }
      });

      console.log('[Consent] vanilla-cookieconsent initialized');
    } catch (error) {
      console.warn('[Consent] Error initializing vanilla-cookieconsent:', error);
      // Fall back to manual banner
    }
  } else {
    console.log('[Consent] vanilla-cookieconsent not loaded, using fallback');
    // Banner is handled by main tracker page
  }
}

/**
 * Handle consent acceptance
 * Sets state and triggers callbacks
 */
function handleConsentAccepted() {
  consentState = true;
  localStorage.setItem('cookie_consent_accepted', 'true');
  
  console.log('[Consent] Consent accepted');
  
  // Call all registered callbacks
  consentCallbacks.forEach((callback) => {
    try {
      callback();
    } catch (error) {
      console.error('[Consent] Callback error:', error);
    }
  });
}

/**
 * Check if user has given consent for tracking
 * @returns {boolean} - True if consent was given, false otherwise
 */
function hasConsent() {
  return consentState || localStorage.getItem('cookie_consent_accepted') === 'true';
}

/**
 * Revoke consent
 * User can withdraw consent at any time
 */
function revokeConsent() {
  consentState = false;
  localStorage.setItem('cookie_consent_accepted', 'false');
  console.log('[Consent] Consent revoked');
}

/**
 * Get current consent state
 * @returns {Object} - { consented: boolean, timestamp: string }
 */
function getConsentState() {
  return {
    consented: hasConsent(),
    timestamp: localStorage.getItem('cookie_consent_timestamp') || new Date().toISOString()
  };
}

module.exports = {
  initConsentGate,
  hasConsent,
  revokeConsent,
  getConsentState
};
