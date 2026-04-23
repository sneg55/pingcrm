"use client";

import { useEffect } from "react";

/**
 * Global error reporter — catches unhandled JS errors and promise rejections,
 * sends them to the backend structured log via POST /api/v1/errors.
 *
 * Mount once in the root layout. No UI rendered.
 */
export function ErrorReporter() {
  useEffect(() => {
    function report(payload: Record<string, unknown>) {
      const token = localStorage.getItem("access_token");
      fetch("/api/v1/errors", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      }).catch(() => {
        // Best-effort — don't throw if reporting itself fails
      });
    }

    function onError(event: ErrorEvent) {
      const err = event.error as { stack?: unknown } | undefined;
      report({
        message: event.message,
        source: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: typeof err?.stack === "string" ? err.stack : undefined,
        url: window.location.href,
      });
    }

    function onUnhandledRejection(event: PromiseRejectionEvent) {
      const reason = event.reason as { message?: unknown; stack?: unknown } | undefined;
      const message = typeof reason?.message === "string" ? reason.message : String(event.reason);
      const stack = typeof reason?.stack === "string" ? reason.stack : undefined;
      report({
        message,
        stack,
        source: "unhandledrejection",
        url: window.location.href,
      });
    }

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, []);

  return null;
}
