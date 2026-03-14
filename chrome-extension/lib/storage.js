/**
 * Chrome storage wrapper for PingCRM extension settings.
 */
const Storage = {
  async get(keys) {
    return chrome.storage.local.get(keys);
  },

  async set(data) {
    return chrome.storage.local.set(data);
  },

  async getConfig() {
    const { apiUrl, token, autoSync, lastSync, profileCount, messageCount, lastSyncError, userEmail } =
      await this.get(['apiUrl', 'token', 'autoSync', 'lastSync', 'profileCount', 'messageCount', 'lastSyncError', 'userEmail']);
    return {
      apiUrl: apiUrl || '',
      token: token || '',
      autoSync: autoSync !== false,
      lastSync: lastSync || null,
      profileCount: profileCount || 0,
      messageCount: messageCount || 0,
      lastSyncError: lastSyncError || null,
      userEmail: userEmail || null,
    };
  },

  async saveConfig({ apiUrl, token }) {
    await this.set({ apiUrl: apiUrl.replace(/\/+$/, ''), token });
  },

  async setAutoSync(enabled) {
    await this.set({ autoSync: enabled });
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
