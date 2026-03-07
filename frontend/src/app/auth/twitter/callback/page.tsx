"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";

function TwitterCallbackInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code || !state) {
      setError("Missing code or state parameter.");
      return;
    }

    api
      .post("/auth/twitter/callback", { code, state })
      .then(() => {
        router.replace("/settings?connected=twitter");
      })
      .catch((err) => {
        const detail =
          err?.response?.data?.detail || "Twitter authentication failed.";
        setError(detail);
      });
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="bg-white rounded-xl p-6 max-w-sm w-full shadow-sm border border-gray-200 text-center">
        <p className="text-sm text-red-600 mb-4">{error}</p>
        <button
          onClick={() => router.replace("/settings")}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700"
        >
          Back to Settings
        </button>
      </div>
    );
  }

  return <p className="text-sm text-gray-500">Connecting Twitter...</p>;
}

export default function TwitterCallbackPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Suspense fallback={<p className="text-sm text-gray-500">Loading...</p>}>
        <TwitterCallbackInner />
      </Suspense>
    </div>
  );
}
