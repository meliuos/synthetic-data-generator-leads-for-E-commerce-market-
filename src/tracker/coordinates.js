/**
 * Coordinate Normalization
 * Converts browser-relative coordinates to document-relative percentages (0-100)
 */

/**
 * Normalize click coordinates to document-relative percentages
 * @param {number} clientX - Horizontal click position from left edge of viewport
 * @param {number} clientY - Vertical click position from top edge of viewport
 * @returns {Object} - { x_pct: number, y_pct: number } - normalized to 0-100 scale
 */
function normalizeCoordinates(clientX, clientY) {
  // Get document dimensions (including scroll)
  const docWidth = document.documentElement.scrollWidth;
  const docHeight = document.documentElement.scrollHeight;

  // Get scroll position
  const scrollX = window.scrollX || window.pageXOffset || 0;
  const scrollY = window.scrollY || window.pageYOffset || 0;

  // Convert viewport-relative coordinates to document-relative
  const documentX = clientX + scrollX;
  const documentY = clientY + scrollY;

  // Convert to percentages
  const x_pct = (docWidth > 0) ? (documentX / docWidth) * 100 : 0;
  const y_pct = (docHeight > 0) ? (documentY / docHeight) * 100 : 0;

  // Clamp to 0-100 range and round to 1 decimal place
  return {
    x_pct: Math.max(0, Math.min(100, Math.round(x_pct * 10) / 10)),
    y_pct: Math.max(0, Math.min(100, Math.round(y_pct * 10) / 10))
  };
}

module.exports = {
  normalizeCoordinates
};
