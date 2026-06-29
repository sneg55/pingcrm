/**
 * In-memory stub of the chrome.* extension APIs the service worker touches.
 *
 * This is the foundation for Layers 1 and 2: it replaces the only stateful
 * browser surfaces (storage, cookies, tabs, scripting, action) with plain JS
 * so the real extension code runs unmodified in Node.
 *
 * The single browser-coupled seam in the whole sync path is
 * chrome.scripting.executeScript (Voyager calls run inside a LinkedIn tab).
 * Pass an `executeScript` router to serve canned Voyager responses.
 */

/**
 * @param {object}   opts
 * @param {(args:any[]) => any}  opts.executeScript  Router for executeScript.
 *        Receives the call's `args` array and returns the value the in-page
 *        function would have returned (e.g. {ok, status, data} for Voyager).
 * @param {Array<{name:string,value:string,domain?:string}>} [opts.cookies]
 * @param {Array<{id:number,url:string,active?:boolean}>}    [opts.tabs]
 * @param {object}   [opts.manifest]
 */
export function makeChrome({
  executeScript = async () => ({ ok: false, status: 0, body: "NO_ROUTER" }),
  cookies = [],
  tabs = [{ id: 1, url: "https://www.linkedin.com/feed/", active: true }],
  manifest = { version: "test" },
} = {}) {
  const store = new Map();
  const badges = [];
  const listeners = { message: [], installed: [], cookieChanged: [], tabUpdated: [] };

  const localGet = (keys) => {
    const out = {};
    if (keys == null) {
      for (const [k, v] of store) out[k] = v;
    } else if (typeof keys === "string") {
      if (store.has(keys)) out[keys] = store.get(keys);
    } else if (Array.isArray(keys)) {
      for (const k of keys) if (store.has(k)) out[k] = store.get(k);
    } else {
      for (const k of Object.keys(keys)) out[k] = store.has(k) ? store.get(k) : keys[k];
    }
    return Promise.resolve(out);
  };
  const localSet = (obj) => {
    for (const k of Object.keys(obj)) store.set(k, obj[k]);
    return Promise.resolve();
  };
  const localRemove = (keys) => {
    for (const k of Array.isArray(keys) ? keys : [keys]) store.delete(k);
    return Promise.resolve();
  };
  const localClear = () => {
    store.clear();
    return Promise.resolve();
  };

  const matchTab = (pattern) => {
    if (!pattern) return tabs;
    // crude chrome match-pattern: "https://www.linkedin.com/*"
    const re = new RegExp("^" + pattern.replace(/[.]/g, "\\.").replace(/\*/g, ".*"));
    return tabs.filter((t) => re.test(t.url));
  };

  const chrome = {
    runtime: {
      getManifest: () => manifest,
      onMessage: { addListener: (fn) => listeners.message.push(fn) },
      onInstalled: { addListener: (fn) => listeners.installed.push(fn) },
    },
    storage: {
      local: { get: localGet, set: localSet, remove: localRemove, clear: localClear },
    },
    cookies: {
      getAll: async (q) =>
        cookies.filter((c) => !q?.domain || (c.domain ?? ".linkedin.com").includes(q.domain.replace(/^\./, ""))),
      get: async ({ name }) => cookies.find((c) => c.name === name) ?? null,
      onChanged: { addListener: (fn) => listeners.cookieChanged.push(fn) },
    },
    tabs: {
      query: async (q) => matchTab(q?.url),
      create: async (p) => {
        const t = { id: tabs.length + 1, active: true, ...p };
        tabs.push(t);
        return t;
      },
      remove: async () => {},
      onUpdated: {
        addListener: (fn) => listeners.tabUpdated.push(fn),
        removeListener: () => {},
      },
    },
    scripting: {
      executeScript: async ({ args }) => [{ result: await executeScript(args) }],
    },
    action: {
      setBadgeText: ({ text }) => badges.push(text),
      setBadgeBackgroundColor: () => {},
    },
  };

  /** Drive the SW's onMessage router and resolve with its sendResponse value. */
  const sendMessage = (msg, sender = {}) =>
    new Promise((resolve) => {
      let answered = false;
      const sendResponse = (r) => {
        answered = true;
        resolve(r);
      };
      for (const fn of listeners.message) {
        const ret = fn(msg, sender, sendResponse);
        if (ret === true) return; // async: sendResponse will fire later
      }
      if (!answered) resolve(undefined);
    });

  return { chrome, store, badges, listeners, tabs, sendMessage };
}
