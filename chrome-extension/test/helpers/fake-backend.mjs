/**
 * A fetch() replacement that records every request and returns canned
 * PingCRM backend responses. Used by Layers 1 and 2 to run fully offline.
 *
 * To test against a *real* local backend instead, skip this and pass Node's
 * global fetch with a real apiUrl + extension token (see test/README.md).
 */

function jsonResponse(status, obj) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => obj,
    text: async () => JSON.stringify(obj),
  };
}

/**
 * @param {object} [opts]
 * @param {object} [opts.pushData]   `data` payload for /linkedin/push (envelope-wrapped)
 * @param {number} [opts.pushStatus] HTTP status for /linkedin/push (default 200)
 */
export function makeFakeBackend({ pushData, pushStatus = 200 } = {}) {
  const requests = [];

  const fetchImpl = async (url, opts = {}) => {
    const entry = {
      url,
      method: opts.method ?? "GET",
      headers: opts.headers ?? {},
      body: opts.body ? safeParse(opts.body) : null,
    };
    requests.push(entry);

    if (url.includes("/api/v1/linkedin/push")) {
      const data = pushData ?? {
        contacts_created: 0,
        contacts_updated: 0,
        interactions_created: 0,
        interactions_skipped: 0,
        backfill_needed: [],
      };
      return jsonResponse(pushStatus, { data });
    }
    if (url.includes("/api/v1/extension/refresh")) {
      return jsonResponse(200, { data: { token: "refreshed-token" } });
    }
    if (url.includes("/api/v1/extension/pair")) {
      const base = url.split("/api/v1/")[0];
      return jsonResponse(200, { data: { token: "paired-token", api_url: base } });
    }
    return jsonResponse(404, { error: { message: "no fake route" } });
  };

  const pushes = () => requests.filter((r) => r.url.includes("/linkedin/push"));
  return { fetchImpl, requests, pushes };
}

function safeParse(body) {
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}
