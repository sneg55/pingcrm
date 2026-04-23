/**
 * Typed API client generated from the backend OpenAPI spec.
 *
 * Usage:
 *   import { client } from "@/lib/api-client";
 *   const { data } = await client.GET("/api/v1/contacts", { params: { query: { page: 1 } } });
 *
 * Regenerate types: npm run generate:api
 */
import createClient from "openapi-fetch";
import type { paths } from "./api-types";

const client = createClient<paths>({
  baseUrl: "",
});

// Auth interceptor — attach JWT from localStorage
client.use({
  onRequest({ request }) {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      if (!window.location.pathname.startsWith("/auth")) {
        window.location.href = "/auth/login";
      }
    }
    // Throw on server errors so React Query transitions to error state
    // (401 is handled above via redirect; 4xx client errors surface as res.error in callers)
    if (response.status >= 500) {
      throw new Error(`API error: ${response.status}`);
    }
    return response;
  },
});

export { client };
export type { paths };
