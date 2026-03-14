/**
 * Fetch wrapper for PingCRM backend API.
 */
const Api = {
  async login(apiUrl, email, password) {
    const body = new URLSearchParams();
    body.append('username', email);
    body.append('password', password);

    const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });

    if (response.status === 401) {
      throw new Error('Incorrect email or password');
    }
    if (!response.ok) {
      throw new Error(`Login failed: ${response.status}`);
    }

    const result = await response.json();
    return result.data.access_token;
  },

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
