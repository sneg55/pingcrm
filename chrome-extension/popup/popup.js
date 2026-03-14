/**
 * Popup script for PingCRM LinkedIn Companion settings.
 */
(function () {
  'use strict';

  const setupSection = document.getElementById('setup-section');
  const statusSection = document.getElementById('status-section');
  const apiUrlInput = document.getElementById('api-url');
  const emailInput = document.getElementById('email');
  const passwordInput = document.getElementById('password');
  const loginBtn = document.getElementById('login-btn');
  const loginError = document.getElementById('login-error');
  const disconnectBtn = document.getElementById('disconnect-btn');
  const autoSyncToggle = document.getElementById('auto-sync');
  const profileCountEl = document.getElementById('profile-count');
  const messageCountEl = document.getElementById('message-count');
  const lastSyncEl = document.getElementById('last-sync');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const userEmailEl = document.getElementById('user-email');
  const syncNowBtn = document.getElementById('sync-now-btn');
  const syncErrorEl = document.getElementById('sync-error');
  const syncErrorMsgEl = document.getElementById('sync-error-msg');
  const retryBtn = document.getElementById('retry-btn');

  async function render() {
    const config = await Storage.getConfig();

    if (config.apiUrl && config.token) {
      setupSection.classList.add('hidden');
      statusSection.classList.remove('hidden');

      profileCountEl.textContent = config.profileCount;
      messageCountEl.textContent = config.messageCount;
      autoSyncToggle.checked = config.autoSync;

      if (config.lastSync) {
        const ago = timeAgo(new Date(config.lastSync));
        lastSyncEl.textContent = `Last sync: ${ago}`;
      } else {
        lastSyncEl.textContent = 'Never synced';
      }

      statusDot.classList.remove('error');
      statusText.textContent = 'Connected';

      // Task 3.3: show user email
      if (config.userEmail) {
        userEmailEl.textContent = config.userEmail;
        userEmailEl.classList.remove('hidden');
      } else {
        userEmailEl.classList.add('hidden');
      }

      // Task 3.4: show sync error if present
      if (config.lastSyncError) {
        syncErrorMsgEl.textContent = config.lastSyncError;
        syncErrorEl.classList.remove('hidden');
      } else {
        syncErrorEl.classList.add('hidden');
      }
    } else {
      setupSection.classList.remove('hidden');
      statusSection.classList.add('hidden');

      if (config.apiUrl) {
        apiUrlInput.value = config.apiUrl;
      }
    }
  }

  function timeAgo(date) {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  function showError(msg) {
    loginError.textContent = msg;
    loginError.classList.remove('hidden');
  }

  function hideError() {
    loginError.classList.add('hidden');
  }

  async function triggerSync() {
    syncNowBtn.disabled = true;
    syncNowBtn.textContent = 'Syncing...';
    retryBtn.disabled = true;
    retryBtn.textContent = 'Retrying...';

    try {
      const response = await chrome.runtime.sendMessage({ type: 'SYNC_NOW' });
      if (response && response.ok) {
        lastSyncEl.textContent = `Synced: ${response.profiles} profiles, ${response.messages} messages`;
      } else {
        const errMsg = (response && response.error) ? response.error : 'Sync failed';
        await Storage.set({ lastSyncError: errMsg });
      }
    } catch (e) {
      await Storage.set({ lastSyncError: e.message });
    } finally {
      syncNowBtn.disabled = false;
      syncNowBtn.textContent = 'Sync Now';
      retryBtn.disabled = false;
      retryBtn.textContent = 'Retry';
      await render();
    }
  }

  loginBtn.addEventListener('click', async () => {
    const apiUrl = apiUrlInput.value.trim();
    const email = emailInput.value.trim();
    const password = passwordInput.value;

    if (!apiUrl || !email || !password) {
      showError('Please fill in all fields.');
      return;
    }

    hideError();
    loginBtn.disabled = true;
    loginBtn.textContent = 'Logging in...';

    try {
      const cleanUrl = apiUrl.replace(/\/+$/, '');
      const token = await Api.login(cleanUrl, email, password);
      await Storage.saveConfig({ apiUrl: cleanUrl, token });
      // Task 3.3: persist the email for display in the connected state
      await Storage.set({ userEmail: email });
      await render();
    } catch (e) {
      showError(e.message);
    } finally {
      loginBtn.disabled = false;
      loginBtn.textContent = 'Log in';
    }
  });

  // Allow Enter key to submit
  passwordInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loginBtn.click();
  });

  // Task 3.1: disconnect only clears auth state, preserves apiUrl
  disconnectBtn.addEventListener('click', async () => {
    await Storage.clearToken();
    await Storage.set({ userEmail: null, lastSyncError: null });
    await render();
  });

  autoSyncToggle.addEventListener('change', async () => {
    await Storage.setAutoSync(autoSyncToggle.checked);
  });

  // Task 3.2: Sync Now button
  syncNowBtn.addEventListener('click', triggerSync);

  // Task 3.4: Retry button triggers re-sync
  retryBtn.addEventListener('click', triggerSync);

  // Live updates when storage changes
  chrome.storage.onChanged.addListener((_changes, _area) => {
    render();
  });

  // Initial render
  render();
})();
