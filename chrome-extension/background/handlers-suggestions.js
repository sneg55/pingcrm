/**
 * Suggestion handlers for the LinkedIn content script.
 *
 * Each takes (message, sendResponse) and always calls sendResponse exactly once.
 */

/** GET_SUGGESTION — content script asks for a pending suggestion for a thread. */
async function handleGetSuggestion(message, sendResponse) {
  try {
    const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
    if (!apiUrl || !token) {
      sendResponse({ suggestion: null, error: "NOT_PAIRED" });
      return;
    }

    // Read cookies to call Voyager
    const cookies = await chrome.cookies.getAll({ domain: ".linkedin.com" });
    const liAt = cookies.find(c => c.name === "li_at")?.value;
    const jsid = cookies.find(c => c.name === "JSESSIONID")?.value;
    if (!liAt || !jsid) {
      sendResponse({ suggestion: null, error: "COOKIES_EXPIRED" });
      return;
    }

    // Resolve conversation to a LinkedIn profile slug
    // Two paths: threadId (from URL on full-page messaging) or profileSlug (from DOM on overlay)
    let slug = message.profileSlug || null;

    if (!slug && message.threadId) {
      // Full-page messaging: resolve thread ID via Voyager
      try {
        const convUrn = `urn:li:messagingThread:${message.threadId}`;
        const selfUrn = await voyagerGetSelfUrn(liAt, jsid);
        const selfUrnSuffix = selfUrn.split(":").pop();
        const convData = await voyagerGetConversations(liAt, jsid, selfUrn);
        const conversations = _parseConversations(convData);
        const conv = conversations.find(c =>
          (c.backendUrn === convUrn) ||
          (c.entityUrn && c.entityUrn.includes(message.threadId))
        );
        if (conv) {
          const participants = _parseParticipants(conv);
          const others = participants.filter(p => {
            const urn = (p.profileUrn || "").split(":").pop();
            return urn !== selfUrnSuffix;
          });
          const partner = others[0] ?? participants[0];
          slug = partner?.publicIdentifier ?? null;
          if (slug && /^ACo/i.test(slug)) slug = null;
        }
      } catch (e) {
        console.warn("[SW] Voyager thread resolve failed:", e.message);
      }
    }

    // Fetch suggestions and find match by slug or name
    const suggestions = await _getSuggestions(token, apiUrl);
    console.log("[SW] Got", suggestions.length, "suggestions. Looking for slug:", slug, "name:", message.partnerName);
    if (suggestions.length > 0) {
      console.log("[SW] First suggestion contact:", suggestions[0]?.contact?.full_name, "linkedin_profile_id:", suggestions[0]?.contact?.linkedin_profile_id);
    }
    let match = null;

    if (slug) {
      match = suggestions.find(s =>
        s.contact?.linkedin_profile_id === slug
      );
    }

    // Fallback: match by partner name (from overlay header)
    if (!match && message.partnerName) {
      const name = message.partnerName.toLowerCase();
      match = suggestions.find(s =>
        s.contact?.full_name?.toLowerCase() === name
      );
      if (match) console.log("[SW] Matched suggestion by name:", message.partnerName);
    }

    if (!match && !slug) {
      sendResponse({ suggestion: null });
      return;
    }

    if (match) {
      sendResponse({
        suggestion: {
          id: match.id,
          message: match.suggested_message,
          contact_name: match.contact?.full_name || slug,
        },
      });
    } else {
      sendResponse({ suggestion: null, slug });
    }
  } catch (e) {
    console.warn("[SW] GET_SUGGESTION error:", e.message);
    sendResponse({ suggestion: null, error: e.message });
  }
}

/** REGENERATE_SUGGESTION — regenerate the AI message for an existing suggestion. */
async function handleRegenerateSuggestion(message, sendResponse) {
  try {
    const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
    if (!apiUrl || !token) {
      sendResponse({ suggestion: null, error: "NOT_PAIRED" });
      return;
    }

    const suggestionId = message.suggestion_id;
    if (!suggestionId) {
      sendResponse({ suggestion: null, error: "NO_SUGGESTION" });
      return;
    }

    const resp = await apiFetch(`${apiUrl}/api/v1/suggestions/${suggestionId}/regenerate`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    if (!resp.ok) {
      sendResponse({ suggestion: null, error: `REGEN_FAILED:${resp.status}` });
      return;
    }

    const data = await resp.json();
    _invalidateSuggestionCache();

    sendResponse({
      suggestion: {
        id: suggestionId,
        message: data?.data?.suggested_message ?? null,
      },
    });
  } catch (e) {
    console.warn("[SW] REGENERATE_SUGGESTION error:", e.message);
    sendResponse({ suggestion: null, error: e.message });
  }
}
