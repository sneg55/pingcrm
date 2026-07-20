/**
 * LinkedIn message handlers.
 *
 * Each takes (message, sendResponse) and always calls sendResponse exactly once.
 * The router returns true for these so Chrome keeps the port open.
 */

/** LINKEDIN_PAGE_VISIT — user visited any LinkedIn page, refresh cookies. */
async function handleLinkedInPageVisit(_message, sendResponse) {
  try {
    const cookies = await chrome.cookies.getAll({ domain: ".linkedin.com" });
    const liAt = cookies.find(c => c.name === "li_at")?.value;
    const jsid = cookies.find(c => c.name === "JSESSIONID")?.value;
    const valid = !!(liAt && jsid);
    await chrome.storage.local.set({ cookiesValid: valid });
    console.log("[PingCRM SW] Cookie refresh:", valid ? "valid" : "missing", "li_at:", !!liAt, "JSESSIONID:", !!jsid);

    if (valid) {
      // Trigger throttled sync in background
      _maybeRunVoyagerSync().catch(e =>
        console.warn("[PingCRM SW] Auto-sync after page visit failed:", e.message)
      );
    }
  } catch (e) {
    console.warn("[PingCRM SW] Cookie refresh failed:", e.message);
  }
  sendResponse({ ok: true });
}

/**
 * PROFILE_VISIT — user opened a member profile page (/in/<slug>). Fetch that
 * person via Voyager and enrich the matching contact (avatar, company,
 * headline). Unlike DM sync, this is the only path that has the public slug,
 * so it can also repair contacts stored under an anonymized ACo member id.
 */
async function handleProfileVisit(message, sendResponse) {
  try {
    const slug = (message.slug || "").trim();
    // ACo member ids aren't accepted by the profile endpoint (needs a slug).
    if (!slug || /^aco/i.test(slug)) {
      sendResponse({ ok: false, error: "NO_SLUG" });
      return;
    }

    const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
    if (!apiUrl || !token) {
      sendResponse({ ok: false, error: "Not paired" });
      return;
    }

    const now = Date.now();
    if (now - (_profileVisitAt[slug] || 0) < PROFILE_VISIT_THROTTLE_MS) {
      sendResponse({ ok: true, throttled: true });
      return;
    }
    _profileVisitAt[slug] = now;

    const cookies = await chrome.cookies.getAll({ domain: ".linkedin.com" });
    const liAt = cookies.find(c => c.name === "li_at")?.value;
    const jsid = cookies.find(c => c.name === "JSESSIONID")?.value;
    if (!liAt || !jsid) {
      sendResponse({ ok: false, error: "MISSING_COOKIES" });
      return;
    }

    const raw = await voyagerGetProfile(liAt, jsid, slug);
    const fields = _extractProfileFields(raw);
    if (!fields) {
      console.warn("[ProfileVisit] No profile object for:", slug);
      sendResponse({ ok: false, error: "NO_PROFILE" });
      return;
    }

    let avatarData = null;
    if (fields.avatarUrl) {
      try {
        avatarData = await fetchLinkedInImageAsBase64(fields.avatarUrl);
      } catch (err) {
        console.warn("[ProfileVisit] Avatar fetch failed for:", slug, err.message);
      }
    }

    const resp = await apiFetch(`${apiUrl}/api/v1/linkedin/push`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      body: JSON.stringify({
        // Enrich existing contacts only — don't create a CRM entry for every
        // stranger whose profile you happen to open.
        enrich_only: true,
        profiles: [{
          profile_id: slug,
          member_id: fields.memberId,
          profile_url: `https://www.linkedin.com/in/${slug}`,
          full_name: fields.fullName,
          headline: fields.headline,
          company: fields.company,
          location: fields.location,
          avatar_url: fields.avatarUrl,
          avatar_data: avatarData,
        }],
        messages: [],
      }),
    });

    if (!resp.ok) {
      console.warn("[ProfileVisit] Push failed:", slug, resp.status);
      sendResponse({ ok: false, error: `PUSH_FAILED:${resp.status}` });
      return;
    }
    console.log("[ProfileVisit] Enriched:", slug, "company:", fields.company, "avatar:", !!avatarData);
    sendResponse({ ok: true, company: fields.company, avatar: !!avatarData });
  } catch (e) {
    console.warn("[ProfileVisit] Failed:", message.slug, e.message);
    sendResponse({ ok: false, error: e.message });
  }
}

/** SYNC_NOW — force Voyager sync (from popup). */
async function handleSyncNow(_message, sendResponse) {
  try {
    const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
    if (!apiUrl || !token) {
      sendResponse({ ok: false, error: "Not paired" });
      return;
    }

    setBadge("...", "#64748b");
    console.log("[SW] SYNC_NOW starting...");

    const result = await runSync(apiUrl, token, true);
    console.log("[SW] SYNC_NOW result:", JSON.stringify(result).substring(0, 200));

    if (result.error) {
      setBadge("X", "#FF9800");
      sendResponse({ ok: false, error: result.error });
      return;
    }

    await Storage.recordSync({
      profilesSynced: result.backfilled,
      messagesSynced: result.messages,
    });

    setBadge("OK", "#4CAF50");
    setTimeout(() => setBadge("", ""), 3000);

    sendResponse({
      ok: true,
      conversations: result.conversations,
      messages: result.messages,
      backfilled: result.backfilled,
    });

    // Run backfill in the background after responding to popup
    _runPendingBackfill().catch(e =>
      console.warn("[SW] Background backfill failed:", e.message)
    );
  } catch (e) {
    console.error("[SW] SYNC_NOW crashed:", e.message, e.stack);
    setBadge("X", "#FF9800");
    sendResponse({ ok: false, error: e.message });
  }
}
