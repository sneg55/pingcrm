/**
 * Toolbar badge helper.
 *
 * Extracted from service-worker.js so the sync, suggestion, and Meta handlers
 * can all share it without the router file owning presentation concerns.
 */

/**
 * @param {string} text  badge label; "" clears it
 * @param {string} [color] background colour, e.g. "#4CAF50"
 */
function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}
