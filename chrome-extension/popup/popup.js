/**
 * PingCRM LinkedIn Companion v2 — Popup Controller
 *
 * State machine with three views:
 *   unpaired  — no token in storage (show pairing flow)
 *   expired   — token present but cookiesValid === false
 *   connected — token present and cookiesValid === true
 *
 * Data flow:
 *   popup.js → chrome.runtime.sendMessage → service-worker.js
 *   service-worker.js writes chrome.storage.local
 *   chrome.storage.onChanged → popup re-renders
 */
(function () {
  "use strict";

  // ── View elements ──
  const views = {
    unpaired: document.getElementById("view-unpaired"),
    connected: document.getElementById("view-connected"),
    expired: document.getElementById("view-expired"),
  };

  // ── Unpaired view elements ──
  const stepUrl = document.getElementById("step-url");
  const stepCode = document.getElementById("step-code");
  const instanceUrlInput = document.getElementById("instance-url-input");
  const urlError = document.getElementById("url-error");
  const startPairingBtn = document.getElementById("start-pairing-btn");
  const pairingCodeDisplay = document.getElementById("pairing-code-display");
  const changeUrlBtn = document.getElementById("change-url-btn");

  // ── Connected view elements ──
  const liStatusChip = document.getElementById("li-status");
  const liStatusText = document.getElementById("li-status-text");
  const statProfiles = document.getElementById("stat-profiles");
  const statMessages = document.getElementById("stat-messages");
  const cookieStatusEl = document.getElementById("cookie-status-el");
  const lastSyncEl = document.getElementById("last-sync-el");
  const syncNowBtn = document.getElementById("sync-now-btn");
  const disconnectBtn = document.getElementById("disconnect-btn");
  const instanceHostEl = document.getElementById("instance-host-el");
  const activityFeed = document.getElementById("activity-feed");

  // ── Meta elements ──
  const metaStatusChip = document.getElementById("meta-status");
  const metaStatusText = document.getElementById("meta-status-text");
  const metaCookieStatusEl = document.getElementById("meta-cookie-status-el");
  const lastFbSyncEl = document.getElementById("last-fb-sync-el");
  const lastIgSyncEl = document.getElementById("last-ig-sync-el");
  const metaSyncBtn = document.getElementById("meta-sync-btn");
  const metaHint = document.getElementById("meta-hint");
  const versionFooter = document.getElementById("version-footer");

  // ════════════════════════════════════════════
  // View Management
  // ════════════════════════════════════════════

  function showView(name) {
    Object.entries(views).forEach(([key, el]) => {
      el.classList.toggle("hidden", key !== name);
    });
  }

  // ════════════════════════════════════════════
  // Main Render
  // ════════════════════════════════════════════

  async function render() {
    const state = await chrome.storage.local.get([
      "token",
      "apiUrl",
      "cookiesValid",
      "profileCount",
      "messageCount",
      "lastVoyagerSync",
      "_pairingCode",
      "metaCookiesValid",
      "lastFacebookSync",
      "lastInstagramSync",
    ]);

    // No token → unpaired view
    if (!state.token) {
      showView("unpaired");
      renderUnpairedView(state);
      return;
    }

    // Token present but cookies invalid → expired view
    if (state.cookiesValid === false) {
      showView("expired");
      return;
    }

    // Fully connected
    showView("connected");
    renderConnectedView(state);
  }

  // ════════════════════════════════════════════
  // Unpaired View Renderer
  // ════════════════════════════════════════════

  function renderUnpairedView(state) {
    // If a pairing code is already active (service worker regenerated it), show it
    if (state._pairingCode) {
      pairingCodeDisplay.textContent = state._pairingCode;
      showPairingStep("code");
    } else {
      // Prefill URL if previously stored
      if (state.apiUrl) {
        instanceUrlInput.value = state.apiUrl;
      }
      showPairingStep("url");
    }
  }

  function showPairingStep(step) {
    stepUrl.classList.toggle("hidden", step !== "url");
    stepCode.classList.toggle("hidden", step !== "code");
  }

  // ════════════════════════════════════════════
  // Connected View Renderer
  // ════════════════════════════════════════════

  function renderConnectedView(state) {
    // Stats
    statProfiles.textContent = formatNumber(state.profileCount || 0);
    statMessages.textContent = formatNumber(state.messageCount || 0);

    // Cookie status
    const valid = state.cookiesValid !== false;
    cookieStatusEl.innerHTML = valid
      ? '<span class="cookie-dot valid"></span> Valid'
      : '<span class="cookie-dot expired"></span> Expired';

    // LinkedIn status chip
    liStatusChip.className = "status-chip " + (valid ? "connected" : "expired");
    liStatusText.textContent = valid ? "Connected" : "Cookies Expired";

    // Last sync
    lastSyncEl.textContent = state.lastVoyagerSync
      ? timeAgo(new Date(state.lastVoyagerSync))
      : "—";

    // Instance hostname
    if (state.apiUrl) {
      try {
        instanceHostEl.textContent = new URL(state.apiUrl).hostname;
      } catch {
        instanceHostEl.textContent = state.apiUrl;
      }
    }

    // Activity feed — build from available state
    renderActivityFeed(state);

    // Meta section
    renderMetaSection(state);

    // Version footer
    const manifest = chrome.runtime.getManifest();
    versionFooter.textContent = `v${manifest.version}`;
  }

  function renderMetaSection(state) {
    const metaValid = state.metaCookiesValid === true;

    metaCookieStatusEl.innerHTML = metaValid
      ? '<span class="cookie-dot valid"></span> Valid'
      : '<span class="cookie-dot expired"></span> Not detected';

    if (metaValid) {
      metaStatusChip.className = "status-chip connected";
      metaStatusText.textContent = "Connected";
      metaHint.classList.add("hidden");
    } else {
      metaStatusChip.className = "status-chip disconnected";
      metaStatusText.textContent = "Not connected";
      metaHint.classList.remove("hidden");
    }

    lastFbSyncEl.textContent = state.lastFacebookSync
      ? timeAgo(new Date(state.lastFacebookSync))
      : "—";

    lastIgSyncEl.textContent = state.lastInstagramSync
      ? timeAgo(new Date(state.lastInstagramSync))
      : "—";
  }

  function renderActivityFeed(state) {
    const items = [];

    if (state.profileCount > 0) {
      items.push({
        type: "profile",
        label: `<strong>${formatNumber(state.profileCount)}</strong> profiles synced`,
        time: state.lastVoyagerSync ? timeAgo(new Date(state.lastVoyagerSync)) : "",
      });
    }

    if (state.messageCount > 0) {
      items.push({
        type: "message",
        label: `<strong>${formatNumber(state.messageCount)}</strong> messages synced`,
        time: state.lastVoyagerSync ? timeAgo(new Date(state.lastVoyagerSync)) : "",
      });
    }

    if (items.length === 0) {
      activityFeed.innerHTML =
        '<div class="activity-item activity-empty">' +
        '<div class="activity-text" style="text-align:center;width:100%;padding:8px 0;">No activity yet — click Sync Now</div>' +
        "</div>";
      return;
    }

    const profileIcon =
      '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
      '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';

    const messageIcon =
      '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
      '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>';

    activityFeed.innerHTML = items
      .map(
        (item) =>
          `<div class="activity-item">` +
          `<div class="activity-icon ${item.type}">${item.type === "profile" ? profileIcon : messageIcon}</div>` +
          `<div class="activity-text">${item.label}</div>` +
          `<span class="activity-time">${item.time}</span>` +
          `</div>`
      )
      .join("");
  }

  // ════════════════════════════════════════════
  // Unpaired: Start Pairing
  // ════════════════════════════════════════════

  startPairingBtn.addEventListener("click", async () => {
    const rawUrl = instanceUrlInput.value.trim();
    if (!rawUrl) {
      showUrlError("Please enter your PingCRM instance URL.");
      return;
    }

    let cleanUrl;
    try {
      cleanUrl = new URL(rawUrl).origin;
    } catch {
      showUrlError("Please enter a valid URL (e.g. https://pingcrm.example.com).");
      return;
    }

    hideUrlError();
    setLoading(startPairingBtn, true);

    try {
      const response = await chrome.runtime.sendMessage({
        type: "START_PAIRING",
        apiUrl: cleanUrl,
      });

      if (!response || !response.ok) {
        showUrlError(response?.error || "Failed to start pairing. Please try again.");
        return;
      }

      pairingCodeDisplay.textContent = response.code;
      showPairingStep("code");
    } catch (e) {
      showUrlError(e.message || "Extension error. Please reload.");
    } finally {
      setLoading(startPairingBtn, false);
    }
  });

  changeUrlBtn.addEventListener("click", async () => {
    // Tell service worker to stop polling, then clear the stored code
    try {
      await chrome.runtime.sendMessage({ type: "DISCONNECT" });
    } catch (e) {
      // Ignore — just clear local state
    }
    await chrome.storage.local.remove(["_pairingCode", "apiUrl"]);
    showPairingStep("url");
    instanceUrlInput.value = "";
  });

  function showUrlError(msg) {
    urlError.textContent = msg;
    urlError.classList.remove("hidden");
  }

  function hideUrlError() {
    urlError.classList.add("hidden");
  }

  // ════════════════════════════════════════════
  // Connected: Sync Now
  // ════════════════════════════════════════════

  syncNowBtn.addEventListener("click", async () => {
    setLoading(syncNowBtn, true);

    try {
      const response = await chrome.runtime.sendMessage({ type: "SYNC_NOW" });
      if (!response || !response.ok) {
        console.warn("[PingCRM Popup] Sync failed:", response?.error);
        const label = syncNowBtn.querySelector(".btn-label");
        const original = label.textContent;
        if (response?.error === "NO_LINKEDIN_TAB" || response?.error === "PROXY_NO_RESPONSE") {
          label.textContent = "Open linkedin.com first";
        } else if (response?.error === "VOYAGER_AUTH_REJECTED") {
          label.textContent = "LinkedIn API rejected — try again later";
        } else if (response?.error === "RATE_LIMITED") {
          label.textContent = "Rate limited — try later";
        } else {
          label.textContent = "Sync failed";
        }
        setTimeout(() => { label.textContent = original; }, 4000);
      }
    } catch (e) {
      console.error("[PingCRM Popup] SYNC_NOW error:", e.message);
    } finally {
      setLoading(syncNowBtn, false);
      await render();
    }
  });

  // ════════════════════════════════════════════
  // Connected: Meta Sync
  // ════════════════════════════════════════════

  metaSyncBtn.addEventListener("click", async () => {
    setLoading(metaSyncBtn, true);

    try {
      const response = await chrome.runtime.sendMessage({ type: "META_SYNC_NOW", platform: "both" });
      if (!response || !response.ok) {
        console.warn("[PingCRM Popup] Meta sync failed:", response?.error);
        const label = metaSyncBtn.querySelector(".btn-label");
        const original = label.textContent;
        if (response?.error === "NO_META_TAB") {
          label.textContent = "Open facebook.com first";
        } else if (response?.error === "MISSING_META_COOKIES") {
          label.textContent = "Log in to Facebook first";
        } else if (response?.error === "RATE_LIMITED") {
          label.textContent = "Rate limited — try later";
        } else {
          label.textContent = "Sync failed";
        }
        setTimeout(() => { label.textContent = original; }, 4000);
      }
    } catch (e) {
      console.error("[PingCRM Popup] META_SYNC_NOW error:", e.message);
    } finally {
      setLoading(metaSyncBtn, false);
      await render();
    }
  });

  // ════════════════════════════════════════════
  // Connected: Disconnect
  // ════════════════════════════════════════════

  disconnectBtn.addEventListener("click", async () => {
    disconnectBtn.disabled = true;

    try {
      await chrome.runtime.sendMessage({ type: "DISCONNECT" });
    } catch (e) {
      console.warn("[PingCRM Popup] DISCONNECT error:", e.message);
    } finally {
      disconnectBtn.disabled = false;
      await render();
    }
  });

  // ════════════════════════════════════════════
  // Live Updates (storage changes from service worker)
  // ════════════════════════════════════════════

  chrome.storage.onChanged.addListener((_changes, area) => {
    if (area === "local") render();
  });

  // ════════════════════════════════════════════
  // Helpers
  // ════════════════════════════════════════════

  function timeAgo(date) {
    const s = Math.floor((Date.now() - date.getTime()) / 1000);
    if (s < 60) return "just now";
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  }

  function formatNumber(n) {
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  function setLoading(btn, loading) {
    btn.disabled = loading;
    const label = btn.querySelector(".btn-label");
    const spinner = btn.querySelector(".btn-spinner");
    if (label) label.style.opacity = loading ? "0" : "";
    if (spinner) spinner.classList.toggle("hidden", !loading);
  }

  // ── Init ──
  render();
})();
