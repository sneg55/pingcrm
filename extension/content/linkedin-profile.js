/**
 * Content script for LinkedIn profile pages (/in/*).
 * Passively captures profile data when the user browses profiles.
 */
(function () {
  'use strict';

  const DEBOUNCE_MS = 5 * 60 * 1000; // 5 minutes per profile
  const recentCaptures = new Map(); // profile_id -> timestamp

  function getProfileId() {
    const path = window.location.pathname;
    const match = path.match(/^\/in\/([^/]+)/);
    return match ? match[1].toLowerCase() : null;
  }

  /**
   * Extract from LinkedIn's 2026 SDUI topcard layout.
   * Structure: h2=name, then p tags: [degree, headline, company, location, ...]
   */
  function extractFromTopcard(profileId) {
    const topcard = document.querySelector('[componentkey*="Topcard"]');
    if (!topcard) return null;

    const h2 = topcard.querySelector('h2');
    if (!h2) return null;
    const name = h2.textContent.trim();
    if (!name) return null;

    // Direct child paragraphs of the topcard region around the name
    const paragraphs = Array.from(topcard.querySelectorAll('p'))
      .map(p => p.textContent.trim())
      .filter(t => t && t !== '·');

    // paragraphs[0] is typically "· 3rd" (degree) — skip entries starting with "·"
    // headline is the first long paragraph (not degree, not follower count)
    let headline = null;
    let company = null;
    let location = null;

    for (const text of paragraphs) {
      if (/^·/.test(text) || /followers?$/i.test(text) || text === 'Contact info') continue;
      if (/Profile enhanced/i.test(text)) continue;
      // Location pattern: "City, State/Region, Country"
      if (!location && /,.*,/.test(text) && !/·/.test(text) && text.length < 80) {
        location = text;
      } else if (!headline && text.length > 5) {
        headline = text;
      } else if (!company && text.length > 2 && text !== headline) {
        company = text;
      }
    }

    // Avatar: second img in topcard (first is cover photo)
    const imgs = Array.from(topcard.querySelectorAll('img'));
    const avatarImg = imgs.length > 1 ? imgs[1] : null;

    // About section
    const aboutEl = querySelector('about');

    return {
      profile_id: profileId,
      profile_url: `https://www.linkedin.com/in/${profileId}`,
      full_name: name,
      headline: headline || null,
      company: company || null,
      location: location || null,
      about: aboutEl ? aboutEl.textContent.trim() : null,
      avatar_url: avatarImg ? avatarImg.src : null,
    };
  }

  /**
   * Legacy extraction using CSS selectors (pre-2026 LinkedIn DOM).
   */
  function extractFromLegacy(profileId) {
    const nameEl = querySelector('profileName');
    if (!nameEl) return null;
    const name = nameEl.textContent.trim();
    if (!name) return null;

    const headlineEl = querySelector('headline');
    const companyEl = querySelector('company');
    const locationEl = querySelector('location');
    const aboutEl = querySelector('about');
    const avatarEl = querySelector('avatarUrl');

    return {
      profile_id: profileId,
      profile_url: `https://www.linkedin.com/in/${profileId}`,
      full_name: name,
      headline: headlineEl ? headlineEl.textContent.trim() : null,
      company: companyEl ? companyEl.textContent.trim() : null,
      location: locationEl ? locationEl.textContent.trim() : null,
      about: aboutEl ? aboutEl.textContent.trim() : null,
      avatar_url: avatarEl ? avatarEl.src : null,
    };
  }

  function extractProfile() {
    const profileId = getProfileId();
    if (!profileId) return null;
    // Try new SDUI layout first, fall back to legacy selectors
    return extractFromTopcard(profileId) || extractFromLegacy(profileId);
  }

  function shouldCapture(profileId) {
    const lastCapture = recentCaptures.get(profileId);
    if (lastCapture && Date.now() - lastCapture < DEBOUNCE_MS) {
      return false;
    }
    return true;
  }

  function captureAndSend() {
    try {
      const profile = extractProfile();
      if (!profile) {
        console.debug('[PingCRM] Could not extract profile data');
        return;
      }
      if (!shouldCapture(profile.profile_id)) {
        console.debug('[PingCRM] Skipping (recently captured):', profile.profile_id);
        return;
      }

      console.log('[PingCRM] Captured profile:', profile.full_name, profile.profile_id);
      recentCaptures.set(profile.profile_id, Date.now());
      chrome.runtime.sendMessage({
        type: 'PROFILE_CAPTURED',
        data: profile,
      });
    } catch (e) {
      console.debug('[PingCRM] Profile capture error:', e.message);
    }
  }

  // Wait for profile content to load, then capture
  function waitForProfile() {
    // Check both new SDUI layout and legacy selectors
    const topcard = document.querySelector('[componentkey*="Topcard"] h2');
    const nameEl = topcard || querySelector('profileName');
    if (nameEl) {
      captureAndSend();
      return;
    }

    const observer = new MutationObserver((_mutations, obs) => {
      const tc = document.querySelector('[componentkey*="Topcard"] h2');
      const el = tc || querySelector('profileName');
      if (el) {
        obs.disconnect();
        // Small delay to let other fields render
        setTimeout(captureAndSend, 500);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Timeout after 10 seconds
    setTimeout(() => observer.disconnect(), 10000);
  }

  // Detect SPA navigation (LinkedIn is a SPA)
  let lastUrl = window.location.href;
  const urlObserver = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      if (window.location.pathname.startsWith('/in/')) {
        setTimeout(waitForProfile, 1000);
      }
    }
  });
  urlObserver.observe(document.body, { childList: true, subtree: true });

  // Initial capture (only on profile pages)
  if (window.location.pathname.startsWith('/in/')) {
    waitForProfile();
  }
})();
