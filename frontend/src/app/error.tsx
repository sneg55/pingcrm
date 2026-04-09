'use client'

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch("/api/v1/errors", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message: error.message,
        stack: error.stack,
        source: "error_boundary",
        component: "RootErrorBoundary",
        url: window.location.href,
      }),
    }).catch(() => {});
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white dark:bg-stone-950">
      <div className="text-center">
        <h2 className="text-2xl font-bold mb-4 text-stone-900 dark:text-stone-100">Something went wrong!</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-4">{error.message}</p>
        <button
          onClick={() => reset()}
          className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors text-sm font-medium"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
