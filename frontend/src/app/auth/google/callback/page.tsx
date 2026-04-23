"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { client } from "@/lib/api-client";

export const dynamic = "force-dynamic";

function GoogleCallbackInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code) {
      setError("Missing authorization code from Google.");
      return;
    }

    void (async () => {
      const { data, error } = await client.POST("/api/v1/auth/google/callback", {
        body: { code, state: state ?? undefined },
      });
      if (error) {
        setError((error as { detail?: string })?.detail ?? "Google authentication failed.");
      } else {
        const token = (data?.data as { access_token?: string })?.access_token;
        if (token) {
          localStorage.setItem("access_token", token);
        }
        const returnTo = localStorage.getItem("google_oauth_return");
        localStorage.removeItem("google_oauth_return");
        router.replace(returnTo || "/settings?connected=google");
      }
    })();
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

  return <p className="text-sm text-gray-500">Connecting Google...</p>;
}

function GoogleCallbackPageContent() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Suspense fallback={<p className="text-sm text-gray-500">Loading...</p>}>
        <GoogleCallbackInner />
      </Suspense>
    </div>
  );
}

function PageLoading() { return <div className="min-h-screen flex items-center justify-center"><div className="animate-spin h-8 w-8 border-4 border-teal-500 border-t-transparent rounded-full" /></div>; }
export default function GoogleCallbackPage() { return <Suspense fallback={<PageLoading />}><GoogleCallbackPageContent /></Suspense>; }
