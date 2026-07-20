/**
 * Pending-profile backfill processor.
 *
 * runSync() queues profile ids it could not enrich inline. This drains that
 * queue a few at a time, since a service worker can be killed mid-run.
 */

async function _runPendingBackfill() {
  const { _pendingBackfill, apiUrl, token } = await chrome.storage.local.get([
    "_pendingBackfill", "apiUrl", "token",
  ]);
  if (!_pendingBackfill || _pendingBackfill.length === 0 || !apiUrl || !token) return;

  // Read cookies fresh
  const cookies = await chrome.cookies.getAll({ domain: ".linkedin.com" });
  const liAt = cookies.find(c => c.name === "li_at")?.value;
  const jsid = cookies.find(c => c.name === "JSESSIONID")?.value;
  if (!liAt || !jsid) return;

  console.log("[SW] Running pending backfill for", _pendingBackfill.length, "profiles");

  // Process one at a time to stay within SW lifetime
  const remaining = [..._pendingBackfill];
  let processed = 0;

  for (const item of remaining.splice(0, 10)) { // max 10 per run
    const publicId = item.linkedin_profile_id;
    if (!publicId) continue;
    // Skip URN member IDs (start with ACo or aco) — they won't work with the profile endpoint
    if (/^[Aa][Cc][Oo]/i.test(publicId)) {
      console.log("[Backfill] Skipping URN member ID:", publicId);
      continue;
    }
    try {
      console.log("[Backfill] Fetching:", publicId);
      const raw = await voyagerGetProfile(liAt, jsid, publicId);
      console.log("[Backfill] Got response for:", publicId);

      const fields = _extractProfileFields(raw);
      if (!fields) {
        console.log("[Backfill] No profile object in response for:", publicId);
        continue;
      }

      // Fetch the image bytes inside the LinkedIn tab — the backend can't
      // download from media.licdn.com directly (CDN returns 403 server-side).
      let avatarData = null;
      if (fields.avatarUrl) {
        try {
          avatarData = await fetchLinkedInImageAsBase64(fields.avatarUrl);
        } catch (err) {
          console.warn("[Backfill] Avatar fetch failed for:", publicId, err.message);
        }
      }

      // Push profile to backend
      await apiFetch(`${apiUrl}/api/v1/linkedin/push`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({
          profiles: [{
            profile_id: publicId,
            member_id: fields.memberId,
            profile_url: `https://www.linkedin.com/in/${publicId}`,
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
      console.log("[Backfill] Pushed profile for:", publicId, "company:", fields.company, "avatar:", !!fields.avatarUrl, "bytes:", !!avatarData);
      processed++;
    } catch (e) {
      // Only stop on rate limiting — individual profile 401/403/404 are expected for bad IDs
      if (e.message === "RATE_LIMITED") {
        console.warn("[Backfill] Rate limited, stopping");
        break;
      }
      console.warn("[Backfill] Failed for:", publicId, e.message);
    }
  }

  // Save remaining for next run
  if (remaining.length > 0) {
    await chrome.storage.local.set({ _pendingBackfill: remaining });
    console.log("[Backfill]", remaining.length, "remaining for next sync");
  } else {
    await chrome.storage.local.remove("_pendingBackfill");
    console.log("[Backfill] All done,", processed, "profiles pushed");
  }

  if (processed > 0) {
    await Storage.recordSync({ profilesSynced: processed, messagesSynced: 0 });
  }
}
