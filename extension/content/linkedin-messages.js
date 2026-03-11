/**
 * Content script for LinkedIn messaging.
 * Supports both full-page (/messaging/*) and the on-page overlay messenger
 * (shadow DOM inside #interop-outlet on any LinkedIn page).
 */
(function () {
  'use strict';

  const capturedConversations = new Set(); // per browser session

  /**
   * Get the messaging root — either the overlay conversation bubble (shadow DOM)
   * or the document (full-page messaging).
   * LinkedIn renders the overlay messenger inside #interop-outlet's shadow root.
   * We scope to .msg-overlay-conversation-bubble to avoid picking up sidebar elements.
   */
  function getMsgRoot() {
    const host = document.querySelector('#interop-outlet');
    if (host && host.shadowRoot) {
      const bubble = host.shadowRoot.querySelector('.msg-overlay-conversation-bubble');
      if (bubble) return bubble;
    }
    return document;
  }

  function getConversationId() {
    // Full-page messaging: ID is in the URL
    const urlMatch = window.location.pathname.match(/\/messaging\/thread\/([^/]+)/);
    if (urlMatch) return urlMatch[1];

    // Overlay messenger: check if bubble exists in shadow DOM
    const host = document.querySelector('#interop-outlet');
    if (host && host.shadowRoot) {
      const bubble = host.shadowRoot.querySelector('.msg-overlay-conversation-bubble');
      if (bubble) {
        // Derive conversation ID from partner profile link
        const link = bubble.querySelector('a[href*="/in/"]');
        if (link) {
          const match = (link.getAttribute('href') || link.href || '').match(/\/in\/([^/]+)/);
          if (match) return 'overlay-' + match[1];
        }
      }
    }
    return null;
  }

  /**
   * Clean a LinkedIn name — strip status indicators, availability text, etc.
   * e.g. "Simon LETORT Status is offline Building..." → "Simon LETORT"
   */
  function cleanName(raw) {
    // Remove everything from "Status is" onwards
    let name = raw.replace(/\s*Status is\s.*/i, '');
    // Remove trailing availability/time markers like "Mobile • 4h ago"
    name = name.replace(/\s*(Mobile|Desktop|Web)\s*[•·].*$/i, '');
    // Remove "Active now" or "Active Xh ago"
    name = name.replace(/\s*Active\s+(now|\d+[hmd]\s+ago).*$/i, '');
    return name.trim();
  }

  function extractMessages() {
    if (document.visibilityState !== 'visible') return null;

    const conversationId = getConversationId();
    if (!conversationId) return null;
    if (capturedConversations.has(conversationId)) return null;

    const root = getMsgRoot();

    // Get conversation partner info
    const partnerNameEl = root.querySelector(
      SELECTORS.conversationPartnerName.join(', ')
    );
    if (!partnerNameEl) return null;
    const partnerName = cleanName(partnerNameEl.textContent.trim());

    // Get partner profile ID from link
    const partnerLinkEl = root.querySelector(
      SELECTORS.conversationPartnerLink.join(', ')
    ) || root.querySelector('a[href*="/in/"]');

    let profileId = null;
    if (partnerLinkEl) {
      const href = partnerLinkEl.getAttribute('href') || partnerLinkEl.href || '';
      const match = href.match(/\/in\/([^/]+)/);
      if (match) profileId = match[1].toLowerCase();
    }
    if (!profileId) return null;

    // Extract visible messages
    const messageEls = Array.from(root.querySelectorAll(
      SELECTORS.messageItem.join(', ')
    ));
    const messages = [];
    let currentSender = null;

    for (const msgEl of messageEls) {
      const senderEl = msgEl.querySelector(
        SELECTORS.messageSender.join(', ')
      );
      if (senderEl) {
        currentSender = senderEl.textContent.trim();
      }

      const bodyEl = msgEl.querySelector(
        SELECTORS.messageBody.join(', ')
      );
      const timeEl = msgEl.querySelector(
        SELECTORS.messageTimestamp.join(', ')
      );

      if (bodyEl) {
        const content = bodyEl.textContent.trim();
        if (!content) continue;

        // Direction: if sender matches conversation partner → inbound, else outbound
        const isOutbound = currentSender !== null && currentSender !== partnerName;

        messages.push({
          profile_id: profileId,
          profile_name: partnerName,
          direction: isOutbound ? 'outbound' : 'inbound',
          content_preview: content.substring(0, 500),
          timestamp: timeEl
            ? timeEl.getAttribute('datetime') || new Date().toISOString()
            : new Date().toISOString(),
          conversation_id: conversationId,
        });
      }
    }

    if (messages.length === 0) return null;
    capturedConversations.add(conversationId);
    return messages;
  }

  function captureAndSend() {
    try {
      const messages = extractMessages();
      if (!messages) return;

      console.log('[PingCRM] Captured', messages.length, 'messages with', messages[0].profile_name);
      chrome.runtime.sendMessage({
        type: 'MESSAGES_CAPTURED',
        data: messages,
      });
    } catch (e) {
      console.debug('[PingCRM] Message capture error:', e.message);
    }
  }

  function hasVisibleMessages() {
    const root = getMsgRoot();
    return root.querySelectorAll(SELECTORS.messageItem.join(', ')).length > 0;
  }

  // Wait for messages to load before capturing
  function waitForMessages() {
    const conversationId = getConversationId();
    if (!conversationId) return;
    if (capturedConversations.has(conversationId)) return;

    if (hasVisibleMessages()) {
      setTimeout(captureAndSend, 1000);
      return;
    }

    const observer = new MutationObserver((_mutations, obs) => {
      if (hasVisibleMessages()) {
        obs.disconnect();
        setTimeout(captureAndSend, 1000);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 10000);
  }

  // Detect SPA navigation and overlay open/close
  let lastUrl = window.location.href;
  const urlObserver = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      setTimeout(waitForMessages, 1000);
    }
  });
  urlObserver.observe(document.body, { childList: true, subtree: true });

  // Watch for overlay messenger opening (shadow DOM mutations)
  function watchOverlay() {
    const host = document.querySelector('#interop-outlet');
    if (!host || !host.shadowRoot) return;

    // Immediate check for already-open conversation
    checkOverlay();

    const overlayObserver = new MutationObserver(() => {
      checkOverlay();
    });

    overlayObserver.observe(host.shadowRoot, { childList: true, subtree: true });
  }

  // Check overlay for capturable conversations
  function checkOverlay() {
    const convId = getConversationId();
    if (!convId || capturedConversations.has(convId)) return;
    if (hasVisibleMessages()) {
      setTimeout(captureAndSend, 1500);
    }
  }

  // Periodic poll — overlay can open/close at any time and shadow DOM
  // mutations don't always bubble reliably
  let pollInterval = null;
  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      checkOverlay();
    }, 5000);
  }

  // Capture when tab becomes visible
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      waitForMessages();
      checkOverlay();
    }
  });

  // Initial capture for full-page messaging
  waitForMessages();
  // Delay overlay watcher to let shadow DOM initialize, then start polling
  setTimeout(() => {
    watchOverlay();
    startPolling();
  }, 3000);
})();
