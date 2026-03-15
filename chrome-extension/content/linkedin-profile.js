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

    // Filter out noise paragraphs
    const meaningful = paragraphs.filter(text => {
      if (/^·/.test(text) || /followers?$/i.test(text) || text === 'Contact info') return false;
      if (/Profile enhanced/i.test(text)) return false;
      return true;
    });

    // Pass 1: identify location (City, State, Country pattern — at least 2 commas, short)
    for (const text of meaningful) {
      if (/,.*,/.test(text) && text.length < 80 && !/[@|]/.test(text)) {
        location = text;
        break;
      }
    }

    // Helper: extract company from "Title @ Company | Other" or "Title at Company"
    function extractCompany(text) {
      const atMatch = text.match(/(?:\s@\s|\sat\s)(.+)/i);
      if (!atMatch) return null;
      // Take first segment before | or · separators
      return atMatch[1].split(/\s*[|·]\s*/)[0].trim() || null;
    }

    // Pass 2: assign headline and company from remaining texts
    for (const text of meaningful) {
      if (text === location) continue;
      if (!headline && text.length > 5) {
        headline = text;
      } else if (!company && text.length > 2 && text !== headline) {
        const extracted = extractCompany(text);
        // Split on · or | separators (LinkedIn combines company + education)
        company = (extracted || text.split(/\s*[|·]\s*/)[0]).trim();
      }
    }

    // If headline contains "@ Company" or "at Company", extract company from it
    if (headline && !company) {
      const extracted = extractCompany(headline);
      if (extracted) company = extracted.split(/\s*[|·]\s*/)[0].trim();
    }

    // Avatar: find profile photo
    // Strategy: search topcard first, then broader page for profile photo
    let avatarImg = null;

    // 1. Look for profile photo by URL pattern (most reliable)
    const allPageImgs = Array.from(document.querySelectorAll('img'));
    for (const img of allPageImgs) {
      const src = img.src || '';
      if (src.includes('profile-displayphoto')) {
        avatarImg = img;
        break;
      }
    }

    // 2. Topcard images — skip company logos and covers
    if (!avatarImg) {
      const topcardImgs = Array.from(topcard.querySelectorAll('img'));
      for (const img of topcardImgs) {
        const src = img.src || '';
        if (!src || src.includes('company-logo') || src.includes('background-cover') || src.includes('li-default-avatar')) continue;
        if (src.includes('/dms/image/')) {
          avatarImg = img;
          break;
        }
      }
    }

    // 3. Fallback: circular img near the name (often has specific dimensions)
    if (!avatarImg) {
      const circularImg = document.querySelector('img[class*="profile-photo"], img[class*="pv-top-card-profile-picture"], .pv-top-card--photo img');
      if (circularImg) avatarImg = circularImg;
    }

    console.debug('[PingCRM] Avatar search:', avatarImg ? avatarImg.src?.substring(0, 80) : 'NOT FOUND',
      '| topcard imgs:', Array.from(topcard.querySelectorAll('img')).map(i => i.src?.substring(0, 60)));

    // About section
    const aboutEl = querySelector('about');

    let avatarUrl = avatarImg ? avatarImg.src : null;
    if (avatarUrl) {
      avatarUrl = avatarUrl.replace(/_100_100/, '_400_400').replace(/_200_200/, '_400_400');
    }

    return {
      profile_id: profileId,
      profile_url: `https://www.linkedin.com/in/${profileId}`,
      full_name: name,
      headline: headline || null,
      company: company || null,
      location: location || null,
      about: aboutEl ? aboutEl.textContent.trim() : null,
      avatar_url: avatarUrl,
      _avatarImgElement: avatarImg,  // DOM ref for canvas extraction (deleted before send)
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

    let avatarUrl = avatarEl ? avatarEl.src : null;
    if (avatarUrl) {
      avatarUrl = avatarUrl.replace(/_100_100/, '_400_400').replace(/_200_200/, '_400_400');
    }

    return {
      profile_id: profileId,
      profile_url: `https://www.linkedin.com/in/${profileId}`,
      full_name: name,
      headline: headlineEl ? headlineEl.textContent.trim() : null,
      company: companyEl ? companyEl.textContent.trim() : null,
      location: locationEl ? locationEl.textContent.trim() : null,
      about: aboutEl ? aboutEl.textContent.trim() : null,
      avatar_url: avatarUrl,
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

  /**
   * Extract avatar as base64 from an already-loaded <img> element.
   * Draws the image to a canvas to bypass CORS restrictions on fetch().
   * Falls back to fetch() if canvas fails (tainted canvas).
   */
  async function extractAvatarAsBase64(imgElement, url) {
    // Method 1: Canvas (works when image is same-origin or CORS-allowed)
    try {
      const img = imgElement || new Image();
      if (!imgElement) {
        img.crossOrigin = 'anonymous';
        img.src = url;
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
          setTimeout(reject, 5000);
        });
      }
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth || img.width || 400;
      canvas.height = img.naturalHeight || img.height || 400;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
      if (dataUrl && dataUrl.length > 100) return dataUrl;
    } catch (e) {
      console.debug('[PingCRM] Canvas avatar extract failed:', e.message);
    }

    // Method 2: Fetch with credentials (may fail with CORS)
    try {
      const resp = await fetch(url, { credentials: 'include' });
      if (!resp.ok) return null;
      const blob = await resp.blob();
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = () => resolve(null);
        reader.readAsDataURL(blob);
      });
    } catch (e) {
      console.debug('[PingCRM] Avatar fetch failed:', e.message);
      return null;
    }
  }

  async function captureAndSend() {
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

      // If no avatar found yet, don't send — wait for the page to fully load
      // and the MutationObserver to trigger another capture attempt
      if (!profile.avatar_url) {
        console.debug('[PingCRM] No avatar found yet, deferring capture for:', profile.profile_id);
        return;
      }

      // Request avatar download from service worker (has host_permissions, bypasses CORS)
      if (profile.avatar_url && !profile.avatar_url.startsWith('data:')) {
        try {
          const base64 = await new Promise((resolve) => {
            chrome.runtime.sendMessage(
              { type: 'DOWNLOAD_AVATAR', url: profile.avatar_url },
              (response) => resolve(response?.data || null)
            );
          });
          if (base64) {
            profile.avatar_data = base64;
          }
        } catch (e) {
          console.debug('[PingCRM] Avatar download request failed:', e.message);
        }
        delete profile._avatarImgElement;
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
