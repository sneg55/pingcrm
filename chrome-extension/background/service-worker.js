/**
 * Service worker for PingCRM LinkedIn Companion.
 * Batches captured profiles and messages, pushes to backend.
 *
 * Note: Storage and Api are inlined here because MV3 module service workers
 * cannot importScripts, and relative ES module imports from subdirectories
 * have inconsistent behavior across Chrome versions.
 */

// ── Storage (mirrors lib/storage.js) ──
const Storage = {
  async get(keys) {
    return chrome.storage.local.get(keys);
  },
  async set(data) {
    return chrome.storage.local.set(data);
  },
  async getConfig() {
    const { apiUrl, token, autoSync, lastSync, profileCount, messageCount, lastSyncError } =
      await this.get(['apiUrl', 'token', 'autoSync', 'lastSync', 'profileCount', 'messageCount', 'lastSyncError']);
    return {
      apiUrl: apiUrl || '',
      token: token || '',
      autoSync: autoSync !== false,
      lastSync: lastSync || null,
      profileCount: profileCount || 0,
      messageCount: messageCount || 0,
      lastSyncError: lastSyncError || null,
    };
  },
  async saveConfig({ apiUrl, token }) {
    await this.set({ apiUrl: apiUrl.replace(/\/+$/, ''), token });
  },
  async recordSync({ profilesSynced = 0, messagesSynced = 0 }) {
    const config = await this.getConfig();
    await this.set({
      lastSync: new Date().toISOString(),
      profileCount: config.profileCount + profilesSynced,
      messageCount: config.messageCount + messagesSynced,
    });
  },
  async clearToken() {
    await this.set({ token: '' });
  },
  async isConfigured() {
    const { apiUrl, token } = await this.getConfig();
    return Boolean(apiUrl && token);
  },
};

// ── Api (mirrors lib/api.js) ──
const Api = {
  async push(profiles, messages) {
    const config = await Storage.getConfig();
    if (!config.apiUrl || !config.token) {
      throw new Error('Not configured: missing API URL or token');
    }
    const response = await fetch(`${config.apiUrl}/api/v1/linkedin/push`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.token}`,
      },
      body: JSON.stringify({ profiles, messages }),
    });
    if (response.status === 401) {
      await Storage.clearToken();
      throw new Error('AUTH_EXPIRED');
    }
    if (!response.ok) {
      throw new Error(`Push failed: ${response.status}`);
    }
    return response.json();
  },
};

// ── Batch logic ──
const BATCH_DELAY_MS = 3000;

let pendingProfiles = [];
let pendingMessages = [];
let batchTimer = null;

function scheduleBatch() {
  if (batchTimer) clearTimeout(batchTimer);
  batchTimer = setTimeout(flushBatch, BATCH_DELAY_MS);
}

async function flushBatch(sendResponse) {
  batchTimer = null;
  const profiles = pendingProfiles.splice(0);
  const messages = pendingMessages.splice(0);

  if (profiles.length === 0 && messages.length === 0) {
    if (sendResponse) sendResponse({ ok: true, profiles: 0, messages: 0 });
    return;
  }

  const configured = await Storage.isConfigured();
  if (!configured) {
    setBadge('!', '#F44336');
    if (sendResponse) sendResponse({ ok: false, error: 'Not configured' });
    return;
  }

  try {
    const result = await Api.push(profiles, messages);
    const data = result.data || {};

    const profilesSynced = (data.contacts_created || 0) + (data.contacts_updated || 0);
    const messagesSynced = data.interactions_created || 0;

    await Storage.recordSync({ profilesSynced, messagesSynced });
    await Storage.set({ lastSyncError: null });

    setBadge('OK', '#4CAF50');
    setTimeout(() => setBadge('', ''), 3000);

    if (sendResponse) sendResponse({ ok: true, profiles: profilesSynced, messages: messagesSynced });
  } catch (e) {
    console.error('[PingCRM] Push failed:', e.message);
    await Storage.set({ lastSyncError: e.message });

    if (e.message === 'AUTH_EXPIRED') {
      setBadge('!', '#F44336');
    } else {
      setBadge('X', '#FF9800');
      pendingProfiles.unshift(...profiles);
      pendingMessages.unshift(...messages);
      setTimeout(scheduleBatch, 30000);
    }

    if (sendResponse) sendResponse({ ok: false, error: e.message });
  }
}

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}

// ── Event listeners ──
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'PROFILE_CAPTURED') {
    pendingProfiles.push(message.data);
    scheduleBatch();
    sendResponse({ ok: true });
    return false;
  } else if (message.type === 'MESSAGES_CAPTURED') {
    pendingMessages.push(...(Array.isArray(message.data) ? message.data : [message.data]));
    scheduleBatch();
    sendResponse({ ok: true });
    return false;
  } else if (message.type === 'SYNC_NOW') {
    if (batchTimer) {
      clearTimeout(batchTimer);
      batchTimer = null;
    }
    flushBatch(sendResponse);
    return true; // async sendResponse
  }
  return false;
});

chrome.runtime.onInstalled.addListener(() => {
  console.log('[PingCRM] LinkedIn Companion v0.3.1 installed');
});
