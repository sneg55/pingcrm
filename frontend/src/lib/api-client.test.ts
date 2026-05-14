import { describe, it, expect, beforeAll, beforeEach, vi, type Mock } from "vitest";

/**
 * Tests for the openapi-fetch client + auth interceptors.
 *
 * Critical setup notes:
 *  - openapi-fetch captures `globalThis.fetch` at `createClient()` time, so we must
 *    stub fetch BEFORE the module is imported. We do that via a dynamic import in
 *    `beforeAll` after `vi.stubGlobal("fetch", ...)`.
 *  - Vitest 4's default localStorage stub in jsdom is missing getItem/setItem/
 *    removeItem, so we install a real in-memory Storage shim.
 *  - jsdom rejects relative URLs in `new Request(...)`. The production client uses
 *    `baseUrl: ""`, but in tests we pass absolute URLs like `http://localhost/api/...`.
 *    The interceptors don't care about the URL scheme; they only look at status +
 *    headers + window.location.pathname.
 */

// --- in-memory Storage shim -----------------------------------------------
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  key(i: number) {
    return Array.from(this.store.keys())[i] ?? null;
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}

const memoryStorage = new MemoryStorage();
vi.stubGlobal("localStorage", memoryStorage);

// --- fetch mock + window.location stub ------------------------------------
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

// jsdom provides window.location, but `href = ...` triggers a navigation that
// jsdom logs as a "Not implemented" warning. Replace location with a plain
// stand-in so we can assert on the assignment without noise.
type LocationStub = { pathname: string; href: string };
const locationStub: LocationStub = { pathname: "/dashboard", href: "" };
Object.defineProperty(window, "location", {
  configurable: true,
  writable: true,
  value: locationStub,
});

function setPathname(p: string) {
  locationStub.pathname = p;
  locationStub.href = "";
}

// --- dynamic import (after stubs are installed) ---------------------------
let client: typeof import("./api-client").client;

beforeAll(async () => {
  const mod = await import("./api-client");
  client = mod.client;
});

beforeEach(() => {
  fetchMock.mockReset();
  memoryStorage.clear();
  setPathname("/dashboard");
});

// Helper: build a Response with a JSON body and a given status
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Cast helper so we can call typed routes that don't strictly exist in
// generated `paths`. The client is the runtime singleton — we just need it to
// route through the interceptors.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const c = () => client as unknown as any;

describe("api-client auth interceptor (onRequest)", () => {
  it("attaches Authorization: Bearer <token> when localStorage has access_token", async () => {
    memoryStorage.setItem("access_token", "tok-123");
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await c().GET("http://localhost/api/v1/contacts");

    expect(fetchMock).toHaveBeenCalledOnce();
    const req = (fetchMock as Mock).mock.calls[0][0] as Request;
    expect(req.headers.get("Authorization")).toBe("Bearer tok-123");
  });

  it("omits Authorization header when no token in localStorage", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await c().GET("http://localhost/api/v1/contacts");

    const req = (fetchMock as Mock).mock.calls[0][0] as Request;
    expect(req.headers.get("Authorization")).toBeNull();
  });

  it("preserves URL and HTTP method on the outgoing Request", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));

    await c().GET("http://localhost/api/v1/contacts/abc");

    const req = (fetchMock as Mock).mock.calls[0][0] as Request;
    expect(req.url).toBe("http://localhost/api/v1/contacts/abc");
    expect(req.method).toBe("GET");
  });
});

describe("api-client HTTP verbs", () => {
  it.each([
    ["GET", "GET", false],
    ["POST", "POST", true],
    ["PUT", "PUT", true],
    ["PATCH", "PATCH", true],
    ["DELETE", "DELETE", false],
  ] as const)(
    "client.%s routes to fetch with method %s",
    async (verb, expectedMethod, hasBody) => {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

      const opts = hasBody ? { body: {} } : {};
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (c() as any)[verb]("http://localhost/api/v1/x", opts);

      const req = (fetchMock as Mock).mock.calls[0][0] as Request;
      expect(req.method).toBe(expectedMethod);
    },
  );
});

describe("api-client response handling", () => {
  it("parses 2xx JSON body into result.data", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "1", name: "Ada" }));

    const result = await c().GET("http://localhost/api/v1/contacts/1");

    expect(result.data).toEqual({ id: "1", name: "Ada" });
    expect(result.error).toBeUndefined();
  });

  it("returns 404 body in result.error and does not throw", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { detail: "Not found" }),
    );

    const result = await c().GET("http://localhost/api/v1/contacts/nope");

    expect(result.data).toBeUndefined();
    expect(result.error).toEqual({ detail: "Not found" });
  });

  it("returns 422 validation body in result.error and does not throw", async () => {
    const validation = {
      detail: [
        { loc: ["body", "email"], msg: "field required", type: "value_error.missing" },
      ],
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(422, validation));

    const result = await c().POST("http://localhost/api/v1/contacts", {
      body: {},
    });

    expect(result.error).toEqual(validation);
    expect(result.data).toBeUndefined();
  });
});

describe("api-client 401 handling", () => {
  it("clears access_token from localStorage on 401", async () => {
    memoryStorage.setItem("access_token", "expired-token");
    setPathname("/dashboard");
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Unauthorized" }));

    await c().GET("http://localhost/api/v1/contacts");

    expect(memoryStorage.getItem("access_token")).toBeNull();
  });

  it("redirects to /auth/login on 401 from a non-/auth path", async () => {
    setPathname("/dashboard");
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Unauthorized" }));

    await c().GET("http://localhost/api/v1/contacts");

    expect(locationStub.href).toBe("/auth/login");
  });

  it("does NOT redirect on 401 when already on /auth/login", async () => {
    setPathname("/auth/login");
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Unauthorized" }));

    await c().POST("http://localhost/api/v1/auth/login", { body: {} });

    expect(locationStub.href).toBe("");
  });

  it("does NOT redirect on 401 from any /auth/* path (e.g. /auth/register)", async () => {
    setPathname("/auth/register");
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Unauthorized" }));

    await c().POST("http://localhost/api/v1/auth/register", { body: {} });

    expect(locationStub.href).toBe("");
  });

  it("still clears token on 401 even when on /auth/* (no redirect)", async () => {
    memoryStorage.setItem("access_token", "tok");
    setPathname("/auth/login");
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Unauthorized" }));

    await c().GET("http://localhost/api/v1/me");

    expect(memoryStorage.getItem("access_token")).toBeNull();
    expect(locationStub.href).toBe("");
  });
});

describe("api-client 5xx handling", () => {
  it("throws 'API error: 500' so React Query enters error state", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(500, { detail: "Boom" }));

    await expect(c().GET("http://localhost/api/v1/contacts")).rejects.toThrow(
      "API error: 500",
    );
  });

  it("throws 'API error: 503' on 503 Service Unavailable", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(503, { detail: "Maintenance" }));

    await expect(c().GET("http://localhost/api/v1/contacts")).rejects.toThrow(
      "API error: 503",
    );
  });
});

describe("api-client network failures", () => {
  it("propagates the original fetch rejection (e.g. NetworkError)", async () => {
    const netErr = new TypeError("Failed to fetch");
    fetchMock.mockRejectedValueOnce(netErr);

    await expect(
      c().GET("http://localhost/api/v1/contacts"),
    ).rejects.toThrow("Failed to fetch");
  });
});
