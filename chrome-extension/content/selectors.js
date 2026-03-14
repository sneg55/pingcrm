/**
 * Centralized DOM selectors for LinkedIn pages.
 * When LinkedIn changes their DOM, only this file needs updating.
 */
const SELECTORS = {
  // ── Profile selectors (updated 2026-03 for LinkedIn's SDUI redesign) ──
  profileName: [
    '[componentkey*="Topcard"] h2',                    // 2026 SDUI layout
    'h1.text-heading-xlarge',                          // legacy (pre-2026)
    '[data-anonymize="person-name"]',
    '.pv-text-details__left-panel h1',
  ],
  headline: [
    '.text-body-medium[data-anonymize="headline"]',
    '.pv-text-details__left-panel .text-body-medium',
  ],
  company: [
    '[data-anonymize="company-name"]',
    'div[aria-label="Current company"] span',
    '.pv-text-details__right-panel .inline-show-more-text',
  ],
  location: [
    '.text-body-small[data-anonymize="location"]',
    '.pv-text-details__left-panel .pb2 .text-body-small',
    'section.pv-top-card .text-body-small.t-black--light',
  ],
  about: [
    '[componentkey*="About"] span',                    // 2026 SDUI layout
    '#about ~ .display-flex .inline-show-more-text',
    'section.pv-about-section .pv-about__summary-text',
    '[data-anonymize="person-summary"]',
  ],
  avatarUrl: [
    'img.pv-top-card-profile-picture__image--show',
    '.pv-top-card__photo img',
    'img[data-anonymize="headshot-photo"]',
  ],
  // Messaging selectors
  conversationPartnerName: [
    'h2.msg-entity-lockup__entity-title',             // full-page messaging (clean name only)
    '.msg-overlay-bubble-header__title',              // overlay messenger header
  ],
  conversationPartnerLink: [
    'a.msg-thread__link-to-profile',
    '.msg-entity-lockup__entity-title a',
    'a[href*="/in/"]',                                // generic fallback
  ],
  messageItem: [
    '.msg-s-event-listitem',
  ],
  messageSender: [
    '.msg-s-message-group__name',
    '.msg-s-event-listitem__link span.visually-hidden',
  ],
  messageBody: [
    '.msg-s-event-listitem__body',
    '.msg-s-event__content p',
  ],
  messageTimestamp: [
    'time.msg-s-message-list__time-heading',
    '.msg-s-message-group__timestamp',
  ],
};

/**
 * Query the DOM using fallback selectors.
 * @param {string} key - Key from SELECTORS
 * @returns {Element|null}
 */
function querySelector(key) {
  const selectors = SELECTORS[key];
  if (!selectors) return null;
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

/**
 * Query all matching elements using fallback selectors.
 * @param {string} key - Key from SELECTORS
 * @returns {Element[]}
 */
function querySelectorAll(key) {
  const selectors = SELECTORS[key];
  if (!selectors) return [];
  for (const sel of selectors) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) return Array.from(els);
  }
  return [];
}
